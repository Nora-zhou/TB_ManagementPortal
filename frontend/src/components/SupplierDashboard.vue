<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  LegendScrollComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { fetchAvailableMonths, fetchSupplierDashboard, fetchRefundOrdersBySeller } from '../api/purchase_orders.js'

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, LegendScrollComponent])

const router = useRouter()

// ── Return rate expand state ──────────────────────────────────────────────
const expandedSeller = ref(null)
const expandedOrders = ref([])
const expandLoading = ref(false)

async function toggleSellerExpand(sellerName) {
  if (expandedSeller.value === sellerName) {
    expandedSeller.value = null
    expandedOrders.value = []
    return
  }
  expandedSeller.value = sellerName
  expandedOrders.value = []
  expandLoading.value = true
  try {
    expandedOrders.value = await fetchRefundOrdersBySeller(sellerName, {
      startMonth: startMonth.value || undefined,
      endMonth: endMonth.value || undefined,
      store: storeFilter.value ?? undefined,
    })
  } catch {
    expandedOrders.value = []
  } finally {
    expandLoading.value = false
  }
}

const availableMonths = ref([])
const startMonth = ref('')
const endMonth = ref('')
const loading = ref(false)
const error = ref(null)
const dashData = ref(null)
const storeFilter = ref(null)  // null = 全部, 1 = 店铺1, 2 = 店铺2

const chart1Option = ref({})
const chart2Option = ref({})
const chart3Option = ref({})

// Chart 3 supplier multi-select
const allSupplierNames = ref([])
const selectedSuppliers = ref([])

function monthKey(m) {
  return `${m.year}-${String(m.month).padStart(2, '0')}`
}

async function loadMonths() {
  try {
    const months = await fetchAvailableMonths()
    availableMonths.value = [...months].sort((a, b) => {
      const ka = monthKey(a)
      const kb = monthKey(b)
      return ka < kb ? -1 : ka > kb ? 1 : 0
    })
  } catch {
    availableMonths.value = []
  }
}

function buildChart2() {
  const data = dashData.value
  if (!data || !data.top_suppliers || data.top_suppliers.length === 0) {
    chart2Option.value = {}
    return
  }
  const { top_suppliers, months, monthly_data } = data
  const filtered = selectedSuppliers.value.length > 0
    ? top_suppliers.filter(s => selectedSuppliers.value.includes(s.seller_name))
    : top_suppliers
  const series2 = filtered.map(supplier => {
    const md = monthly_data.find(d => d.seller_name === supplier.seller_name)
    return {
      name: supplier.seller_name,
      type: 'line',
      smooth: true,
      data: months.map(m => (md ? (md.monthly_orders[m] ?? 0) : 0)),
      emphasis: { focus: 'series' },
    }
  })
  chart2Option.value = {
    title: { text: '按月订单单量趋势', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        const month = params[0].axisValue
        let html = `<b>${month}</b><br/>`
        for (const p of params) {
          html += `${p.marker}${p.seriesName}：${p.value} 单<br/>`
        }
        return html
      },
    },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: '2%', right: '4%', bottom: '15%', containLabel: true },
    xAxis: { type: 'category', data: months, boundaryGap: false },
    yAxis: { type: 'value', name: '订单数' },
    series: series2,
  }
}

function buildChart3() {
  const data = dashData.value
  if (!data || !data.top_suppliers || data.top_suppliers.length === 0) {
    chart3Option.value = {}
    return
  }
  const { top_suppliers, months, monthly_data } = data
  const filtered = selectedSuppliers.value.length > 0
    ? top_suppliers.filter(s => selectedSuppliers.value.includes(s.seller_name))
    : top_suppliers
  const series3 = filtered.map(supplier => {
    const md = monthly_data.find(d => d.seller_name === supplier.seller_name)
    return {
      name: supplier.seller_name,
      type: 'line',
      smooth: true,
      data: months.map(m => (md ? (md.monthly_amounts[m] ?? 0) : 0)),
      emphasis: { focus: 'series' },
    }
  })
  chart3Option.value = {
    title: { text: '按月采购金额趋势', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        const month = params[0].axisValue
        let html = `<b>${month}</b><br/>`
        for (const p of params) {
          html += `${p.marker}${p.seriesName}：¥${Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}<br/>`
        }
        return html
      },
    },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: '2%', right: '4%', bottom: '15%', containLabel: true },
    xAxis: { type: 'category', data: months, boundaryGap: false },
    yAxis: { type: 'value', name: '金额（元）' },
    series: series3,
  }
}

function toggleSupplier(name) {
  const idx = selectedSuppliers.value.indexOf(name)
  if (idx === -1) selectedSuppliers.value.push(name)
  else selectedSuppliers.value.splice(idx, 1)
  buildChart2()
  buildChart3()
}

function selectAllSuppliers() {
  selectedSuppliers.value = [...allSupplierNames.value]
  buildChart2()
  buildChart3()
}

function clearAllSuppliers() {
  selectedSuppliers.value = []
  buildChart2()
  buildChart3()
}

function buildCharts() {
  const data = dashData.value
  if (!data || !data.top_suppliers || data.top_suppliers.length === 0) {
    chart1Option.value = {}
    chart2Option.value = {}
    chart3Option.value = {}
    return
  }

  const { top_suppliers, months, monthly_data } = data

  // Init supplier list for chart 3 filter (reset on data reload)
  allSupplierNames.value = top_suppliers.map(s => s.seller_name)
  selectedSuppliers.value = [...allSupplierNames.value]

  // Chart 1: Horizontal bar — Top N suppliers by total paid amount
  const sortedSuppliers = [...top_suppliers].sort((a, b) => a.total_amount - b.total_amount)
  chart1Option.value = {
    title: { text: 'Top 供应商历史总采购金额', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const p = params[0]
        return `${p.name}<br/>金额：¥${Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
      },
    },
    grid: { left: '2%', right: '8%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', name: '金额（元）' },
    yAxis: {
      type: 'category',
      data: sortedSuppliers.map(s => s.seller_name),
      axisLabel: {
        overflow: 'truncate',
        width: 120,
      },
    },
    series: [
      {
        type: 'bar',
        data: sortedSuppliers.map(s => s.total_amount),
        label: { show: false },
        itemStyle: { color: '#0ea5e9' },
      },
    ],
  }

  // Chart 2 & 3: Line charts filtered by selectedSuppliers
  buildChart2()
  buildChart3()
}

async function loadDashboard() {
  loading.value = true
  error.value = null
  try {
    dashData.value = await fetchSupplierDashboard({
      topN: 15,
      startMonth: startMonth.value || undefined,
      endMonth: endMonth.value || undefined,
      store: storeFilter.value ?? undefined,
    })
    buildCharts()
  } catch (e) {
    error.value = e?.detail || '加载失败，请稍后重试'
    chart1Option.value = {}
    chart2Option.value = {}
    chart3Option.value = {}
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadMonths()
  await loadDashboard()
})
</script>

<template>
  <div class="supplier-dashboard">
    <div class="dashboard-header">
      <button class="btn-back" @click="router.push('/suppliers')">← 返回供应商列表</button>
      <h2 class="dashboard-title">供应商采购分析仪表盘</h2>
    </div>

    <div class="filter-row">
      <label>开始月份：
        <select v-model="startMonth" @change="loadDashboard" class="month-select">
          <option value="">不限</option>
          <option v-for="m in availableMonths" :key="monthKey(m)" :value="monthKey(m)">
            {{ monthKey(m) }}
          </option>
        </select>
      </label>
      <label>结束月份：
        <select v-model="endMonth" @change="loadDashboard" class="month-select">
          <option value="">不限</option>
          <option v-for="m in availableMonths" :key="monthKey(m)" :value="monthKey(m)">
            {{ monthKey(m) }}
          </option>
        </select>
      </label>
      <div class="store-filter">
        <button :class="{ active: storeFilter === null }" @click="storeFilter = null; loadDashboard()">全部</button>
        <button :class="{ active: storeFilter === 1 }"    @click="storeFilter = 1; loadDashboard()">店铺1</button>
        <button :class="{ active: storeFilter === 2 }"    @click="storeFilter = 2; loadDashboard()">店铺2</button>
      </div>
    </div>

    <div v-if="loading" class="status-msg">加载中…</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>
    <div v-else-if="!dashData || !dashData.top_suppliers || dashData.top_suppliers.length === 0" class="status-msg">
      暂无数据
    </div>

    <template v-else>
      <div class="chart-block">
        <v-chart :option="chart1Option" autoresize style="height: 420px; width: 100%;" />
      </div>
      <div class="chart-block">
        <div class="chart3-filter">
          <span class="filter-label">供应商筛选：</span>
          <button class="btn-filter-action" @click="selectAllSuppliers">全选</button>
          <button class="btn-filter-action" @click="clearAllSuppliers">清空</button>
          <div class="supplier-checkboxes">
            <label
              v-for="name in allSupplierNames"
              :key="name"
              class="supplier-checkbox-item"
            >
              <input
                type="checkbox"
                :checked="selectedSuppliers.includes(name)"
                @change="toggleSupplier(name)"
              />
              <span>{{ name }}</span>
            </label>
          </div>
        </div>
        <v-chart :option="chart3Option" autoresize style="height: 440px; width: 100%;" />
      </div>
      <div class="chart-block">
        <v-chart :option="chart2Option" autoresize style="height: 440px; width: 100%;" />
      </div>

      <!-- Return rate top 15 -->
      <div class="chart-block" v-if="dashData.return_rate_suppliers && dashData.return_rate_suppliers.length">
        <h3 class="section-title">退款率 Top {{ dashData.return_rate_suppliers.length }}（退款单数 / 总单数，至少 3 单）</h3>
        <table class="rr-table">
          <thead>
            <tr>
              <th>#</th>
              <th>供应商名称</th>
              <th>退款率</th>
              <th>退款单数 / 总单数</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(s, i) in dashData.return_rate_suppliers" :key="s.seller_name">
              <tr class="rr-row" @click="toggleSellerExpand(s.seller_name)">
                <td class="rr-rank">{{ i + 1 }}</td>
                <td class="rr-name">
                  <span class="rr-toggle">{{ expandedSeller === s.seller_name ? '▾' : '▸' }}</span>
                  {{ s.seller_name }}
                </td>
                <td class="rr-rate" :class="s.return_rate >= 20 ? 'rr-high' : s.return_rate >= 10 ? 'rr-mid' : ''">
                  {{ s.return_rate.toFixed(1) }}%
                </td>
                <td class="rr-counts">{{ s.return_count }} / {{ s.total_count }}</td>
              </tr>
              <tr v-if="expandedSeller === s.seller_name" class="rr-detail-row">
                <td colspan="4" class="rr-detail-cell">
                  <div v-if="expandLoading" class="rr-detail-loading">加载中…</div>
                  <div v-else-if="expandedOrders.length === 0" class="rr-detail-empty">暂无退款订单</div>
                  <table v-else class="rr-detail-table">
                    <thead>
                      <tr>
                        <th>订单编号</th>
                        <th>商品名称</th>
                        <th>状态</th>
                        <th>金额（元）</th>
                        <th>下单日期</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="o in expandedOrders" :key="o.order_id">
                        <td class="rr-d-id">{{ o.order_id }}</td>
                        <td class="rr-d-goods">{{ o.goods_title || '-' }}</td>
                        <td class="rr-d-status" :class="o.status === '交易成功' ? 'rr-d-success' : 'rr-d-refund'">{{ o.status }}</td>
                        <td class="rr-d-amount">¥{{ Number(o.paid_amount).toFixed(2) }}</td>
                        <td class="rr-d-date">{{ o.created_at || '-' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.supplier-dashboard {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}

.dashboard-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.dashboard-title {
  font-size: 28px;
  font-weight: 300;
  margin: 0;
  letter-spacing: -0.5px;
  color: var(--text);
}

.btn-back {
  padding: 6px 14px;
  background: var(--surface);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 9999px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  box-shadow: var(--shadow-soft);
  transition: background 0.15s, color 0.15s;
}

.btn-back:hover {
  background: var(--bg-subtle);
  color: var(--text);
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  font-size: 13px;
  flex-wrap: wrap;
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  padding: 10px 16px;
  box-shadow: var(--shadow-soft);
}

.store-filter {
  display: inline-flex;
  gap: 4px;
}
.store-filter button {
  padding: 5px 12px;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 9999px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  box-shadow: var(--shadow-soft);
  transition: all 0.15s;
}
.store-filter button:hover:not(.active) { background: var(--bg-subtle); color: var(--text); }
.store-filter button.active {
  background: #000;
  color: #fff;
  border-color: #000;
  box-shadow: var(--shadow-card);
}

.month-select {
  margin-left: 6px;
  padding: 5px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  font-size: 13px;
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  box-shadow: var(--shadow-inset);
  outline: none;
}

.chart-block {
  margin-bottom: 32px;
  background: var(--surface);
  border-radius: 16px;
  padding: 20px 24px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}

.section-title {
  font-size: 14px;
  font-weight: 500;
  text-align: center;
  margin: 0 0 16px;
  color: var(--text);
}
.rr-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.rr-table th {
  text-align: left;
  padding: 8px 12px;
  border-bottom: 2px solid var(--border);
  color: var(--text-secondary);
  font-weight: 500;
}
.rr-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text);
}
.rr-rank { color: var(--text-secondary); width: 36px; }
.rr-name { max-width: 320px; }
.rr-rate { font-weight: 600; }
.rr-high { color: #ef4444; }
.rr-mid  { color: #f97316; }
.rr-counts { color: var(--text-secondary); }
.rr-row { cursor: pointer; transition: background 0.12s; }
.rr-row:hover { background: var(--bg-subtle); }
.rr-toggle { display: inline-block; width: 14px; font-size: 11px; color: var(--text-muted); }
.rr-detail-row td { padding: 0; }
.rr-detail-cell { padding: 0 12px 12px 28px !important; background: var(--bg-subtle); }
.rr-detail-loading, .rr-detail-empty { padding: 10px 0; font-size: 13px; color: var(--text-secondary); }
.rr-detail-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px; }
.rr-detail-table th { padding: 6px 10px; border-bottom: 1px solid var(--border); color: var(--text-secondary); font-weight: 500; text-align: left; }
.rr-detail-table td { padding: 7px 10px; border-bottom: 1px solid var(--border-subtle); color: var(--text); }
.rr-d-id { color: var(--text-muted); font-size: 11px; max-width: 180px; word-break: break-all; }
.rr-d-goods { max-width: 280px; }
.rr-d-status { white-space: nowrap; }
.rr-d-success { color: #16a34a; font-weight: 500; }
.rr-d-refund  { color: #ef4444; font-weight: 500; }
.rr-d-amount { font-weight: 500; white-space: nowrap; }
.rr-d-date { white-space: nowrap; color: var(--text-secondary); }

.chart3-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.filter-label {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 28px;
  white-space: nowrap;
}

.btn-filter-action {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 9999px;
  background: var(--surface);
  cursor: pointer;
  color: var(--text-secondary);
  box-shadow: var(--shadow-soft);
  transition: background 0.15s;
}

.btn-filter-action:hover {
  background: var(--bg-subtle);
  color: var(--text);
}

.supplier-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.supplier-checkbox-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}

.supplier-checkbox-item input[type='checkbox'] {
  cursor: pointer;
}

.status-msg {
  text-align: center;
  padding: 40px;
  font-size: 14px;
  color: var(--text-muted);
}

.error-msg {
  text-align: center;
  padding: 16px;
  font-size: 13px;
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 10px;
}


</style>
