<script setup>
import { ref, onMounted, watch } from 'vue'
import {
  fetchSKUList,
  fetchSKUCosts,
  saveSKUCosts,
  fetchSKUCostSuggest,
  fetchProfitSummary,
  fetchProductProfitMonthly,
  fetchMonthOrders,
} from '../api/products.js'

const props = defineProps({ productId: { type: Number, required: true } })

// ── Profit summary ──
const summary = ref(null)
const loadingSummary = ref(false)
const summaryError = ref(null)

// ── Monthly data ──
const monthly = ref([])
const loadingMonthly = ref(false)

// ── Month detail (click on bar) ──
const selectedMonth = ref(null)
const monthDetail = ref(null)
const loadingDetail = ref(false)

async function selectMonth(month) {
  if (selectedMonth.value === month) { selectedMonth.value = null; monthDetail.value = null; return }
  selectedMonth.value = month
  loadingDetail.value = true
  try {
    monthDetail.value = await fetchMonthOrders(props.productId, month)
  } catch {
    monthDetail.value = null
  } finally {
    loadingDetail.value = false
  }
}

// ── SKU costs editor ──
const skuItems = ref([])
const loadingSkus = ref(false)
const saving = ref(false)
const saveMsg = ref(null)
const saveError = ref(null)
const suggestData = ref(null)

// ── Load helpers ──
async function loadAll() {
  loadSummary()
  loadMonthly()
  loadSkus()
}

async function loadSummary() {
  loadingSummary.value = true
  summaryError.value = null
  try {
    summary.value = await fetchProfitSummary(props.productId)
  } catch (e) {
    summaryError.value = e.message
  } finally {
    loadingSummary.value = false
  }
}

async function loadMonthly() {
  loadingMonthly.value = true
  try {
    const data = await fetchProductProfitMonthly(props.productId)
    monthly.value = (data.items || data.months || []).slice(-12)
  } catch {
    monthly.value = []
  } finally {
    loadingMonthly.value = false
  }
}

async function loadSkus() {
  loadingSkus.value = true
  try {
    const [skuList, costs] = await Promise.all([
      fetchSKUList(props.productId),
      fetchSKUCosts(props.productId),
    ])
    const costMap = Object.fromEntries((costs || []).map(c => [c.sku_id, c]))
    const baseList = (skuList || []).length > 0
      ? skuList
      : (costs || []).map(c => ({ sku_id: c.sku_id, sku_name: c.sku_name }))
    skuItems.value = baseList.map(s => ({
      sku_id: s.sku_id,
      sku_name: s.sku_name || s.sku_id || '默认（无规格）',
      purchase_cost: costMap[s.sku_id]?.purchase_cost ?? '',
      hasError: false,
      errorMsg: '',
    }))
    // non-blocking suggest
    fetchSKUCostSuggest(props.productId)
      .then(d => { suggestData.value = d })
      .catch(() => {})
  } finally {
    loadingSkus.value = false
  }
}

function validateItem(item) {
  const v = item.purchase_cost
  if (v === '' || v == null) { item.hasError = false; item.errorMsg = ''; return }
  const num = Number(v)
  if (isNaN(num) || num < 0) {
    item.hasError = true; item.errorMsg = '须为非负数字'
  } else if (!/^\d+(\.\d{0,2})?$/.test(String(v).trim())) {
    item.hasError = true; item.errorMsg = '最多两位小数'
  } else {
    item.hasError = false; item.errorMsg = ''
  }
}

function applySuggest() {
  if (!suggestData.value?.available) return
  skuItems.value.forEach(item => {
    item.purchase_cost = String(suggestData.value.suggested_cost ?? '')
    validateItem(item)
  })
}

async function saveCosts() {
  skuItems.value.forEach(validateItem)
  if (skuItems.value.some(r => r.hasError)) return
  saving.value = true; saveMsg.value = null; saveError.value = null
  try {
    const items = skuItems.value.map(r => ({
      sku_id: r.sku_id,
      sku_name: r.sku_name,
      purchase_cost: (r.purchase_cost === '' || r.purchase_cost == null) ? 0 : Number(r.purchase_cost),
    }))
    await saveSKUCosts(props.productId, items)
    saveMsg.value = '保存成功'
    setTimeout(() => { saveMsg.value = null }, 3000)
    loadSummary()
    loadMonthly()
  } catch (e) {
    saveError.value = `保存失败: ${e.message}`
  } finally {
    saving.value = false
  }
}

// ── Bar chart helpers ──
function barColor(value) {
  return value < 0 ? '#e74c3c' : '#27ae60'
}
function maxAbsProfit() {
  return Math.max(1, ...monthly.value.map(m => Math.abs(m.gross_profit ?? 0)))
}
function barHeight(value) {
  return Math.round((Math.abs(value ?? 0) / maxAbsProfit()) * 200)
}

// ── Format helpers ──
function fmt(n) {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(n) {
  if (n == null) return '—'
  return n.toFixed(1) + '%'
}
function marginColor(n) {
  if (n == null) return ''
  if (n < 0) return 'kpi--red'
  if (n < 10) return 'kpi--orange'
  return 'kpi--green'
}

watch(() => props.productId, () => { selectedMonth.value = null; monthDetail.value = null; loadAll() })
onMounted(loadAll)
</script>

<template>
  <div class="profit-analysis">
    <h3 class="section-title">利润分析</h3>

    <!-- SKU cost editor -->
    <div class="cost-editor">
      <h4 class="subsection-title">采购成本设置</h4>
      <div v-if="loadingSkus" class="muted">加载中…</div>
      <template v-else>
        <div v-if="skuItems.length === 0" class="muted">暂无 SKU 数据，请先导入子订单</div>
        <table v-else class="sku-table">
          <thead>
            <tr>
              <th>SKU 规格</th>
              <th>采购成本（元/件）</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in skuItems" :key="item.sku_id">
              <td>{{ item.sku_name }}</td>
              <td>
                <input
                  v-model="item.purchase_cost"
                  type="text"
                  class="cost-input"
                  :class="{ 'cost-input--error': item.hasError }"
                  placeholder="未设置"
                  @input="validateItem(item)"
                />
                <span v-if="item.hasError" class="inline-error">{{ item.errorMsg }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="cost-actions">
          <button
            v-if="suggestData?.available"
            class="btn btn-sm btn-suggest"
            @click="applySuggest"
          >从采购单推算</button>
          <span class="spacer" />
          <span v-if="saveMsg" class="save-msg">{{ saveMsg }}</span>
          <span v-if="saveError" class="save-error">{{ saveError }}</span>
          <button
            class="btn btn-sm btn-primary"
            :disabled="saving || skuItems.some(r => r.hasError)"
            @click="saveCosts"
          >{{ saving ? '保存中…' : '保存成本' }}</button>
        </div>
      </template>
    </div>

    <!-- KPI cards -->
    <div v-if="loadingSummary" class="muted">加载利润数据中…</div>
    <div v-else-if="summaryError" class="error-msg">{{ summaryError }}</div>
    <template v-else-if="summary">
      <div v-if="!summary.cost_configured" class="notice notice--info">
        请先设置采购成本以启用利润分析
      </div>
      <template v-else>
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">已销数量</div>
            <div class="kpi-value">{{ summary.units_sold ?? '—' }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">总销售额</div>
            <div class="kpi-value">¥{{ fmt(summary.revenue) }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">总成本</div>
            <div class="kpi-value">¥{{ fmt(summary.cost) }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">毛利润</div>
            <div class="kpi-value" :class="marginColor(summary.gross_profit)">¥{{ fmt(summary.gross_profit) }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">毛利率</div>
            <div class="kpi-value" :class="marginColor(summary.gross_margin_pct)">{{ fmtPct(summary.gross_margin_pct) }}</div>
          </div>
        </div>

        <!-- Monthly bar chart -->
        <div class="monthly-chart">
          <h4 class="subsection-title">月度毛利走势（近 12 个月）<span v-if="selectedMonth" class="month-hint">点击同一月份取消选中</span></h4>
          <div v-if="loadingMonthly" class="muted">加载中…</div>
          <div v-else-if="monthly.length === 0" class="muted">暂无月度数据</div>
          <div v-else class="chart-detail-layout">
            <!-- Bar chart -->
            <div class="bar-chart">
              <div
                v-for="m in monthly"
                :key="m.month"
                class="bar-col"
                :class="{ 'bar-col--selected': selectedMonth === m.month }"
                @click="selectMonth(m.month)"
              >
                <div class="bar-value-label">{{ m.gross_profit > 0 ? '¥' + fmt(m.gross_profit) : '' }}</div>
                <div class="bar-wrap">
                  <div
                    class="bar"
                    :style="{ height: barHeight(m.gross_profit) + 'px', background: barColor(m.gross_profit) }"
                    :title="`${m.month}: ¥${fmt(m.gross_profit)}`"
                  />
                </div>
                <div class="bar-label">{{ m.month?.slice(5) }}</div>
              </div>
            </div>

            <!-- Month detail panel -->
            <transition name="detail-fade">
            <div v-if="selectedMonth" class="month-detail">
              <div class="month-detail-header">
                <div class="month-detail-meta">
                  <span class="month-detail-title">{{ selectedMonth }} 订单明细</span>
                  <div v-if="monthDetail" class="month-kpis">
                    <span class="kpi-chip">已售 <strong>{{ monthDetail.units_sold }}</strong> 件</span>
                    <span class="kpi-chip">收入 <strong>¥{{ fmt(monthDetail.revenue) }}</strong></span>
                    <span class="kpi-chip">成本 <strong>¥{{ fmt(monthDetail.cost) }}</strong></span>
                    <span class="kpi-chip" :class="monthDetail.gross_profit >= 0 ? 'kpi--green' : 'kpi--red'">毛利 <strong>¥{{ fmt(monthDetail.gross_profit) }}</strong></span>
                  </div>
                </div>
                <button class="month-detail-close" @click="selectedMonth = null; monthDetail = null">×</button>
              </div>
              <div v-if="loadingDetail" class="muted detail-loading">加载中…</div>
              <template v-else-if="monthDetail">
                <div class="detail-table-wrap">
                  <table class="detail-table">
                    <thead>
                      <tr>
                        <th>日期</th>
                        <th>SKU</th>
                        <th class="num">数量</th>
                        <th class="num">实付</th>
                        <th class="num">成本</th>
                        <th class="num">毛利</th>
                        <th>状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="o in monthDetail.orders" :key="o.sub_order_id" :class="{ 'row--refund': o.refund_amount > 0 }">
                        <td class="mono">{{ o.date }}</td>
                        <td class="sku-cell" :title="o.sku_name">{{ o.sku_name }}</td>
                        <td class="num">{{ o.quantity }}</td>
                        <td class="num">¥{{ fmt(o.buyer_paid) }}</td>
                        <td class="num">¥{{ fmt(o.quantity * o.unit_cost) }}</td>
                        <td class="num" :class="o.gross_profit >= 0 ? 'profit-pos' : 'profit-neg'">¥{{ fmt(o.gross_profit) }}</td>
                        <td class="status-cell">{{ o.status }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>
            </div>
            </transition>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.profit-analysis {
  margin-top: 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-title    { font-size: 17px; font-weight: 500; margin: 0 0 4px; color: var(--text); }
.subsection-title { font-size: 14px; font-weight: 500; margin: 0 0 10px; color: var(--text-muted); }

.muted     { font-size: 13.5px; color: var(--text-muted); }
.error-msg { font-size: 13.5px; color: var(--danger); }
.save-msg  { font-size: 13px; color: var(--success); }
.save-error { font-size: 13px; color: var(--danger); }

/* SKU table */
.sku-table { width: 100%; border-collapse: collapse; font-size: 13.5px; margin-bottom: 10px; }
.sku-table th { text-align: left; padding: 5px 10px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--border-subtle); }
.sku-table td { padding: 5px 10px; border-top: 1px solid var(--border-subtle); }

.cost-input { padding: 4px 8px; border: 1px solid var(--border); border-radius: 8px; font-size: 13.5px; width: 110px; box-shadow: var(--shadow-inset); }
.cost-input--error { border-color: var(--danger); }
.inline-error { color: var(--danger); font-size: 12px; margin-left: 6px; }

.cost-actions { display: flex; align-items: center; gap: 8px; }
.spacer { flex: 1; }

/* Buttons */
.btn { padding: 5px 12px; border-radius: 9999px; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid var(--border); background: var(--surface); color: var(--text); box-shadow: var(--shadow-soft); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #000; color: #fff; border-color: #000; box-shadow: var(--shadow-card); }
.btn-primary:hover:not(:disabled) { background: #222; }
.btn-suggest { background: var(--bg-warm); border-color: var(--border); color: var(--text); box-shadow: var(--shadow-warm); }

/* Notice */
.notice { font-size: 13px; padding: 8px 12px; border-radius: 8px; }
.notice--info { background: var(--bg-subtle); color: var(--text-secondary); border: 1px solid var(--border); }

/* KPI grid */
.kpi-grid { display: flex; flex-wrap: wrap; gap: 12px; }
.kpi-card { background: var(--surface); border-radius: 16px; padding: 14px 18px; min-width: 110px; box-shadow: var(--shadow-outline), var(--shadow-soft); }
.kpi-label { font-size: 12px; color: var(--text-muted); margin-bottom: 4px; letter-spacing: 0.12px; }
.kpi-value { font-size: 18px; font-weight: 300; color: var(--text); letter-spacing: -0.2px; }
.kpi--red    { color: var(--danger) !important; }
.kpi--orange { color: var(--warning) !important; }
.kpi--green  { color: var(--success) !important; }

/* Monthly chart */
.monthly-chart { display: flex; flex-direction: column; gap: 12px; }
.month-hint { font-size: 11px; color: var(--text-muted); font-weight: 400; margin-left: 8px; }
.chart-detail-layout { display: flex; flex-direction: column; gap: 16px; }

/* Bar chart */
.bar-chart { display: flex; gap: 8px; align-items: flex-end; padding-bottom: 4px; overflow-x: auto; }
.bar-col   { display: flex; flex-direction: column; align-items: center; min-width: 56px; cursor: pointer; border-radius: 8px; padding: 4px 4px 0; transition: background .12s; }
.bar-col:hover { background: var(--bg-subtle); }
.bar-col--selected { background: var(--bg-subtle); outline: 2px solid var(--border); }
.bar-value-label { font-size: 10px; color: var(--text-muted); white-space: nowrap; margin-bottom: 2px; height: 14px; }
.bar-wrap  { height: 180px; display: flex; align-items: flex-end; }
.bar       { width: 36px; border-radius: 6px 6px 0 0; min-height: 3px; transition: height 0.2s; }
.bar-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; white-space: nowrap; }

/* Month detail panel */
.month-detail {
  background: var(--surface);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: rgba(0,0,0,0.06) 0px 0px 0px 1px, rgba(0,0,0,0.04) 0px 4px 8px;
}
.month-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 20px 14px;
  border-bottom: 1px solid var(--border-subtle);
}
.month-detail-meta { display: flex; flex-direction: column; gap: 8px; }
.month-detail-title { font-size: 14px; font-weight: 500; color: var(--text); letter-spacing: 0.14px; }
.month-detail-close {
  background: none; border: none; cursor: pointer;
  font-size: 14px; color: var(--text-muted);
  padding: 2px 6px; line-height: 1;
  border-radius: 6px;
  transition: background 0.12s, color 0.12s;
  flex-shrink: 0;
  margin-top: -2px;
}
.month-detail-close:hover { background: var(--bg-subtle); color: var(--text); }
.month-kpis { display: flex; gap: 20px; flex-wrap: wrap; }
.kpi-chip { font-size: 13px; color: var(--text-muted); letter-spacing: 0.13px; }
.kpi-chip strong { color: var(--text); font-weight: 500; }
.detail-loading { padding: 20px; }
.detail-table-wrap { overflow-x: auto; max-height: 280px; overflow-y: auto; }
.detail-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.detail-table th { position: sticky; top: 0; background: var(--surface); text-align: left; padding: 8px 16px; color: var(--text-muted); font-weight: 500; font-size: 12px; letter-spacing: 0.12px; border-bottom: 1px solid var(--border-subtle); white-space: nowrap; }
.detail-table td { padding: 8px 16px; border-top: 1px solid var(--border-subtle); white-space: nowrap; letter-spacing: 0.13px; }
.detail-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.detail-table .mono { font-family: ui-monospace, monospace; font-size: 12px; color: var(--text-muted); }
.detail-table .sku-cell { max-width: 200px; overflow: hidden; text-overflow: ellipsis; }
.detail-table .status-cell { font-size: 12px; color: var(--text-muted); }
.detail-table .profit-pos { color: var(--success); font-weight: 500; }
.detail-table .profit-neg { color: var(--danger); font-weight: 500; }
.detail-table .row--refund td { background: #fff8f8; }

/* Detail fade transition */
.detail-fade-enter-active { transition: opacity 0.2s, transform 0.2s; }
.detail-fade-leave-active { transition: opacity 0.15s; }
.detail-fade-enter-from { opacity: 0; transform: translateY(-6px); }
.detail-fade-leave-to { opacity: 0; }
</style>
