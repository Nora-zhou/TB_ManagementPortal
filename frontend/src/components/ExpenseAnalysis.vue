<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { fetchExpenseAnalysis } from '../api/profit.js'
import MonthPicker from './MonthPicker.vue'

use([
  CanvasRenderer,
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
])

const MONTH_RE = /^\d{4}-\d{2}$/

const CATEGORY_META = {
  platform_fee: { label: '平台扣费', color: '#8b5cf6' },
  promotion: { label: '推广费', color: '#f59e0b' },
  shipping_insurance: { label: '运费险', color: '#06b6d4' },
  other: { label: '其它费用', color: '#64748b' },
}

const CATEGORY_KEYS = Object.keys(CATEGORY_META)

const router = useRouter()
const startMonth = ref('')
const endMonth = ref('')
const store = ref(null)
const loading = ref(false)
const error = ref(null)
const data = ref(null)
const selectedCategory = ref('')
const selectedItemKey = ref('')

function money(value) {
  return Number(value ?? 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function pct(value) {
  if (value === null || value === undefined) return '—'
  return `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}%`
}

function pctClass(value) {
  if (value === null || value === undefined) return ''
  return value > 0 ? 'up' : value < 0 ? 'down' : ''
}

function roiText(value) {
  if (value === null || value === undefined) return '—'
  return Number(value).toFixed(2)
}

function categoryLabel(value) {
  return CATEGORY_META[value]?.label || value || '其它费用'
}

const kpi = computed(() => data.value?.kpi ?? {})
const hasData = computed(() => (data.value?.kpi?.total_expense ?? 0) > 0)
// 账单里带了「本月交易额」才画 ROI 轴，否则不显示空线
const hasRoi = computed(() => (data.value?.monthly ?? []).some((item) => item.roi != null))

const roiSub = computed(() => {
  const latest = kpi.value.latest_roi
  if (latest === null || latest === undefined) return '交易额 ÷ 费用合计'
  return `交易额 ÷ 费用合计 · ${kpi.value.latest_month} 为 ${roiText(latest)}`
})

const trendOption = computed(() => {
  const monthly = data.value?.monthly ?? []
  if (!monthly.length) return {}
  const months = monthly.map((item) => item.month)
  const moneyAxis = {
    type: 'value',
    axisLabel: { formatter: (value) => `¥${Number(value).toLocaleString('zh-CN')}` },
  }
  const series = [
    ...CATEGORY_KEYS.map((key) => ({
      name: CATEGORY_META[key].label,
      type: 'bar',
      stack: 'expense',
      color: CATEGORY_META[key].color,
      data: monthly.map((item) => item[key] ?? 0),
    })),
    {
      name: '费用合计',
      type: 'line',
      smooth: true,
      symbolSize: 7,
      color: '#111827',
      lineStyle: { width: 2.5 },
      data: monthly.map((item) => item.total ?? 0),
    },
  ]
  if (hasRoi.value) {
    series.push({
      name: 'ROI',
      type: 'line',
      yAxisIndex: 1,
      smooth: true,
      symbolSize: 7,
      color: '#0284c7',
      lineStyle: { width: 2, type: 'dashed' },
      data: monthly.map((item) => item.roi),
    })
  }
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        const month = params[0].axisValue
        const point = monthly.find((item) => item.month === month) || {}
        let html = `<b>${month}</b><br/>`
        params.forEach((p) => {
          if (p.seriesName === 'ROI') {
            html += `${p.marker}ROI：${roiText(p.value)}<br/>`
          } else {
            html += `${p.marker}${p.seriesName}：¥${money(p.value)}<br/>`
          }
        })
        html += `交易额：¥${money(point.transaction_amount)}<br/>`
        html += `ROI：${roiText(point.roi)}`
        return html
      },
    },
    legend: { bottom: 0 },
    grid: { left: '3%', right: '4%', top: 24, bottom: 48, containLabel: true },
    xAxis: { type: 'category', data: months },
    yAxis: hasRoi.value
      ? [
          moneyAxis,
          {
            type: 'value',
            name: 'ROI',
            position: 'right',
            axisLabel: { formatter: (value) => Number(value).toFixed(0) },
            splitLine: { show: false },
          },
        ]
      : moneyAxis,
    series,
  }
})

const categorySummary = computed(() => {
  const monthly = data.value?.monthly ?? []
  const totals = Object.fromEntries(CATEGORY_KEYS.map((key) => [key, 0]))
  monthly.forEach((item) => {
    CATEGORY_KEYS.forEach((key) => {
      totals[key] += Number(item[key] ?? 0)
    })
  })
  const total = Object.values(totals).reduce((sum, value) => sum + value, 0)
  return CATEGORY_KEYS.map((key) => ({
    key,
    label: CATEGORY_META[key].label,
    color: CATEGORY_META[key].color,
    amount: totals[key],
    share: total > 0 ? (totals[key] / total) * 100 : 0,
  }))
})

const pieOption = computed(() => {
  const items = categorySummary.value.filter((item) => item.amount > 0)
  if (!items.length) return {}
  return {
    tooltip: {
      trigger: 'item',
      formatter: (params) =>
        `${params.marker}${params.name}<br/>¥${money(params.value)}（${params.percent}%）`,
    },
    series: [
      {
        type: 'pie',
        radius: ['46%', '70%'],
        center: ['50%', '46%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{d}%', fontSize: 11, color: '#4e4e4e' },
        data: items.map((item) => ({
          name: item.label,
          value: Number(item.amount.toFixed(2)),
          itemStyle: { color: item.color },
        })),
      },
    ],
  }
})

const filteredItems = computed(() => {
  const items = data.value?.items ?? []
  if (!selectedCategory.value) return items
  return items.filter((item) => item.category === selectedCategory.value)
})

const selectedItem = computed(() => {
  const items = data.value?.items ?? []
  if (!items.length) return null
  const key = `${selectedItemKey.value}`
  return items.find((item) => `${item.category}::${item.name}` === key) || items[0]
})

const itemTrendOption = computed(() => {
  const item = selectedItem.value
  if (!item) return {}
  const months = data.value?.months ?? []
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const point = params[0]
        return `<b>${point.axisValue}</b><br/>${point.marker}${item.name}：¥${money(point.value)}`
      },
    },
    grid: { left: '3%', right: '4%', top: 20, bottom: 40, containLabel: true },
    xAxis: { type: 'category', data: months },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (value) => `¥${Number(value).toLocaleString('zh-CN')}` },
    },
    series: [
      {
        name: item.name,
        type: 'bar',
        barMaxWidth: 40,
        color: CATEGORY_META[item.category]?.color || '#111827',
        data: months.map((month) => item.monthly?.[month] ?? 0),
      },
    ],
  }
})

function selectCategory(key) {
  selectedCategory.value = key
  const first = filteredItems.value[0]
  selectedItemKey.value = first ? `${first.category}::${first.name}` : ''
}

function selectItem(item) {
  selectedItemKey.value = `${item.category}::${item.name}`
}

async function loadData() {
  if (startMonth.value && !MONTH_RE.test(startMonth.value)) return
  if (endMonth.value && !MONTH_RE.test(endMonth.value)) return

  loading.value = true
  error.value = null
  try {
    data.value = await fetchExpenseAnalysis({
      startMonth: startMonth.value || undefined,
      endMonth: endMonth.value || undefined,
      store: store.value ?? undefined,
    })
    const first = data.value?.items?.[0]
    selectedCategory.value = ''
    selectedItemKey.value = first ? `${first.category}::${first.name}` : ''
  } catch (e) {
    console.error('[运营费用分析] 加载失败', e)
    error.value = e.message || '加载失败'
    data.value = null
  } finally {
    loading.value = false
  }
}

watch([startMonth, endMonth, store], loadData)
onMounted(loadData)
</script>

<template>
  <div class="expense-analysis">
    <div class="page-header">
      <div>
        <h1 class="page-title">运营费用分析</h1>
        <p class="page-desc">
          按月查看运营费用走势，拆解平台扣费、推广费、运费险与其它费用，并结合账单「本月交易额」
          分析各费用项占比、环比变化与 ROI（交易额 ÷ 费用）。
        </p>
      </div>
      <button class="btn-primary" @click="router.push('/operating-costs/import')">
        导入运营成本
      </button>
    </div>

    <div class="filter-bar">
      <label class="filter-field">
        <span>开始月份</span>
        <MonthPicker v-model="startMonth" />
      </label>
      <label class="filter-field">
        <span>结束月份</span>
        <MonthPicker v-model="endMonth" />
      </label>
      <div class="store-filter">
        <button :class="{ active: store === null }" @click="store = null">全部店铺</button>
        <button :class="{ active: store === 1 }" @click="store = 1">店铺 1</button>
        <button :class="{ active: store === 2 }" @click="store = 2">店铺 2</button>
      </div>
    </div>

    <div v-if="loading" class="state-box">加载中…</div>
    <div v-else-if="error" class="error-box">{{ error }}</div>
    <div v-else-if="!hasData" class="empty-box">
      暂无运营费用数据。请先在
      <a @click="router.push('/operating-costs/import')">运营成本导入</a>
      上传汇总账单。
    </div>

    <template v-else>
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-label">费用合计</div>
          <div class="kpi-value">¥{{ money(kpi.total_expense) }}</div>
          <div class="kpi-sub">{{ kpi.month_count }} 个月有费用</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">月均费用</div>
          <div class="kpi-value">¥{{ money(kpi.avg_monthly) }}</div>
          <div class="kpi-sub">按有费用的月份平均</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">环比变化</div>
          <div class="kpi-value" :class="pctClass(kpi.mom_pct)">{{ pct(kpi.mom_pct) }}</div>
          <div class="kpi-sub">{{ kpi.latest_month || '—' }} 对比上月</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">累计交易额</div>
          <div class="kpi-value">¥{{ money(kpi.total_transaction_amount) }}</div>
          <div class="kpi-sub">来自账单「本月交易额」</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">累计 ROI</div>
          <div class="kpi-value">{{ roiText(kpi.roi) }}</div>
          <div class="kpi-sub">{{ roiSub }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">最大费用类别</div>
          <div class="kpi-value kpi-value--small">
            {{ categoryLabel(kpi.top_category) }}
          </div>
          <div class="kpi-sub">¥{{ money(kpi.top_category_amount) }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">最大费用项</div>
          <div class="kpi-value kpi-value--small">{{ kpi.top_item || '—' }}</div>
          <div class="kpi-sub">¥{{ money(kpi.top_item_amount) }}</div>
        </div>
      </div>

      <div class="chart-row">
        <div class="chart-card chart-card--wide">
          <div class="card-head">
            <span class="card-title">运营费用走势</span>
            <span class="card-sub">
              按费用类别堆叠，折线为当月合计{{ hasRoi ? '，右轴为 ROI（交易额 ÷ 费用）' : '' }}
            </span>
          </div>
          <VChart class="chart chart--tall" :option="trendOption" autoresize />
        </div>

        <div class="chart-card">
          <div class="card-head">
            <span class="card-title">类别构成</span>
            <span class="card-sub">区间累计</span>
          </div>
          <VChart v-if="pieOption.series" class="chart chart--tall" :option="pieOption" autoresize />
          <div class="category-list">
            <div v-for="item in categorySummary" :key="item.key" class="category-row">
              <span class="dot" :style="{ background: item.color }"></span>
              <span class="category-name">{{ item.label }}</span>
              <span class="category-amount">¥{{ money(item.amount) }}</span>
              <span class="category-share">{{ item.share.toFixed(1) }}%</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <span class="card-title">费用项分析</span>
          <span class="card-sub">共 {{ filteredItems.length }} 项，点击查看单项走势</span>
        </div>

        <div class="chip-row">
          <button :class="{ active: selectedCategory === '' }" @click="selectCategory('')">
            全部
          </button>
          <button
            v-for="item in categorySummary"
            :key="item.key"
            :class="{ active: selectedCategory === item.key }"
            @click="selectCategory(item.key)"
          >
            {{ item.label }}
          </button>
        </div>

        <div v-if="!filteredItems.length" class="empty-inline">该类别下暂无费用项</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>费用项</th>
              <th>类别</th>
              <th class="num">合计</th>
              <th class="num">占比</th>
              <th class="num">交易额</th>
              <th class="num">ROI</th>
              <th class="num">最近月</th>
              <th class="num">环比</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in filteredItems"
              :key="`${item.category}::${item.name}`"
              class="clickable"
              :class="{ selected: selectedItemKey === `${item.category}::${item.name}` }"
              @click="selectItem(item)"
            >
              <td class="item-name">{{ item.name }}</td>
              <td>
                <span class="category-tag" :style="{ color: CATEGORY_META[item.category]?.color }">
                  {{ categoryLabel(item.category) }}
                </span>
              </td>
              <td class="num">¥{{ money(item.total) }}</td>
              <td class="num">{{ Number(item.share_pct).toFixed(1) }}%</td>
              <td class="num">¥{{ money(item.transaction_amount) }}</td>
              <td class="num">{{ roiText(item.roi) }}</td>
              <td class="num">¥{{ money(item.latest_amount) }}</td>
              <td class="num" :class="pctClass(item.mom_pct)">{{ pct(item.mom_pct) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="selectedItem" class="card">
        <div class="card-head">
          <span class="card-title">{{ selectedItem.name }} · 月度走势</span>
          <span class="card-sub">
            {{ categoryLabel(selectedItem.category) }} · 合计 ¥{{ money(selectedItem.total) }}
          </span>
        </div>
        <VChart class="chart" :option="itemTrendOption" autoresize />
      </div>
    </template>
  </div>
</template>

<style scoped>
.expense-analysis {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.page-title {
  font-size: 28px;
  font-weight: 300;
  letter-spacing: -0.5px;
  color: var(--text);
  margin: 0 0 4px;
}
.page-desc {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-muted);
  margin: 0;
  max-width: 760px;
}
.btn-primary {
  padding: 8px 18px;
  background: #000;
  color: #fff;
  border: none;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}
.btn-primary:hover { background: #222; }

.filter-bar {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  padding: 14px 18px;
  background: var(--surface);
  border-radius: 16px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.filter-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  color: var(--text-muted);
}
.filter-field input {
  width: 120px;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
  outline: none;
}
.filter-field input:focus { border-color: var(--text-secondary); }

.store-filter {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: var(--bg-subtle);
  border-radius: 9999px;
  margin-left: auto;
}
.store-filter button {
  padding: 6px 14px;
  border: none;
  background: transparent;
  border-radius: 9999px;
  font-size: 12.5px;
  color: var(--text-muted);
  cursor: pointer;
}
.store-filter button.active {
  background: #000;
  color: #fff;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
}
.kpi-card {
  background: var(--surface);
  border-radius: 14px;
  padding: 16px 18px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.kpi-label { font-size: 12px; color: var(--text-muted); margin-bottom: 8px; }
.kpi-value {
  font-size: 24px;
  font-weight: 300;
  letter-spacing: -0.4px;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.kpi-value--small { font-size: 17px; font-weight: 500; line-height: 1.5; }
.kpi-sub { margin-top: 6px; font-size: 11.5px; color: var(--text-muted); }

.up { color: #b45309; }
.down { color: #047857; }

.chart-row {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 12px;
}
.chart-card,
.card {
  background: var(--surface);
  border-radius: 16px;
  padding: 18px 20px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.card-title { font-size: 14px; font-weight: 500; color: var(--text); }
.card-sub { font-size: 11.5px; color: var(--text-muted); }

.chart { width: 100%; height: 260px; }
.chart--tall { height: 320px; }

.category-list { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
.category-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--text-secondary);
}
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.category-name { flex: 1; }
.category-amount { font-variant-numeric: tabular-nums; }
.category-share { width: 48px; text-align: right; color: var(--text-muted); }

.chip-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.chip-row button {
  padding: 5px 13px;
  border: 1px solid var(--border);
  border-radius: 9999px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12.5px;
  cursor: pointer;
}
.chip-row button.active {
  background: #000;
  border-color: #000;
  color: #fff;
}

.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th {
  text-align: left;
  padding: 8px 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}
.data-table td {
  padding: 10px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}
.data-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.data-table tbody tr.clickable { cursor: pointer; }
.data-table tbody tr.clickable:hover { background: var(--bg-subtle); }
.data-table tbody tr.selected { background: rgba(0, 0, 0, 0.04); }
.item-name { color: var(--text); }
.category-tag { font-size: 12px; font-weight: 500; }

.state-box,
.empty-box,
.empty-inline {
  padding: 40px 0;
  text-align: center;
  font-size: 13.5px;
  color: var(--text-muted);
}
.empty-box {
  background: var(--surface);
  border-radius: 16px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.empty-box a { color: var(--text); text-decoration: underline; text-underline-offset: 3px; cursor: pointer; }
.empty-inline { padding: 24px 0; }
.error-box {
  padding: 12px 16px;
  border-radius: 10px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-size: 13px;
}

@media (max-width: 900px) {
  .chart-row { grid-template-columns: 1fr; }
  .page-header { flex-direction: column; }
  .store-filter { margin-left: 0; }
}
</style>
