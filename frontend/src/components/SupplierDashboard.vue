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
import { fetchAvailableMonths, fetchSupplierDashboard } from '../api/purchase_orders.js'

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, LegendScrollComponent])

const router = useRouter()

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
        itemStyle: { color: '#409eff' },
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
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: var(--text, #1a1a1a);
}

.btn-back {
  padding: 7px 16px;
  background: #fff;
  color: #409eff;
  border: 1px solid #409eff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
  transition: background 0.15s;
}

.btn-back:hover {
  background: #ecf5ff;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 20px;
  font-size: 14px;
  flex-wrap: wrap;
}

.store-filter {
  display: inline-flex;
  gap: 4px;
}
.store-filter button {
  padding: 4px 12px;
  border: 1px solid var(--border, #ddd);
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.store-filter button.active {
  background: #000;
  color: #fff;
  border-color: #000;
}

.month-select {
  margin-left: 6px;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  font-size: 14px;
  background: #fff;
  cursor: pointer;
}

.chart-block {
  margin-bottom: 32px;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px;
}

.chart3-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.filter-label {
  font-size: 13px;
  color: #555;
  line-height: 28px;
  white-space: nowrap;
}

.btn-filter-action {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #f9fafb;
  cursor: pointer;
  color: #374151;
  transition: background 0.15s;
}

.btn-filter-action:hover {
  background: #e5e7eb;
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
  color: #374151;
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
  color: #888;
}

.error-msg {
  text-align: center;
  padding: 40px;
  font-size: 14px;
  color: #991b1b;
  background: #fee2e2;
  border-radius: 8px;
}


</style>
