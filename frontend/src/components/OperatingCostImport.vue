<template>
  <div class="op-cost-page">
    <div class="page-header">
      <h1 class="page-title">运营成本导入</h1>
      <p class="page-desc">
        上传淘宝账单中心导出的「汇总账单.xlsx」，按月把平台服务费、推广费、运费险等计入成本，自动参与纯利润计算。
      </p>
    </div>

    <div class="card">
      <div class="store-row">
        <span class="field-label">归属店铺</span>
        <label class="radio"><input v-model="store" type="radio" :value="1" /> 店铺1</label>
        <label class="radio"><input v-model="store" type="radio" :value="2" /> 店铺2</label>
        <span class="field-tip">同一月份重复导入，会覆盖相同业务大类的金额</span>
      </div>

      <div class="file-area">
        <label class="file-label">
          <input
            ref="fileInput"
            type="file"
            accept=".xlsx,.xlsm"
            class="file-input"
            :disabled="loading"
            @change="onFileChange"
          />
          <span class="file-btn">选择账单文件</span>
          <span class="file-name">{{ selectedFile ? selectedFile.name : '未选择文件' }}</span>
        </label>
        <button class="btn-primary" :disabled="!selectedFile || loading" @click="upload">
          {{ loading ? '导入中…' : '导入账单' }}
        </button>
      </div>

      <p class="hint">
        必需列：月份、业务大类、本月付款（缺失时取扣费金额合计）；「本月交易额」会一并导入，
        用于在运营费用分析里计算 ROI。业务大类自动归类：
        含「服务费 / 佣金 / 扣费」→ 平台扣费，含「推广 / 直通车 / 万相台」→ 推广费，
        含「险」→ 运费险，其余 → 其它费用。<br />
        汇总账单已覆盖平台服务费，同一月份请勿再用 RPA 重复抓取平台扣费。
      </p>
    </div>

    <div v-if="result" class="result-card">
      <div class="result-head">
        <span class="result-title">
          导入完成：新增 {{ result.imported }} 条，更新 {{ result.updated }} 条
        </span>
        <span v-if="result.month" class="result-meta">
          {{ result.month }} · 合计 ¥{{ money(result.total_amount) }}
        </span>
      </div>

      <table v-if="result.items.length" class="result-table">
        <thead>
          <tr>
            <th>月份</th>
            <th>业务大类</th>
            <th>归类</th>
            <th class="num">计入成本</th>
            <th class="num">本月交易额</th>
            <th>动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in result.items" :key="index">
            <td>{{ item.period_month }}</td>
            <td>{{ item.business_type }}</td>
            <td>{{ categoryLabel(item.category) }}</td>
            <td class="num">¥{{ money(item.amount) }}</td>
            <td class="num">¥{{ money(item.transaction_amount) }}</td>
            <td>{{ item.action === 'updated' ? '更新' : '新增' }}</td>
          </tr>
        </tbody>
      </table>

      <details v-if="result.errors.length" class="error-details">
        <summary>未导入 {{ result.errors.length }} 行</summary>
        <ul>
          <li v-for="(error, index) in result.errors" :key="index">{{ error }}</li>
        </ul>
      </details>
    </div>

    <div v-if="errorMsg" class="error-box">{{ errorMsg }}</div>

    <div class="list-card">
      <div class="list-head">
        <div>
          <span class="list-title">已导入的运营成本</span>
          <span class="list-sub">{{ store }} 店 · 来源：账单导入</span>
        </div>
        <button class="btn-ghost" :disabled="listLoading" @click="loadRecords">刷新</button>
      </div>

      <div v-if="listLoading" class="empty">加载中…</div>
      <div v-else-if="records.length === 0" class="empty">暂无账单导入记录</div>
      <table v-else class="data-table">
        <thead>
          <tr>
            <th>月份</th>
            <th>类别</th>
            <th>业务大类</th>
            <th class="num">金额</th>
            <th class="num">本月交易额</th>
            <th>备注</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in records" :key="row.id">
            <td>{{ row.period_month }}</td>
            <td>{{ categoryLabel(row.category) }}</td>
            <td>{{ row.sub_category || '—' }}</td>
            <td class="num">¥{{ money(row.amount) }}</td>
            <td class="num">¥{{ money(row.transaction_amount) }}</td>
            <td class="note">{{ row.note || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { fetchExpenses, importExpenseBill } from '../api/profit.js'

const CATEGORY_LABELS = {
  platform_fee: '平台扣费',
  promotion: '推广费',
  shipping_insurance: '运费险',
  other: '其它费用',
}

const store = ref(1)
const fileInput = ref(null)
const selectedFile = ref(null)
const loading = ref(false)
const result = ref(null)
const errorMsg = ref(null)

const records = ref([])
const listLoading = ref(false)

function categoryLabel(value) {
  return CATEGORY_LABELS[value] || value
}

function money(value) {
  const number = Number(value || 0)
  return number.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function onFileChange(event) {
  selectedFile.value = event.target.files[0] || null
  result.value = null
  errorMsg.value = null
}

async function upload() {
  if (!selectedFile.value) return
  loading.value = true
  result.value = null
  errorMsg.value = null
  try {
    result.value = await importExpenseBill(selectedFile.value, store.value)
    await loadRecords()
  } catch (error) {
    console.error('[运营成本导入] 导入失败', error)
    errorMsg.value = error.message || '导入失败'
  } finally {
    loading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function loadRecords() {
  listLoading.value = true
  try {
    const data = await fetchExpenses({ store: store.value, source: 'xlsx' })
    records.value = data.items || []
  } catch (error) {
    console.error('[运营成本导入] 加载已导入记录失败', error)
    records.value = []
    errorMsg.value = error.message || '加载已导入记录失败'
  } finally {
    listLoading.value = false
  }
}

watch(store, () => {
  result.value = null
  errorMsg.value = null
  loadRecords()
})

onMounted(loadRecords)
</script>

<style scoped>
.op-cost-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 980px;
}

.page-header { display: flex; flex-direction: column; gap: 4px; }
.page-title { font-size: 28px; font-weight: 300; margin: 0; color: var(--text); letter-spacing: -0.5px; }
.page-desc { font-size: 14px; color: var(--text-muted); margin: 0; line-height: 1.6; }

.card {
  background: var(--surface);
  border-radius: 16px;
  padding: 24px 28px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}

.store-row {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: 12px;
  margin-bottom: 18px;
}
.field-label { font-size: 13px; font-weight: 500; color: var(--text-secondary); }
.radio { display: flex; align-items: center; gap: 6px; font-size: 14px; cursor: pointer; }
.field-tip { font-size: 12px; color: var(--text-muted); }

.file-area {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 18px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: 16px;
}

.file-label { display: flex; align-items: center; gap: 10px; cursor: pointer; flex: 1; }
.file-input { display: none; }
.file-btn {
  padding: 7px 16px;
  border: 1px solid var(--border);
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 500;
  background: var(--surface);
  color: var(--text);
  white-space: nowrap;
}
.file-name { font-size: 13px; color: var(--text-muted); }

.btn-primary {
  padding: 8px 20px;
  background: #000;
  color: #fff;
  border: none;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.hint {
  margin: 14px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-muted);
}

.result-card {
  background: var(--surface);
  border-radius: 16px;
  padding: 20px 24px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.result-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.result-title { font-size: 14px; font-weight: 500; color: var(--text); }
.result-meta { font-size: 13px; color: var(--text-muted); }

.result-table,
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.result-table th,
.data-table th {
  text-align: left;
  padding: 8px 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}
.result-table td,
.data-table td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}
.result-table .num,
.data-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.data-table .note { max-width: 260px; color: var(--text-muted); }

.error-details { margin-top: 12px; font-size: 12.5px; color: var(--text-muted); }
.error-details summary { cursor: pointer; }
.error-details ul { margin: 8px 0 0; padding-left: 18px; max-height: 180px; overflow: auto; }

.error-box {
  padding: 12px 16px;
  border-radius: 10px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-size: 13px;
}

.list-card {
  background: var(--surface);
  border-radius: 16px;
  padding: 20px 24px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.list-title { font-size: 14px; font-weight: 500; color: var(--text); }
.list-sub { margin-left: 10px; font-size: 12px; color: var(--text-muted); }

.empty { padding: 28px 0; text-align: center; font-size: 13px; color: var(--text-muted); }

.btn-ghost {
  padding: 5px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 9999px;
  font-size: 12.5px;
  color: var(--text-secondary);
  cursor: pointer;
}
.btn-ghost:hover:not(:disabled) { background: var(--bg-subtle); color: var(--text); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
