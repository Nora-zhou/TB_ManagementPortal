<template>
  <div class="sub-order-import">
    <h3>订单信息导入</h3>
    <p class="hint">上传淘宝后台导出的订单明细 Excel 文件（支持 .xlsx 格式）。导入后会自动核对本次涉及的月份。</p>
    <div class="file-area">
      <label class="file-label">
        <input
          ref="fileInput"
          type="file"
          accept=".xlsx"
          @change="onFileChange"
          :disabled="loading"
          class="file-input"
        />
        <span class="file-btn">选择文件</span>
        <span class="file-name">{{ selectedFile ? selectedFile.name : '未选择文件' }}</span>
      </label>
      <button @click="upload" :disabled="!selectedFile || loading" class="btn-primary">
        {{ loading ? '上传中...' : '上传' }}
      </button>
    </div>

    <div v-if="result" class="result-box">
      <p>✅ 导入完成</p>
      <ul>
        <li>新增：{{ result.imported }} 条</li>
        <li>更新：{{ result.updated }} 条</li>
        <li>跳过：{{ result.skipped }} 条</li>
        <li v-if="result.errors.length > 0">无效行：{{ result.errors.length }} 条</li>
      </ul>
      <details v-if="result.errors.length > 0">
        <summary>查看无效行详情</summary>
        <ul class="error-list">
          <li v-for="(e, i) in result.errors" :key="i">{{ e }}</li>
        </ul>
      </details>
    </div>

    <div v-if="errorMsg" class="error-box">
      ❌ {{ errorMsg }}
    </div>

    <!-- 导入后自动核对 -->
    <div v-if="checks.length" class="recon-box">
      <div class="recon-head">
        <h4>导入后自动核对</h4>
        <p class="recon-sub">
          库内汇总（按订单创建时间）对比生意参谋「核心指标监控」。未录入平台数据的月份只做内部一致性检查。
        </p>
      </div>

      <div v-for="c in checks" :key="c.month" class="recon-card" :class="'is-' + c.status">
        <div class="recon-card-head">
          <span class="recon-month">{{ c.month }}<small v-if="c.store != null"> · 店铺{{ c.store }}</small></span>
          <span class="badge" :class="'badge-' + c.status">{{ statusText(c.status) }}</span>
          <span class="recon-days">有单 {{ c.days_with_data }}/{{ c.expected_days }} 天</span>
        </div>

        <table class="recon-table">
          <thead>
            <tr>
              <th>指标</th>
              <th>库内</th>
              <th>平台</th>
              <th>差异</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>销售额</td>
              <td>{{ money(c.db_pay_amount) }}</td>
              <td>{{ money(c.platform_pay_amount) }}</td>
              <td :class="diffClass(c.pay_diff_pct)">
                <strong>{{ pct(c.pay_diff_pct) }}</strong>
              </td>
            </tr>
            <tr>
              <td>退款额</td>
              <td>{{ money(c.db_refund_amount) }}</td>
              <td>{{ money(c.platform_refund_amount) }}</td>
              <td :class="diffClass(c.refund_diff_pct)">{{ pct(c.refund_diff_pct) }}</td>
            </tr>
            <tr>
              <td>支付件数</td>
              <td>{{ c.db_items }}</td>
              <td>{{ numOrDash(c.platform_paid_items) }}</td>
              <td :class="diffClass(c.items_diff_pct)">{{ pct(c.items_diff_pct) }}</td>
            </tr>
            <tr>
              <td>支付单数</td>
              <td>{{ c.db_orders }}</td>
              <td>{{ numOrDash(c.platform_paid_buyers) }}</td>
              <td :class="diffClass(c.buyers_diff_pct)">{{ pct(c.buyers_diff_pct) }}</td>
            </tr>
          </tbody>
        </table>

        <ul v-if="c.hints.length" class="recon-hints">
          <li v-for="(h, i) in c.hints" :key="i">{{ h }}</li>
        </ul>

        <details class="recon-form" :open="!c.has_platform">
          <summary>{{ c.has_platform ? '修改该月平台数据' : '录入生意参谋数据，完成外部对账' }}</summary>
          <div class="form-grid">
            <label>支付金额<input v-model="forms[c.month].pay_amount" type="text" inputmode="decimal" placeholder="20754.46" /></label>
            <label>退款金额<input v-model="forms[c.month].refund_amount" type="text" inputmode="decimal" placeholder="4511.08" /></label>
            <label>支付件数<input v-model="forms[c.month].paid_items" type="text" inputmode="decimal" placeholder="766" /></label>
            <label>支付买家数<input v-model="forms[c.month].paid_buyers" type="text" inputmode="decimal" placeholder="320" /></label>
          </div>
          <div class="form-actions">
            <button class="btn-save" @click="savePlatform(c)" :disabled="saving === c.month">
              {{ saving === c.month ? '保存中...' : '保存并重新核对' }}
            </button>
            <span v-if="formMsg[c.month]" class="form-msg">{{ formMsg[c.month] }}</span>
          </div>
        </details>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { importSubOrders } from '../api/sub_orders.js'
import { syncOrdersFromSubOrders } from '../api/orders.js'
import { fetchMonthlyChecks, savePlatformStat } from '../api/reconcile.js'

const props = defineProps({
  store: { type: Number, default: 1 }
})

const fileInput = ref(null)
const selectedFile = ref(null)
const loading = ref(false)
const result = ref(null)
const errorMsg = ref(null)

const checks = ref([])
const forms = reactive({})
const formMsg = reactive({})
const saving = ref(null)

function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
  result.value = null
  errorMsg.value = null
  checks.value = []
}

async function upload() {
  if (!selectedFile.value) return
  loading.value = true
  result.value = null
  errorMsg.value = null
  checks.value = []
  try {
    result.value = await importSubOrders(selectedFile.value, props.store)
    // Auto-sync to orders table so order list reflects the new data
    await syncOrdersFromSubOrders()
    applyChecks(result.value.reconcile || [])
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}

function applyChecks(items) {
  checks.value = items
  for (const item of items) {
    forms[item.month] = {
      pay_amount: toInput(item.platform_pay_amount),
      refund_amount: toInput(item.platform_refund_amount),
      paid_items: toInput(item.platform_paid_items),
      paid_buyers: toInput(item.platform_paid_buyers),
    }
    formMsg[item.month] = ''
  }
}

async function savePlatform(item) {
  const form = forms[item.month]
  const payload = {
    store: item.store ?? props.store,
    period_month: item.month,
    pay_amount: toNumber(form.pay_amount),
    refund_amount: toNumber(form.refund_amount),
    paid_items: toNumber(form.paid_items),
    paid_buyers: toNumber(form.paid_buyers),
  }
  if (payload.pay_amount == null) {
    formMsg[item.month] = '请至少填写「支付金额」'
    return
  }
  saving.value = item.month
  formMsg[item.month] = ''
  try {
    await savePlatformStat(payload)
    const res = await fetchMonthlyChecks({
      store: payload.store,
      startMonth: item.month,
      endMonth: item.month,
    })
    const updated = (res.items || []).find((i) => i.month === item.month)
    if (updated) {
      const index = checks.value.findIndex((c) => c.month === item.month)
      if (index >= 0) checks.value.splice(index, 1, updated)
    }
    formMsg[item.month] = '已保存，核对结果已刷新'
  } catch (e) {
    formMsg[item.month] = e.message
  } finally {
    saving.value = null
  }
}

function toNumber(value) {
  const text = String(value ?? '').trim()
  if (!text) return null
  const n = Number(text)
  return Number.isFinite(n) ? n : null
}

function toInput(value) {
  return value == null ? '' : String(value)
}

function money(value) {
  if (value == null) return '—'
  return '¥' + Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function numOrDash(value) {
  return value == null ? '—' : Number(value).toLocaleString('zh-CN')
}

function pct(value) {
  if (value == null) return '—'
  return (value > 0 ? '+' : '') + value.toFixed(1) + '%'
}

function diffClass(value) {
  if (value == null) return 'diff-none'
  const abs = Math.abs(value)
  if (abs <= 5) return 'diff-ok'
  if (abs <= 15) return 'diff-warn'
  return 'diff-gap'
}

function statusText(status) {
  if (status === 'gap') return '疑似漏单'
  if (status === 'warning') return '待确认'
  return '正常'
}
</script>

<style scoped>
.sub-order-import { padding: 0; }

h3 {
  font-size: 18px; font-weight: 500; letter-spacing: 0.15px;
  color: var(--text); margin-bottom: 8px;
}

.hint {
  font-size: 13px; color: var(--text-muted); line-height: 1.6; margin-bottom: 20px;
}

.file-area {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  padding: 14px 18px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: 16px;
}

.file-label {
  display: flex; align-items: center; gap: 10px; cursor: pointer; flex: 1;
}
.file-input { display: none; }
.file-btn {
  padding: 7px 16px;
  border: 1px solid var(--border); border-radius: 9999px;
  font-size: 13px; font-weight: 500; cursor: pointer;
  background: var(--surface); color: var(--text);
  transition: background 0.15s; white-space: nowrap;
}
.file-label:hover .file-btn { background: var(--border); }
.file-name { font-size: 13px; color: var(--text-muted); }

.btn-primary {
  padding: 9px 24px;
  background: #000; color: #fff;
  border: none; border-radius: 9999px; cursor: pointer;
  font-size: 13px; font-weight: 500;
  box-shadow: var(--shadow-card); transition: background 0.15s;
  white-space: nowrap; flex-shrink: 0;
}
.btn-primary:hover:not(:disabled) { background: #222; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.result-box {
  margin-top: 0; padding: 16px 20px;
  background: #f0fdf4; border: 1px solid #bbf7d0;
  border-radius: 16px; font-size: 13px;
}
.result-box p { font-weight: 500; color: #166534; margin-bottom: 8px; }
.result-box ul { padding-left: 16px; color: var(--text-secondary); line-height: 1.7; }

.error-box {
  margin-top: 16px; padding: 12px 16px;
  background: #fef2f2; border: 1px solid #fecaca;
  border-radius: 10px; color: var(--danger);
  font-size: 13px;
}

details summary {
  cursor: pointer; font-size: 12px;
  color: var(--text-muted); margin-top: 8px;
}
.error-list {
  max-height: 160px; overflow-y: auto;
  font-size: 12px; color: var(--danger);
  padding-left: 16px; margin-top: 6px;
  line-height: 1.6;
}

/* ── 核对区 ── */
.recon-box { margin-top: 24px; }

.recon-head h4 {
  font-size: 15px; font-weight: 500; color: var(--text); margin-bottom: 4px;
}
.recon-sub {
  font-size: 12px; color: var(--text-muted); line-height: 1.6; margin-bottom: 14px;
}

.recon-card {
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 16px 18px;
  margin-bottom: 12px;
  background: var(--surface);
}
.recon-card.is-gap { border-color: #fecaca; background: #fffafa; }
.recon-card.is-warning { border-color: #fde68a; background: #fffdf5; }

.recon-card-head {
  display: flex; align-items: center; gap: 10px; margin-bottom: 12px;
}
.recon-month { font-size: 14px; font-weight: 500; color: var(--text); }
.recon-month small { font-weight: 400; color: var(--text-muted); }
.recon-days { margin-left: auto; font-size: 12px; color: var(--text-muted); }

.badge {
  font-size: 11px; font-weight: 500; padding: 2px 9px; border-radius: 9999px;
}
.badge-ok { background: #ecfdf5; color: #047857; }
.badge-warning { background: #fffbeb; color: #b45309; }
.badge-gap { background: #fef2f2; color: #b91c1c; }

.recon-table {
  width: 100%; border-collapse: collapse; font-size: 12.5px;
}
.recon-table th {
  text-align: right; font-weight: 500; color: var(--text-muted);
  padding: 6px 8px; border-bottom: 1px solid var(--border);
}
.recon-table th:first-child { text-align: left; }
.recon-table td {
  text-align: right; padding: 6px 8px; color: var(--text);
  border-bottom: 1px solid var(--border-subtle, #f1f5f9);
}
.recon-table td:first-child { text-align: left; color: var(--text-secondary); }

.diff-none { color: var(--text-muted); }
.diff-ok { color: #047857; }
.diff-warn { color: #b45309; }
.diff-gap { color: #b91c1c; font-weight: 500; }

.recon-hints {
  margin: 10px 0 0; padding-left: 16px;
  font-size: 12px; color: var(--text-secondary); line-height: 1.7;
}

.recon-form { margin-top: 12px; }
.recon-form summary {
  font-size: 12px; color: var(--text-muted); cursor: pointer;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
  margin: 12px 0;
}
.form-grid label {
  display: flex; flex-direction: column; gap: 4px;
  font-size: 12px; color: var(--text-muted);
}
.form-grid input {
  border: 1px solid var(--border); border-radius: 8px;
  padding: 6px 10px; font-size: 13px; color: var(--text);
  background: var(--surface); outline: none;
}

.form-actions { display: flex; align-items: center; gap: 12px; }
.btn-save {
  padding: 7px 18px; border-radius: 9999px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text);
  font-size: 12.5px; font-weight: 500; cursor: pointer;
}
.btn-save:hover:not(:disabled) { background: var(--bg-subtle); }
.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }
.form-msg { font-size: 12px; color: var(--text-muted); }
</style>
