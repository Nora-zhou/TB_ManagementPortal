<script setup>
import { ref, onMounted, watch } from 'vue'
import {
  fetchSKUList,
  fetchSKUCosts,
  saveSKUCosts,
  fetchSKUCostSuggest,
  fetchProfitSummary,
  fetchProfitMonthly,
} from '../api/products.js'

const props = defineProps({ productId: { type: Number, required: true } })

// ── Profit summary ──
const summary = ref(null)
const loadingSummary = ref(false)
const summaryError = ref(null)

// ── Monthly data ──
const monthly = ref([])
const loadingMonthly = ref(false)

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
    const data = await fetchProfitMonthly(props.productId)
    monthly.value = (data.months || []).slice(-12)
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
  return Math.round((Math.abs(value ?? 0) / maxAbsProfit()) * 80)
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

watch(() => props.productId, loadAll)
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
          <h4 class="subsection-title">月度毛利走势（近 12 个月）</h4>
          <div v-if="loadingMonthly" class="muted">加载中…</div>
          <div v-else-if="monthly.length === 0" class="muted">暂无月度数据</div>
          <div v-else class="bar-chart">
            <div
              v-for="m in monthly"
              :key="m.month"
              class="bar-col"
            >
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

.section-title    { font-size: 17px; font-weight: 700; margin: 0 0 4px; color: var(--text); }
.subsection-title { font-size: 14px; font-weight: 600; margin: 0 0 10px; color: var(--text-muted); }

.muted     { font-size: 13.5px; color: var(--text-muted); }
.error-msg { font-size: 13.5px; color: #e74c3c; }
.save-msg  { font-size: 13px; color: #27ae60; }
.save-error { font-size: 13px; color: #e74c3c; }

/* SKU table */
.sku-table { width: 100%; border-collapse: collapse; font-size: 13.5px; margin-bottom: 10px; }
.sku-table th { text-align: left; padding: 5px 10px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border-subtle); }
.sku-table td { padding: 5px 10px; border-top: 1px solid var(--border-subtle); }

.cost-input { padding: 4px 8px; border: 1px solid var(--border-subtle); border-radius: 6px; font-size: 13.5px; width: 110px; }
.cost-input--error { border-color: #e74c3c; }
.inline-error { color: #e74c3c; font-size: 12px; margin-left: 6px; }

.cost-actions { display: flex; align-items: center; gap: 8px; }
.spacer { flex: 1; }

/* Buttons */
.btn { padding: 5px 12px; border-radius: 7px; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid var(--border-subtle); background: var(--bg-subtle, #f5f5f5); color: var(--text); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #000; color: #fff; border-color: #000; }
.btn-primary:hover:not(:disabled) { background: #222; }
.btn-suggest { background: #f0f6ff; border-color: #b3d0ff; color: #1a6fd4; }

/* Notice */
.notice { font-size: 13px; padding: 8px 12px; border-radius: 7px; }
.notice--info { background: #e8f4fd; color: #1565c0; border: 1px solid #90caf9; }

/* KPI grid */
.kpi-grid { display: flex; flex-wrap: wrap; gap: 12px; }
.kpi-card { background: var(--bg-subtle, #f8f8f8); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 14px 18px; min-width: 110px; }
.kpi-label { font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
.kpi-value { font-size: 18px; font-weight: 700; color: var(--text); }
.kpi--red    { color: #e74c3c !important; }
.kpi--orange { color: #e67e22 !important; }
.kpi--green  { color: #27ae60 !important; }

/* Bar chart */
.bar-chart { display: flex; gap: 6px; align-items: flex-end; overflow-x: auto; padding-bottom: 4px; }
.bar-col   { display: flex; flex-direction: column; align-items: center; min-width: 32px; }
.bar-wrap  { height: 90px; display: flex; align-items: flex-end; }
.bar       { width: 24px; border-radius: 3px 3px 0 0; min-height: 2px; transition: height 0.2s; }
.bar-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; white-space: nowrap; }
</style>
