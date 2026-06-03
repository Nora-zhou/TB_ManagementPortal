<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, ToolboxComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { getOrderSummary, getOrderTrend, getTopProducts, getTopRefundProducts } from '../api/orders'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, ToolboxComponent])


// ----------------------------------------------------------------
// Time filter state
// ----------------------------------------------------------------
const filterMode = ref('days30')   // 'days7' | 'days30' | 'days90' | 'month' | 'custom'
const startDate = ref('')          // YYYY-MM-DD sent to backend
const endDate = ref('')            // YYYY-MM-DD sent to backend
const selectedMonth = ref('')      // YYYY-MM (month picker binding)
const customStart = ref('')
const customEnd = ref('')
const customError = ref('')

function padDate(d) {
  return d.toISOString().slice(0, 10)
}

function lastDayOfMonth(year, month) {
  return new Date(year, month, 0).getDate()
}

function computeDateRange() {
  const today = new Date()
  const todayStr = padDate(today)

  if (filterMode.value === 'days7') {
    const s = new Date(today); s.setDate(today.getDate() - 6)
    startDate.value = padDate(s)
    endDate.value = todayStr
  } else if (filterMode.value === 'days30') {
    const s = new Date(today); s.setDate(today.getDate() - 29)
    startDate.value = padDate(s)
    endDate.value = todayStr
  } else if (filterMode.value === 'days90') {
    const s = new Date(today); s.setDate(today.getDate() - 89)
    startDate.value = padDate(s)
    endDate.value = todayStr
  } else if (filterMode.value === 'month' && selectedMonth.value) {
    const [y, m] = selectedMonth.value.split('-').map(Number)
    startDate.value = `${selectedMonth.value}-01`
    endDate.value = `${selectedMonth.value}-${String(lastDayOfMonth(y, m)).padStart(2, '0')}`
  } else if (filterMode.value === 'custom') {
    startDate.value = customStart.value
    endDate.value = customEnd.value
  }
}

function setMode(mode) {
  filterMode.value = mode
  customError.value = ''
  computeDateRange()
  loadAll()
}

function onMonthChange() {
  filterMode.value = 'month'
  computeDateRange()
  loadAll()
}

function applyCustom() {
  customError.value = ''
  if (!customStart.value || !customEnd.value) return
  if (customStart.value > customEnd.value) {
    customError.value = '开始日期不能晚于结束日期'
    return
  }
  filterMode.value = 'custom'
  computeDateRange()
  loadAll()
}

function dateParams() {
  return { start_date: startDate.value, end_date: endDate.value }
}

// ----------------------------------------------------------------
// Store filter state
// ----------------------------------------------------------------
const storeFilter = ref(null)  // null = 全部, 1 = 店铺1, 2 = 店铺2

function setStore(val) {
  storeFilter.value = val
  loadAll()
}

function storeParams() {
  return storeFilter.value != null ? { store: storeFilter.value } : {}
}

// ----------------------------------------------------------------
// Summary
// ----------------------------------------------------------------
const summary = ref(null)
const summaryError = ref(null)

async function loadSummary() {
  summaryError.value = null
  try {
    summary.value = await getOrderSummary({ ...dateParams(), ...storeParams() })
  } catch (e) {
    summaryError.value = e.message
  }
}

// ----------------------------------------------------------------
// Trend
// ----------------------------------------------------------------
const trendGranularity = ref('month')
const trendOption = ref(null)
const trendError = ref(null)
const trendEmpty = ref(false)

async function loadTrend() {
  trendError.value = null
  trendEmpty.value = false
  try {
    const data = await getOrderTrend({ granularity: trendGranularity.value, ...dateParams(), ...storeParams() })
    if (!data.labels || data.labels.length === 0) {
      trendEmpty.value = true
      trendOption.value = null
    } else {
      trendOption.value = buildTrendOption(data)
    }
  } catch (e) {
    trendError.value = e.message
  }
}

// ----------------------------------------------------------------
// Top products
// ----------------------------------------------------------------
const topSortBy = ref('revenue')
const topItems = ref([])
const topError = ref(null)
const topEmpty = ref(false)

async function loadTop() {
  topError.value = null
  topEmpty.value = false
  try {
    const res = await getTopProducts({ sort_by: topSortBy.value, limit: 10, ...dateParams(), ...storeParams() })
    topItems.value = res.items
    topEmpty.value = res.items.length === 0
  } catch (e) {
    topError.value = e.message
  }
}

// ----------------------------------------------------------------
// Refund top products
// ----------------------------------------------------------------
const refundByCount = ref([])
const refundByRate = ref([])
const refundTopError = ref(null)
const refundTopEmpty = ref(false)

// Modal
const refundModal = ref({ open: false, type: 'count', page: 1, pageSize: 20 })
const refundModalSource = computed(() =>
  refundModal.value.type === 'count' ? refundByCount.value : refundByRate.value
)
const refundModalTotal = computed(() => refundModalSource.value.length)
const refundModalTotalPages = computed(() =>
  Math.max(1, Math.ceil(refundModalTotal.value / refundModal.value.pageSize))
)
const refundModalPageItems = computed(() => {
  const start = (refundModal.value.page - 1) * refundModal.value.pageSize
  return refundModalSource.value.slice(start, start + refundModal.value.pageSize)
})
function openRefundModal(type) {
  refundModal.value = { open: true, type, page: 1, pageSize: 20 }
}
function closeRefundModal() {
  refundModal.value.open = false
}

async function loadRefundTop() {
  refundTopError.value = null
  refundTopEmpty.value = false
  try {
    const res = await getTopRefundProducts({ limit: 500, ...dateParams(), ...storeParams() })
    refundByCount.value = res.by_count
    refundByRate.value = res.by_rate
    refundTopEmpty.value = res.by_count.length === 0 && res.by_rate.length === 0
  } catch (e) {
    refundTopError.value = e.message
  }
}

function loadAll() {
  loadSummary()
  loadTrend()
  loadTop()
  loadRefundTop()
}

watch(trendGranularity, loadTrend)
watch(topSortBy, loadTop)

onMounted(() => {
  computeDateRange()
  loadAll()
})

// ----------------------------------------------------------------
function buildTrendOption(data) {
  return {
    tooltip: { trigger: 'axis', formatter: (params) => {
      const label = params[0].axisValue
      return params.map(p =>
        `${p.marker}${p.seriesName}：¥${p.value.toFixed(2)}`
      ).join('<br>') + `<br><small>${label}</small>`
    }},
    legend: { data: ['销售额', '退款额'] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: data.labels, axisLabel: { rotate: data.labels.length > 15 ? 30 : 0 } },
    yAxis: { type: 'value', axisLabel: { formatter: '¥{value}' } },
    series: [
      {
        name: '销售额',
        type: 'line',
        smooth: true,
        data: data.revenue,
        itemStyle: { color: '#0ea5e9' },
        areaStyle: { opacity: 0.1 },
      },
      {
        name: '退款额',
        type: 'line',
        smooth: true,
        data: data.refund,
        itemStyle: { color: '#dc2626' },
        areaStyle: { opacity: 0.1 },
      },
    ],
  }
}

function pct(n, d) {
  return d > 0 ? (n / d * 100).toFixed(1) + '%' : '—'
}
</script>

<template>
  <div class="dashboard">
    <div class="toolbar">
      <!-- Row 1: title + store tabs -->
      <div class="toolbar-row toolbar-row--top">
        <h2>订单分析仪表盘</h2>
        <div class="store-filter">
          <button :class="{ active: storeFilter === null }" @click="setStore(null)">全部</button>
          <button :class="{ active: storeFilter === 1 }"    @click="setStore(1)">店铺1</button>
          <button :class="{ active: storeFilter === 2 }"    @click="setStore(2)">店铺2</button>
        </div>
      </div>

      <!-- Row 2: Time filter bar -->
      <div class="toolbar-row toolbar-row--filters">
      <button :class="{ active: filterMode === 'days7' }"  @click="setMode('days7')">近 7 天</button>
      <button :class="{ active: filterMode === 'days30' }" @click="setMode('days30')">近 30 天</button>
      <button :class="{ active: filterMode === 'days90' }" @click="setMode('days90')">近 90 天</button>
      <span class="filter-sep"></span>
      <label class="filter-month">
        按月份
        <input type="text" placeholder="YYYY-MM" maxlength="7" v-model="selectedMonth" @change="onMonthChange"
               class="month-input" :class="{ active: filterMode === 'month' }" />
      </label>
      <span class="filter-sep"></span>
      <span class="filter-custom" :class="{ active: filterMode === 'custom' }">
        自定义
        <input type="text" placeholder="YYYY-MM-DD" maxlength="10" class="date-input" v-model="customStart" />
        <span>~</span>
        <input type="text" placeholder="YYYY-MM-DD" maxlength="10" class="date-input" v-model="customEnd" />
        <button class="btn-apply" @click="applyCustom">确认</button>
      </span>
      <span v-if="customError" class="custom-error">{{ customError }}</span>
      </div>
    </div>

    <!-- Summary cards -->
    <div v-if="summary" class="cards">
      <div class="card">
        <div class="card-label">总销售额</div>
        <div class="card-value blue">¥{{ summary.total_revenue.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</div>
        <div class="card-sub">成功订单 {{ summary.success_orders }} 笔 / 共 {{ summary.total_orders }} 笔</div>
      </div>
      <div class="card">
        <div class="card-label">退款总额</div>
        <div class="card-value red">¥{{ summary.total_refund.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</div>
        <div class="card-sub">退款率 {{ (summary.refund_rate * 100).toFixed(1) }}%</div>
      </div>
      <div class="card">
        <div class="card-label">平均客单价</div>
        <div class="card-value green">¥{{ summary.avg_order_value.toFixed(2) }}</div>
        <div class="card-sub">仅计交易成功订单</div>
      </div>
      <div class="card">
        <div class="card-label">数据时间跨度</div>
        <div class="card-value gray date-range">{{ summary.date_min }} ~ {{ summary.date_max }}</div>
        <div class="card-sub">历史订单</div>
      </div>
    </div>
    <div v-if="summaryError" class="error-msg">⚠ 加载摘要失败：{{ summaryError }}</div>

    <!-- Trend chart -->
    <div class="section">
      <div class="section-header">
        <h3>销售 / 退款走势</h3>
        <div class="tab-group">
          <button :class="{ active: trendGranularity === 'day' }" @click="trendGranularity = 'day'">日</button>
          <button :class="{ active: trendGranularity === 'week' }" @click="trendGranularity = 'week'">周</button>
          <button :class="{ active: trendGranularity === 'month' }" @click="trendGranularity = 'month'">月</button>
        </div>
      </div>
      <div v-if="trendError" class="error-msg">⚠ {{ trendError }}</div>
      <v-chart v-else-if="trendOption" :option="trendOption" class="chart-trend" autoresize />
      <div v-else-if="trendEmpty" class="chart-placeholder empty">所选时间范围内暂无订单数据</div>
      <div v-else class="chart-placeholder">加载中…</div>
    </div>

    <!-- Top products -->
    <div class="section">
      <div class="section-header">
        <h3>热销商品排行 Top 10</h3>
        <div class="tab-group">
          <button :class="{ active: topSortBy === 'revenue' }" @click="topSortBy = 'revenue'">收入</button>
          <button :class="{ active: topSortBy === 'count' }" @click="topSortBy = 'count'">订单数</button>
        </div>
      </div>
      <div v-if="topError" class="error-msg">⚠ {{ topError }}</div>
      <table v-else-if="topItems.length" class="top-table">
        <thead>
          <tr>
            <th>#</th>
            <th>商品ID</th>
            <th>商品标题</th>
            <th>订单数</th>
            <th>销售额</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in topItems" :key="item.rank">
            <td class="rank">{{ item.rank }}</td>
            <td class="item-id"><router-link :to="'/products/' + item.taobao_item_id">{{ item.taobao_item_id }}</router-link></td>
            <td :title="item.product_title">{{ item.product_title.slice(0, 30) }}{{ item.product_title.length > 30 ? '…' : '' }}</td>
            <td class="num">{{ item.order_count }}</td>
            <td class="num">¥{{ item.total_revenue.toFixed(2) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="topEmpty" class="chart-placeholder empty">所选时间范围内暂无订单数据</div>
      <div v-else class="chart-placeholder">暂无数据</div>
    </div>

    <!-- Refund top products -->
    <div class="section-row">
      <!-- By refund count -->
      <div class="section half">
        <div class="section-header">
          <h3>退款数量 Top 10</h3>
          <button v-if="refundByCount.length > 10" class="btn-more" @click="openRefundModal('count')">更多</button>
        </div>
        <div v-if="refundTopError" class="error-msg">⚠ {{ refundTopError }}</div>
        <div v-else-if="refundTopEmpty" class="chart-placeholder empty">所选时间范围内暂无退款数据</div>
        <table v-else-if="refundByCount.length" class="top-table">
          <thead>
            <tr>
              <th>#</th><th>商品标题</th><th>退款次数</th><th>实付订单数</th><th>退款额</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in refundByCount.slice(0, 10)" :key="'c' + item.rank">
              <td class="rank">{{ item.rank }}</td>
              <td :title="item.product_title">{{ item.product_title.slice(0, 32) }}{{ item.product_title.length > 32 ? '…' : '' }}</td>
              <td class="num red">{{ item.refund_count }}</td>
              <td class="num">{{ item.total_orders }}</td>
              <td class="num red">¥{{ item.refund_amount.toFixed(2) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="chart-placeholder">加载中…</div>
      </div>

      <!-- By refund rate -->
      <div class="section half">
        <div class="section-header">
          <h3>退款率 Top 10</h3>
          <button v-if="refundByRate.length > 10" class="btn-more" @click="openRefundModal('rate')">更多</button>
        </div>
        <div v-if="refundTopError" class="error-msg">⚠ {{ refundTopError }}</div>
        <div v-else-if="refundTopEmpty" class="chart-placeholder empty">所选时间范围内暂无退款数据</div>
        <table v-else-if="refundByRate.length" class="top-table">
          <thead>
            <tr>
              <th>#</th><th>商品标题</th><th>退款率</th><th>退款次数</th><th>退款额</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in refundByRate.slice(0, 10)" :key="'r' + item.rank">
              <td class="rank">{{ item.rank }}</td>
              <td :title="item.product_title">{{ item.product_title.slice(0, 32) }}{{ item.product_title.length > 32 ? '…' : '' }}</td>
              <td class="num red">{{ item.refund_rate.toFixed(1) }}%</td>
              <td class="num">{{ item.refund_count }}</td>
              <td class="num red">¥{{ item.refund_amount.toFixed(2) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="chart-placeholder">加载中…</div>
      </div>
    </div>

    <!-- Refund modal -->
    <Teleport to="body">
      <div v-if="refundModal.open" class="modal-backdrop" @click.self="closeRefundModal">
        <div class="modal-card">
          <div class="modal-header">
            <h3>{{ refundModal.type === 'count' ? '退款数量' : '退款率' }} — 全部商品（共 {{ refundModalTotal }} 条）</h3>
            <button class="modal-close" @click="closeRefundModal">✕</button>
          </div>
          <div class="modal-body">
            <table class="top-table">
              <thead>
                <tr v-if="refundModal.type === 'count'">
                  <th>#</th><th>商品标题</th><th>退款次数</th><th>实付订单数</th><th>退款额</th>
                </tr>
                <tr v-else>
                  <th>#</th><th>商品标题</th><th>退款率</th><th>退款次数</th><th>退款额</th>
                </tr>
              </thead>
              <tbody v-if="refundModal.type === 'count'">
                <tr v-for="item in refundModalPageItems" :key="item.rank">
                  <td class="rank">{{ item.rank }}</td>
                  <td :title="item.product_title">{{ item.product_title.slice(0, 40) }}{{ item.product_title.length > 40 ? '…' : '' }}</td>
                  <td class="num red">{{ item.refund_count }}</td>
                  <td class="num">{{ item.total_orders }}</td>
                  <td class="num red">¥{{ item.refund_amount.toFixed(2) }}</td>
                </tr>
              </tbody>
              <tbody v-else>
                <tr v-for="item in refundModalPageItems" :key="item.rank">
                  <td class="rank">{{ item.rank }}</td>
                  <td :title="item.product_title">{{ item.product_title.slice(0, 40) }}{{ item.product_title.length > 40 ? '…' : '' }}</td>
                  <td class="num red">{{ item.refund_rate.toFixed(1) }}%</td>
                  <td class="num">{{ item.refund_count }}</td>
                  <td class="num red">¥{{ item.refund_amount.toFixed(2) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="modal-footer">
            <button class="modal-page-btn" :disabled="refundModal.page <= 1" @click="refundModal.page--">上一页</button>
            <span class="modal-page-info">第 {{ refundModal.page }} / {{ refundModalTotalPages }} 页</span>
            <button class="modal-page-btn" :disabled="refundModal.page >= refundModalTotalPages" @click="refundModal.page++">下一页</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.dashboard { padding: 0; }
h3 { margin: 0; font-size: 14px; font-weight: 500; letter-spacing: 0.14px; color: var(--text); }

/* Toolbar — same two-row pattern as ProductList */
.toolbar { flex-direction: column; gap: 10px; }
.toolbar-row--top { display: flex; align-items: center; gap: 12px; }
.store-filter { display: flex; gap: 4px; }
.store-filter button {
  padding: 5px 12px; border-radius: 9999px; font-size: 12px;
  background: var(--surface); color: var(--text-secondary);
  border: 1px solid var(--border); box-shadow: var(--shadow-soft);
  cursor: pointer; transition: all 0.15s;
}
.store-filter button:hover:not(.active) { background: var(--bg-subtle); color: var(--text); }
.store-filter button.active { background: #000; color: #fff; border-color: #000; box-shadow: var(--shadow-card); }

/* Row 2: time filter bar */
.toolbar-row--filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  padding: 10px 16px;
  box-shadow: var(--shadow-soft);
}
.toolbar-row--filters > button {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: 9999px;
  background: var(--surface);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  box-shadow: var(--shadow-soft);
  transition: all 0.15s;
}
.toolbar-row--filters > button:hover:not(.active) { color: var(--text); background: var(--bg-subtle); }
.toolbar-row--filters > button.active {
  background: #000; color: #fff; border-color: #000;
  box-shadow: var(--shadow-card);
}
.filter-sep { width: 1px; height: 18px; background: var(--border); margin: 0 4px; }
.filter-month {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
}
.filter-month .month-input {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 13px;
  background: var(--surface);
  color: var(--text);
  outline: none;
  box-shadow: var(--shadow-inset);
}
.filter-month input.active { border-color: rgba(0,0,0,0.3); }
.filter-custom {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-muted);
}
.filter-custom.active { color: var(--text); }
.filter-custom .date-input {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 13px;
  background: var(--surface);
  color: var(--text);
  outline: none;
  box-shadow: var(--shadow-inset);
}
.btn-apply {
  padding: 5px 14px;
  background: #000; color: #fff;
  border: none; border-radius: 9999px;
  cursor: pointer; font-size: 13px; font-weight: 500;
  box-shadow: var(--shadow-card);
  transition: background 0.15s;
}
.btn-apply:hover { background: #222; }
.custom-error { color: var(--danger); font-size: 12px; }


/* Cards */
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.card {
  background: var(--surface);
  border-radius: 16px;
  padding: 20px 24px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.card-label {
  font-size: 12px; font-weight: 500; letter-spacing: 0.12px;
  color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase;
}
.card-value { font-size: 26px; font-weight: 300; margin-bottom: 6px; letter-spacing: -0.3px; }
.card-sub { font-size: 12px; color: var(--text-muted); letter-spacing: 0.12px; }
.blue  { color: var(--info); }
.red   { color: var(--danger); }
.green { color: var(--success); }
.gray  { color: var(--text-secondary); }
.date-range { font-size: 16px; }

/* Sections */
.section {
  background: var(--surface);
  border-radius: 16px;
  padding: 20px 24px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.section-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.half { margin-bottom: 0; padding: 14px 14px; }
@media (max-width: 768px) { .section-row { grid-template-columns: 1fr; } }

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px;
}

.tab-group { display: flex; gap: 3px; }
.tab-group button {
  padding: 4px 12px;
  font-size: 12px; font-weight: 500;
  border: 1px solid var(--border);
  background: transparent;
  cursor: pointer;
  border-radius: 9999px;
  color: var(--text-muted);
  transition: all 0.15s;
}
.tab-group button:hover { color: var(--text); background: var(--bg-subtle); }
.tab-group button.active {
  background: #000; color: #fff; border-color: #000;
}

.chart-trend { height: 280px; }
.chart-pie { height: 260px; }
.chart-placeholder {
  height: 200px; display: flex; align-items: center;
  justify-content: center; color: var(--border);
  font-size: 13px;
}
.chart-placeholder.empty { color: var(--text-muted); }

.error-msg { color: var(--danger); font-size: 13px; margin: 8px 0; }

/* Top table */
.top-table {
  width: 100%; border-collapse: collapse;
  font-size: 13px; letter-spacing: 0.13px;
  margin-top: 8px;
}
.top-table th, .top-table td { padding: 8px 10px; border-bottom: 1px solid var(--border-subtle); }
.top-table th {
  font-size: 11px; font-weight: 500; letter-spacing: 0.11px;
  color: var(--text-muted); text-transform: uppercase;
}
.top-table tbody tr:last-child td { border-bottom: none; }
.rank { width: 2rem; text-align: center; color: var(--text-muted); font-weight: 500; font-size: 12px; }
.item-id { font-size: 12px; font-family: monospace; white-space: nowrap; }
.item-id a { color: var(--accent, #3b82f6); text-decoration: none; }
.item-id a:hover { text-decoration: underline; }
.num { text-align: right; font-variant-numeric: tabular-nums; color: var(--text); }
.num.red { color: var(--danger); }

.btn-more {
  padding: 3px 12px;
  font-size: 12px; font-weight: 500;
  border: 1px solid var(--border);
  border-radius: 9999px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}
.btn-more:hover { color: var(--text); background: var(--bg-subtle); }

/* Modal */
:global(.modal-backdrop) {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
:global(.modal-card) {
  background: var(--surface, #fff);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
  width: min(820px, 92vw);
  max-height: 80vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}
:global(.modal-header) {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle, #eee);
}
:global(.modal-header h3) {
  margin: 0; font-size: 14px; font-weight: 500; color: var(--text, #111);
}
:global(.modal-close) {
  background: none; border: none; cursor: pointer;
  font-size: 16px; color: var(--text-muted, #888);
  line-height: 1; padding: 2px 6px; border-radius: 6px;
  transition: background 0.15s;
}
:global(.modal-close:hover) { background: var(--bg-subtle, #f5f5f5); }
:global(.modal-body) {
  flex: 1; overflow-y: auto; padding: 0 20px;
}
:global(.modal-footer) {
  display: flex; align-items: center; justify-content: center; gap: 16px;
  padding: 12px 20px;
  border-top: 1px solid var(--border-subtle, #eee);
}
:global(.modal-page-btn) {
  padding: 5px 16px; font-size: 13px; font-weight: 500;
  border: 1px solid var(--border, #ddd); border-radius: 9999px;
  background: transparent; color: var(--text, #111);
  cursor: pointer; transition: all 0.15s;
}
:global(.modal-page-btn:disabled) { opacity: 0.35; cursor: not-allowed; }
:global(.modal-page-btn:not(:disabled):hover) { background: var(--bg-subtle, #f5f5f5); }
:global(.modal-page-info) { font-size: 13px; color: var(--text-muted, #888); }
</style>
