<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchAvailableMonths,
  fetchSupplierSummary,
  fetchSupplierDetail,
} from '../api/purchase_orders.js'

const router = useRouter()

// ── State refs ──────────────────────────────────────────────────────────────
const availableMonths = ref([])
const selectedMonthKey = ref('')   // "YYYY-MM" string used as select value
const summaryItems = ref([])
const monthTotal = ref(0)
const selectedSeller = ref(null)
const detailItems = ref([])
const detailTotal = ref(0)
const detailPage = ref(1)
const loading = ref(false)
const storeFilter = ref(null)  // null = 全部, 1 = 店铺1, 2 = 店铺2

const PAGE_SIZE = 20

// ── Computed ─────────────────────────────────────────────────────────────────
const totalDetailPages = computed(() =>
  detailTotal.value > 0 ? Math.ceil(detailTotal.value / PAGE_SIZE) : 1
)

const totalOrderCount = computed(() =>
  summaryItems.value.reduce((s, i) => s + i.order_count, 0)
)

function fmtAmount(val) {
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatMonth(m) {
  return `${m.year}-${String(m.month).padStart(2, '0')}`
}

function getSelectedYearMonth() {
  if (!selectedMonthKey.value) return null
  const parts = selectedMonthKey.value.split('-')
  return { year: parseInt(parts[0], 10), month: parseInt(parts[1], 10) }
}

function formatDate(dt) {
  if (!dt) return '-'
  try {
    return new Date(dt).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return String(dt)
  }
}

// ── Summary ───────────────────────────────────────────────────────────────────
async function loadSummary() {
  const ym = getSelectedYearMonth()
  if (!ym) return
  loading.value = true
  try {
    const data = await fetchSupplierSummary(ym.year, ym.month, storeFilter.value)
    summaryItems.value = data.items
    monthTotal.value = data.month_total ?? 0
  } catch {
    summaryItems.value = []
    monthTotal.value = 0
  } finally {
    loading.value = false
  }
}

// ── Detail ────────────────────────────────────────────────────────────────────
async function loadDetail() {
  const ym = getSelectedYearMonth()
  if (!selectedSeller.value || !ym) return
  try {
    const data = await fetchSupplierDetail(
      selectedSeller.value,
      ym.year,
      ym.month,
      detailPage.value,
    )
    detailItems.value = data.items
    detailTotal.value = data.total
  } catch {
    detailItems.value = []
    detailTotal.value = 0
  }
}

function toggleSeller(sellerName) {
  if (selectedSeller.value === sellerName) {
    selectedSeller.value = null
  } else {
    selectedSeller.value = sellerName
    detailPage.value = 1
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    availableMonths.value = await fetchAvailableMonths()
    const now = new Date()
    const curKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    const found = availableMonths.value.find(m => formatMonth(m) === curKey)
    selectedMonthKey.value = found
      ? formatMonth(found)
      : availableMonths.value[0]
        ? formatMonth(availableMonths.value[0])
        : ''
  } catch {
    availableMonths.value = []
  }
})

// When month changes: reset selection and reload summary
watch(selectedMonthKey, () => {
  selectedSeller.value = null
  detailPage.value = 1
  detailItems.value = []
  detailTotal.value = 0
  loadSummary()
})

// When selected seller or page changes: reload detail
watch([selectedSeller, detailPage], ([seller]) => {
  if (seller) {
    loadDetail()
  } else {
    detailItems.value = []
    detailTotal.value = 0
  }
})
</script>

<template>
  <div class="supplier-mgmt">

    <!-- ── Page header ─────────────────────────────────────────────────────── -->
    <div class="page-header">
      <div class="page-header__left">
        <h1 class="page-title">供应商采购汇总</h1>
        <p class="page-subtitle">按月统计各供应商实付金额与订单数（已排除待付款、退款中、交易关闭订单）</p>
      </div>
      <button @click="router.push('/suppliers/dashboard')" class="btn-chart">
        📊 趋势图表
      </button>
      <button @click="router.push('/suppliers/evaluation')" class="btn-eval">
        🏅 供应商评估
      </button>
    </div>

    <!-- ── Filter bar ──────────────────────────────────────────────────────── -->
    <div class="filter-bar">
      <div class="store-tabs">
        <button :class="['tab', { active: storeFilter === null }]" @click="storeFilter = null; loadSummary()">全部</button>
        <button :class="['tab', { active: storeFilter === 1 }]"    @click="storeFilter = 1; loadSummary()">店铺1</button>
        <button :class="['tab', { active: storeFilter === 2 }]"    @click="storeFilter = 2; loadSummary()">店铺2</button>
      </div>
      <div class="month-picker">
        <span class="picker-label">月份</span>
        <select v-model="selectedMonthKey" class="month-select">
          <option value="">-- 选择月份 --</option>
          <option v-for="m in availableMonths" :key="formatMonth(m)" :value="formatMonth(m)">
            {{ formatMonth(m) }}
          </option>
        </select>
      </div>
    </div>

    <!-- ── KPI cards ───────────────────────────────────────────────────────── -->
    <div v-if="!loading && summaryItems.length > 0" class="kpi-row">
      <div class="kpi-card kpi-card--primary">
        <div class="kpi-label">本月采购总额</div>
        <div class="kpi-value">¥ {{ fmtAmount(monthTotal) }}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">供应商数</div>
        <div class="kpi-value">{{ summaryItems.length }} <span class="kpi-unit">家</span></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">采购订单总数</div>
        <div class="kpi-value">{{ totalOrderCount }} <span class="kpi-unit">单</span></div>
      </div>
    </div>

    <!-- ── States ─────────────────────────────────────────────────────────── -->
    <div v-if="loading && summaryItems.length === 0" class="sm-empty">
      <span class="loading-spinner"></span> 加载中…
    </div>
    <div v-else-if="!loading && summaryItems.length === 0" class="sm-empty">暂无数据</div>

    <!-- ── Main table ──────────────────────────────────────────────────────── -->
    <section v-else class="sm-section">
      <table class="sm-table">
        <thead>
          <tr>
            <th class="col-rank">#</th>
            <th>供应商名称</th>
            <th class="col-num">订单数</th>
            <th class="col-num">实付合计（元）</th>
            <th class="col-share">占比</th>
            <th class="col-goods">本月最多采购货品</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(item, idx) in summaryItems" :key="item.seller_name">
            <!-- Summary row -->
            <tr
              class="sm-row sm-row--clickable"
              :class="{ 'sm-row--selected': selectedSeller === item.seller_name }"
              @click="toggleSeller(item.seller_name)"
            >
              <td class="col-rank">
                <span :class="['rank-badge', idx < 3 ? `rank-top${idx+1}` : '']">{{ idx + 1 }}</span>
              </td>
              <td class="col-name">
                <span class="seller-name">{{ item.seller_name }}</span>
                <span v-if="selectedSeller === item.seller_name" class="expand-hint">▲ 收起</span>
                <span v-else class="expand-hint">▼ 展开订单</span>
              </td>
              <td class="col-num">{{ item.order_count }}</td>
              <td class="col-num col-amount">¥ {{ fmtAmount(item.total_paid) }}</td>
              <td class="col-share">
                <div class="share-bar-wrap">
                  <div
                    class="share-bar"
                    :style="{ width: monthTotal > 0 ? (item.total_paid / monthTotal * 100).toFixed(1) + '%' : '0%' }"
                  ></div>
                  <span class="share-pct">{{ monthTotal > 0 ? (item.total_paid / monthTotal * 100).toFixed(1) : '0' }}%</span>
                </div>
              </td>
              <td class="col-goods">
                <span class="goods-text" :title="item.top_goods || ''">{{ item.top_goods || '-' }}</span>
              </td>
            </tr>

            <!-- Inline detail panel -->
            <tr v-if="selectedSeller === item.seller_name" class="sm-detail-row">
              <td colspan="6" class="sm-detail-cell">
                <div class="sm-detail-panel">
                  <div class="detail-header">
                    <span class="detail-title">{{ item.seller_name }} — 本月订单明细</span>
                    <span v-if="detailTotal > 0" class="detail-count">共 {{ detailTotal }} 笔订单</span>
                  </div>
                  <div v-if="detailItems.length === 0" class="sm-empty">暂无有效订单</div>
                  <table v-else class="sm-table sm-table--inner">
                    <thead>
                      <tr>
                        <th>订单编号</th>
                        <th>货品标题</th>
                        <th class="col-num">实付款（元）</th>
                        <th>订单状态</th>
                        <th>订单创建时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="d in detailItems" :key="d.order_id">
                        <td class="col-mono">{{ d.order_id }}</td>
                        <td>{{ d.goods_title || '-' }}</td>
                        <td class="col-num">¥ {{ fmtAmount(d.paid_amount) }}</td>
                        <td>
                          <span :class="['status-badge', `status-${d.status}`]">{{ d.status }}</span>
                        </td>
                        <td class="col-date">{{ formatDate(d.created_at) }}</td>
                      </tr>
                    </tbody>
                  </table>

                  <!-- Pagination -->
                  <div v-if="detailTotal > PAGE_SIZE" class="sm-pagination">
                    <button class="page-btn" :disabled="detailPage <= 1" @click.stop="detailPage--">‹ 上一页</button>
                    <span class="page-info">{{ detailPage }} / {{ totalDetailPages }} 页</span>
                    <button class="page-btn" :disabled="detailPage >= totalDetailPages" @click.stop="detailPage++">下一页 ›</button>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </section>

  </div>
</template>

<style scoped>
/* ── Layout ─────────────────────────────────────────────────────────────── */
.supplier-mgmt {
  max-width: 1200px;
  margin: 0 auto;
  padding: 28px 24px;
  background: var(--bg);
  min-height: 100vh;
}

/* ── Page header ─────────────────────────────────────────────────────────── */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 20px;
}
.page-header__left { flex: 1; }
.page-title {
  font-size: 28px;
  font-weight: 300;
  color: var(--text);
  margin: 0 0 4px;
  letter-spacing: -0.5px;
}
.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.btn-chart {
  flex-shrink: 0;
  padding: 8px 20px;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 9999px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  box-shadow: var(--shadow-soft);
  transition: background 0.15s;
  white-space: nowrap;
}
.btn-chart:hover { background: var(--bg-subtle); }

.btn-eval {
  flex-shrink: 0;
  padding: 8px 20px;
  background: rgba(245, 242, 239, 0.9);
  color: #000;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 9999px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  box-shadow: rgba(78, 50, 23, 0.08) 0px 4px 12px;
  transition: background 0.15s, box-shadow 0.15s;
  white-space: nowrap;
}
.btn-eval:hover {
  background: rgba(238, 233, 228, 0.95);
  box-shadow: rgba(78, 50, 23, 0.12) 0px 6px 16px;
}

/* ── Filter bar ──────────────────────────────────────────────────────────── */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  padding: 12px 16px;
  box-shadow: var(--shadow-soft);
}

.store-tabs {
  display: flex;
  gap: 4px;
}
.tab {
  padding: 5px 12px;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 9999px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  box-shadow: var(--shadow-soft);
  transition: all 0.15s;
}
.tab:hover:not(.active) { background: var(--bg-subtle); color: var(--text); }
.tab.active { background: #000; color: #fff; border-color: #000; box-shadow: var(--shadow-card); }

.month-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.picker-label { font-size: 13px; color: var(--text-muted); white-space: nowrap; }
.month-select {
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  font-size: 13px;
  background: var(--surface);
  cursor: pointer;
  color: var(--text);
  box-shadow: var(--shadow-inset);
  outline: none;
}

/* ── KPI cards ───────────────────────────────────────────────────────────── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.kpi-card {
  background: var(--surface);
  border-radius: 16px;
  padding: 16px 20px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.kpi-card--primary {
  box-shadow: var(--shadow-card);
}
.kpi-label { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.12px; }
.kpi-value { font-size: 24px; font-weight: 300; color: var(--text); letter-spacing: -0.3px; }
.kpi-card--primary .kpi-value { color: var(--text); }
.kpi-unit { font-size: 14px; font-weight: 400; color: var(--text-muted); }

/* ── Section / Table container ───────────────────────────────────────────── */
.sm-section {
  background: var(--surface);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}

.sm-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.sm-table th {
  text-align: left;
  padding: 11px 14px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  font-weight: 500;
  color: var(--text-muted);
  white-space: nowrap;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12px;
}
.sm-table td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
  color: var(--text-secondary);
}

/* ── Rank ─────────────────────────────────────────────────────────────────── */
.col-rank { width: 44px; text-align: center; }
.rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
}
.rank-top1 { background: #fbbf24; color: #78350f; }
.rank-top2 { background: #9ca3af; color: #1f2937; }
.rank-top3 { background: #cd7f32; color: #fff; }

/* ── Supplier name cell ──────────────────────────────────────────────────── */
.col-name { min-width: 140px; }
.seller-name { font-weight: 500; color: var(--text); display: block; }
.expand-hint { font-size: 11px; color: var(--text-muted); margin-top: 2px; display: block; }

/* ── Numbers ─────────────────────────────────────────────────────────────── */
.col-num { text-align: right; white-space: nowrap; }
.col-amount { font-weight: 500; color: var(--text); }

/* ── Share bar ────────────────────────────────────────────────────────────── */
.col-share { width: 140px; }
.share-bar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}
.share-bar {
  height: 6px;
  background: var(--text);
  border-radius: 3px;
  min-width: 2px;
  flex-shrink: 0;
}
.share-pct { font-size: 12px; color: var(--text-muted); white-space: nowrap; }

/* ── Goods column ─────────────────────────────────────────────────────────── */
.col-goods { max-width: 260px; }
.goods-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.4;
}

/* ── Row states ───────────────────────────────────────────────────────────── */
.sm-row--clickable { cursor: pointer; transition: background 0.1s; }
.sm-row--clickable:hover { background: var(--bg-subtle); }
.sm-row--selected { background: var(--bg-subtle) !important; }
.sm-row--selected:hover { background: rgba(245,242,239,0.6) !important; }

/* ── Detail panel ─────────────────────────────────────────────────────────── */
.sm-detail-row > .sm-detail-cell { padding: 0; }
.sm-detail-panel {
  padding: 16px 24px 20px;
  background: var(--bg-subtle);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border-subtle);
}
.detail-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.detail-title { font-size: 14px; font-weight: 500; color: var(--text); }
.detail-count { font-size: 12px; color: var(--text-muted); }

.sm-table--inner { background: var(--surface); border-radius: 8px; overflow: hidden; border: 1px solid var(--border-subtle); }
.sm-table--inner th { background: var(--bg-subtle); }
.sm-table--inner td:last-child { border-bottom: none; }

/* ── Status badge ─────────────────────────────────────────────────────────── */
.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 500;
  background: var(--bg);
  color: var(--text-muted);
}
.status-交易成功, .status-已完成 { background: #dcfce7; color: #166534; }
.status-付款成功 { background: var(--bg-subtle); color: var(--text-secondary); }
.status-退款成功 { background: #fee2e2; color: #991b1b; }

/* ── Misc ─────────────────────────────────────────────────────────────────── */
.col-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; color: var(--text-muted); }
.col-date { font-size: 13px; color: var(--text-muted); white-space: nowrap; }

.sm-pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}
.page-btn {
  padding: 5px 14px;
  border-radius: 9999px;
  border: 1px solid var(--border);
  background: var(--surface);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
  color: var(--text);
  box-shadow: var(--shadow-soft);
}
.page-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.page-btn:not(:disabled):hover { background: var(--bg-subtle); }
.page-info { font-size: 13px; color: var(--text-muted); }

.sm-empty {
  padding: 48px 0;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
}
.loading-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--text);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  margin-right: 6px;
  vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
