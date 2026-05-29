<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  LegendScrollComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { fetchProfitMonthly } from '../api/stats.js'

use([
  CanvasRenderer, BarChart, LineChart, PieChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent, LegendScrollComponent,
])

const MONTH_RE = /^\d{4}-\d{2}$/

const startMonth = ref('')
const endMonth   = ref('')
const loading    = ref(false)
const error      = ref(null)
const data       = ref(null)

async function loadData() {
  if (startMonth.value && !MONTH_RE.test(startMonth.value)) return
  if (endMonth.value   && !MONTH_RE.test(endMonth.value))   return

  loading.value = true
  error.value   = null
  try {
    data.value = await fetchProfitMonthly({
      startMonth: startMonth.value || undefined,
      endMonth:   endMonth.value   || undefined,
    })
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
watch([startMonth, endMonth], loadData)

const ZERO_KPI = {
  revenue_s1: 0, revenue_s2: 0, cost_s1: 0,    cost_s2: 0,
  refund_s1:  0, refund_s2:  0, profit_s1: 0,  profit_s2: 0,
  total_revenue: 0, total_cost: 0, total_refund: 0, total_profit: 0,
}

const kpi     = computed(() => data.value?.kpi ?? ZERO_KPI)
const hasData = computed(() => (data.value?.months?.length ?? 0) > 0)

function fmt(n) {
  return Number(n ?? 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

// ── Trend chart option ────────────────────────────────────────────────────
const trendOption = computed(() => {
  if (!data.value?.months?.length) return {}
  const { months, series: s } = data.value
  return {
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        const month = params[0].axisValue
        let html = `<b>${month}</b><br/>`
        params.forEach(p => {
          html += `${p.marker}${p.seriesName}：¥${Number(p.value ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}<br/>`
        })
        return html
      },
    },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: '3%', right: '8%', bottom: '15%', containLabel: true },
    xAxis: { type: 'category', data: months, boundaryGap: false },
    yAxis: [
      {
        name: '金额（元）',
        type: 'value',
        axisLabel: { formatter: v => `¥${(v / 1000).toFixed(0)}K` },
      },
      {
        name: '分店利润（元）',
        type: 'value',
        position: 'right',
        axisLabel: { formatter: v => `¥${(v / 1000).toFixed(0)}K` },
      },
    ],
    series: [
      { name: '总收入', type: 'line', smooth: true, yAxisIndex: 0, color: '#409eff',              data: s.total_revenue },
      { name: '总成本', type: 'line', smooth: true, yAxisIndex: 0, color: '#e6a23c',              data: s.total_cost },
      { name: '净利润', type: 'line', smooth: true, yAxisIndex: 0, color: '#67c23a',              data: s.total_profit },
      { name: '1店利润', type: 'bar', yAxisIndex: 1, itemStyle: { color: 'rgba(64,158,255,0.5)' }, data: s.profit_s1 },
      { name: '2店利润', type: 'bar', yAxisIndex: 1, itemStyle: { color: 'rgba(103,194,58,0.5)' }, data: s.profit_s2 },
    ],
  }
})

// ── Pie chart option ──────────────────────────────────────────────────────
const pieOption = computed(() => {
  if (!data.value) return {}
  const { total_profit, total_cost, total_refund } = data.value.kpi
  const profitVal = Math.max(0, total_profit)
  const pieData = []
  if (profitVal > 0) {
    pieData.push({ name: '净利润', value: profitVal, itemStyle: { color: '#67c23a' } })
  }
  if (total_cost > 0) {
    pieData.push({ name: '总成本', value: total_cost, itemStyle: { color: '#e6a23c' } })
  }
  if (total_refund > 0) {
    pieData.push({ name: '退款', value: total_refund, itemStyle: { color: '#f56c6c' } })
  }
  return {
    tooltip: { trigger: 'item', formatter: '{a} <br/>{b}：¥{c} ({d}%)' },
    legend: { orient: 'horizontal', bottom: 0 },
    series: [{
      name: '收入构成',
      type: 'pie',
      radius: ['40%', '68%'],
      data: pieData,
      label: { formatter: '{b}\n{d}%' },
      emphasis: {
        itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.5)' },
      },
    }],
  }
})
</script>

<template>
  <div class="home-dashboard">
    <h2 class="page-title">利润分析总览</h2>

    <!-- Filter row -->
    <div class="filter-row">
      <label class="filter-label">
        开始月份
        <input v-model="startMonth" type="text" placeholder="YYYY-MM" maxlength="7" class="month-input" />
      </label>
      <label class="filter-label">
        结束月份
        <input v-model="endMonth" type="text" placeholder="YYYY-MM" maxlength="7" class="month-input" />
      </label>
    </div>

    <div v-if="loading" class="status-msg">加载中…</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>

    <template v-else>
      <!-- KPI Cards -->
      <div class="kpi-section">
        <div class="kpi-store-label">1 店</div>
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">收入</div>
            <div class="kpi-value">¥{{ fmt(kpi.revenue_s1) }}</div>
          </div>
          <div class="kpi-card kpi-refund">
            <div class="kpi-label">退款</div>
            <div class="kpi-value">¥{{ fmt(kpi.refund_s1) }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">成本</div>
            <div class="kpi-value">¥{{ fmt(kpi.cost_s1) }}</div>
          </div>
          <div class="kpi-card" :class="kpi.profit_s1 >= 0 ? 'kpi-profit' : 'kpi-loss'">
            <div class="kpi-label">净利润</div>
            <div class="kpi-value">¥{{ fmt(kpi.profit_s1) }}</div>
          </div>
        </div>

        <div class="kpi-store-label">2 店</div>
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">收入</div>
            <div class="kpi-value">¥{{ fmt(kpi.revenue_s2) }}</div>
          </div>
          <div class="kpi-card kpi-refund">
            <div class="kpi-label">退款</div>
            <div class="kpi-value">¥{{ fmt(kpi.refund_s2) }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">成本</div>
            <div class="kpi-value">¥{{ fmt(kpi.cost_s2) }}</div>
          </div>
          <div class="kpi-card" :class="kpi.profit_s2 >= 0 ? 'kpi-profit' : 'kpi-loss'">
            <div class="kpi-label">净利润</div>
            <div class="kpi-value">¥{{ fmt(kpi.profit_s2) }}</div>
          </div>
        </div>

        <div class="kpi-store-label kpi-total-label">合计</div>
        <div class="kpi-grid">
          <div class="kpi-card kpi-card--total">
            <div class="kpi-label">总收入</div>
            <div class="kpi-value">¥{{ fmt(kpi.total_revenue) }}</div>
          </div>
          <div class="kpi-card kpi-card--total kpi-refund">
            <div class="kpi-label">总退款</div>
            <div class="kpi-value">¥{{ fmt(kpi.total_refund) }}</div>
          </div>
          <div class="kpi-card kpi-card--total">
            <div class="kpi-label">总成本</div>
            <div class="kpi-value">¥{{ fmt(kpi.total_cost) }}</div>
          </div>
          <div class="kpi-card kpi-card--total" :class="kpi.total_profit >= 0 ? 'kpi-profit' : 'kpi-loss'">
            <div class="kpi-label">净利润</div>
            <div class="kpi-value">¥{{ fmt(kpi.total_profit) }}</div>
          </div>
        </div>
      </div>

      <!-- Trend Chart -->
      <div class="chart-block">
        <div class="chart-title">月度利润走势</div>
        <div v-if="!hasData" class="chart-empty">暂无数据</div>
        <v-chart v-else :option="trendOption" autoresize style="height: 420px; width: 100%;" />
      </div>

      <!-- Pie Chart -->
      <div class="chart-block">
        <div class="chart-title">收入构成（净利润 / 成本 / 退款）</div>
        <div v-if="!hasData" class="chart-empty">暂无数据</div>
        <v-chart v-else :option="pieOption" autoresize style="height: 360px; width: 100%;" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.home-dashboard {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text, #1a1a1a);
}

.filter-row {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.filter-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-muted, #666);
}

.month-input {
  border: 1px solid var(--border-subtle, #ddd);
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  cursor: pointer;
}
.month-input:focus {
  border-color: #409eff;
}

.kpi-section {
  margin-bottom: 24px;
}

.kpi-store-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted, #666);
  letter-spacing: 0.5px;
  margin: 12px 0 6px;
}

.kpi-total-label {
  color: #303133;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 4px;
}

.kpi-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-subtle, #e4e7ed);
  border-radius: 8px;
  padding: 16px 20px;
}

.kpi-card--total {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.kpi-label {
  font-size: 12px;
  color: var(--text-muted, #909399);
  margin-bottom: 6px;
}

.kpi-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text, #303133);
}

.kpi-profit .kpi-value {
  color: #67c23a;
}

.kpi-loss .kpi-value {
  color: #f56c6c;
}

.kpi-refund .kpi-value {
  color: #e6a23c;
}

.chart-block {
  background: var(--bg-subtle, #f5f7fa);
  border: 1px solid var(--border-subtle, #e4e7ed);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text, #303133);
  margin-bottom: 12px;
}

.chart-empty {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted, #909399);
  font-size: 14px;
}

.status-msg {
  text-align: center;
  padding: 40px;
  color: var(--text-muted, #909399);
}

.error-msg {
  padding: 16px;
  color: #f56c6c;
  border: 1px solid #fde8e8;
  border-radius: 8px;
  background: #fef0f0;
}
</style>
