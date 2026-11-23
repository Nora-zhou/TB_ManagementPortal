<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
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
import { fetchPureProfit, fetchExpenses, createExpense, updateExpense, deleteExpense } from '../api/profit.js'
import { fetchAccounts, fetchPlatforms } from '../api/credentials.js'
import { createTask, cancelTask, fetchTask } from '../api/rpa_tasks.js'
import MonthPicker from './MonthPicker.vue'

use([
  CanvasRenderer, BarChart, LineChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent, LegendScrollComponent,
])

const MONTH_RE = /^\d{4}-\d{2}$/

function previousMonthKey() {
  const date = new Date()
  date.setDate(1)
  date.setMonth(date.getMonth() - 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

const startMonth = ref('')
const endMonth   = ref(previousMonthKey())
const loading    = ref(false)
const error      = ref(null)
const data       = ref(null)

// ── 费用类别元数据 ──────────────────────────────────────────────
const EXPENSE_META = {
  platform_fee:       { label: '平台扣费',   color: '#8b5cf6' },
  promotion:          { label: '推广费',     color: '#f59e0b' },
  shipping_insurance: { label: '运费险',     color: '#06b6d4' },
  other:              { label: '其它费用',   color: '#64748b' },
}

const CATEGORY_OPTIONS = [
  { value: 'platform_fee',       label: '平台扣费' },
  { value: 'promotion',          label: '推广费' },
  { value: 'shipping_insurance', label: '运费险' },
  { value: 'other',              label: '其它费用' },
]

// ── 数据加载 ───────────────────────────────────────────────────
async function loadData() {
  if (startMonth.value && !MONTH_RE.test(startMonth.value)) return
  if (endMonth.value && !MONTH_RE.test(endMonth.value)) return

  loading.value = true
  error.value = null
  try {
    const [pure, expenses] = await Promise.all([
      fetchPureProfit({
        startMonth: startMonth.value || undefined,
        endMonth: endMonth.value || undefined,
      }),
      fetchExpenses({
        startMonth: startMonth.value || undefined,
        endMonth: endMonth.value || undefined,
      }),
    ])
    data.value = pure
    expenses.value = expenses.items
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
watch([startMonth, endMonth], loadData)

// ── 格式化 ─────────────────────────────────────────────────────
function fmt(n) {
  return Number(n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n) {
  if (n === null || n === undefined) return '—'
  const sign = n > 0 ? '+' : ''
  return `${sign}${Number(n).toFixed(2)}%`
}

const hasData = computed(() => (data.value?.months?.length ?? 0) > 0)

// ── KPI ────────────────────────────────────────────────────────
const ZERO = new Proxy({}, { get: () => 0 })
const kpi = computed(() => data.value?.kpi ?? ZERO)

const STORES = [
  { key: 's1', label: '1 店' },
  { key: 's2', label: '2 店' },
]

function kpiFor(suffix) {
  return {
    revenue: kpi.value['revenue_' + suffix] ?? 0,
    refund: kpi.value['refund_' + suffix] ?? 0,
    cost: kpi.value['cost_' + suffix] ?? 0,
    platform_fee: kpi.value['platform_fee_' + suffix] ?? 0,
    promotion: kpi.value['promotion_' + suffix] ?? 0,
    shipping_insurance: kpi.value['shipping_insurance_' + suffix] ?? 0,
    other: kpi.value['other_' + suffix] ?? 0,
    profit: kpi.value['profit_' + suffix] ?? 0,
  }
}

const total = computed(() => ({
  revenue: kpi.value.total_revenue ?? 0,
  refund: kpi.value.total_refund ?? 0,
  cost: kpi.value.total_cost ?? 0,
  platform_fee: kpi.value.total_platform_fee ?? 0,
  promotion: kpi.value.total_promotion ?? 0,
  shipping_insurance: kpi.value.total_shipping_insurance ?? 0,
  other: kpi.value.total_other ?? 0,
  profit: kpi.value.total_profit ?? 0,
  margin: kpi.value.total_profit_margin_pct ?? null,
}))

const netRevenue = computed(() => total.value.revenue - total.value.refund)

// ── 月度构成图 ─────────────────────────────────────────────────
const trendOption = computed(() => {
  const items = data.value?.items
  if (!items?.length) return {}
  const months = items.map(i => i.month)
  const pick = (field) => items.map(i =>
    Number(((i[field + '_s1'] ?? 0) + (i[field + '_s2'] ?? 0)).toFixed(2))
  )
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
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
    grid: { left: '3%', right: '6%', bottom: '18%', containLabel: true },
    xAxis: { type: 'category', data: months, boundaryGap: true },
    yAxis: {
      name: '金额（元）',
      type: 'value',
      axisLabel: { formatter: v => `¥${(v / 1000).toFixed(0)}K` },
    },
    series: [
      { name: '采购成本',   type: 'bar', stack: 'cost', color: '#d97706', data: pick('cost') },
      { name: '平台扣费',   type: 'bar', stack: 'cost', color: '#8b5cf6', data: pick('platform_fee') },
      { name: '推广费',     type: 'bar', stack: 'cost', color: '#f59e0b', data: pick('promotion') },
      { name: '运费险',     type: 'bar', stack: 'cost', color: '#06b6d4', data: pick('shipping_insurance') },
      { name: '其它费用',   type: 'bar', stack: 'cost', color: '#64748b', data: pick('other') },
      { name: '退款',       type: 'bar', stack: 'cost', color: '#dc2626', data: pick('refund') },
      {
        name: '纯利润', type: 'line', smooth: true, color: '#059669',
        symbolSize: 8, lineStyle: { width: 3 },
        data: pick('profit'),
      },
    ],
  }
})

// ── 运营视角：收入去向与利润率 ─────────────────────────────────
function monthTotal(item, field) {
  return (item[field + '_s1'] ?? 0) + (item[field + '_s2'] ?? 0)
}

function itemMargin(item) {
  const revenue = monthTotal(item, 'revenue')
  const net = revenue - monthTotal(item, 'refund')
  return net > 0 ? (monthTotal(item, 'profit') / net) * 100 : null
}

const opsStructureOption = computed(() => {
  const items = (data.value?.items ?? []).filter(
    (item) => monthTotal(item, 'revenue') > 0,
  )
  if (!items.length) return {}

  const rows = items.map((item) => {
    const revenue = monthTotal(item, 'revenue')
    return {
      month: item.month,
      revenue,
      profit: monthTotal(item, 'profit'),
      refund: monthTotal(item, 'refund'),
      cost: monthTotal(item, 'cost'),
      platform_fee: monthTotal(item, 'platform_fee'),
      promotion: monthTotal(item, 'promotion'),
      shipping_insurance: monthTotal(item, 'shipping_insurance'),
      other: monthTotal(item, 'other'),
      margin: itemMargin(item),
    }
  })

  const share = (value, revenue) => (revenue > 0 ? Number(((value / revenue) * 100).toFixed(2)) : 0)
  const segment = (key, name, color) => ({
    name,
    type: 'bar',
    stack: 'revenue',
    barMaxWidth: 46,
    color,
    data: rows.map((row) => ({
      value: share(row[key], row.revenue),
      amount: row[key],
    })),
  })

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        const row = rows.find((item) => item.month === params[0].axisValue)
        let html = `<b>${row.month}</b>　收入 ¥${fmt(row.revenue)}<br/>`
        params.forEach((point) => {
          if (point.seriesName === '纯利润率') {
            html += `${point.marker}${point.seriesName}：${point.value == null ? '—' : point.value + '%'}<br/>`
          } else {
            html += `${point.marker}${point.seriesName}：¥${fmt(point.data.amount)}（${point.value}%）<br/>`
          }
        })
        return html
      },
    },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: '3%', right: '4%', top: 30, bottom: 54, containLabel: true },
    xAxis: { type: 'category', data: rows.map((row) => row.month) },
    yAxis: {
      type: 'value',
      max: (value) => Math.max(100, Math.ceil(value.max)),
      axisLabel: { formatter: '{value}%' },
    },
    series: [
      segment('profit', '纯利润', '#059669'),
      segment('refund', '退款', '#dc2626'),
      segment('cost', '采购成本', '#d97706'),
      segment('platform_fee', '平台扣费', '#8b5cf6'),
      segment('promotion', '推广费', '#f59e0b'),
      segment('shipping_insurance', '运费险', '#06b6d4'),
      segment('other', '其它费用', '#64748b'),
      {
        name: '纯利润率',
        type: 'line',
        smooth: true,
        symbolSize: 7,
        color: '#111827',
        lineStyle: { width: 2, type: 'dashed' },
        data: rows.map((row) => (row.margin == null ? null : Number(row.margin.toFixed(2)))),
      },
    ],
  }
})

const opsInsights = computed(() => {
  const items = (data.value?.items ?? []).filter(
    (item) => monthTotal(item, 'revenue') > 0,
  )
  if (items.length < 2) return []

  const latest = items[items.length - 1]
  const previous = items[items.length - 2]
  const points = (value) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}pct`
  const rate = (item, field) => {
    const revenue = monthTotal(item, 'revenue')
    return revenue > 0 ? (monthTotal(item, field) / revenue) * 100 : null
  }

  const insights = []
  const latestMargin = itemMargin(latest)
  const previousMargin = itemMargin(previous)
  if (latestMargin != null && previousMargin != null) {
    const delta = latestMargin - previousMargin
    insights.push({
      label: '纯利润率',
      value: `${latestMargin.toFixed(2)}%`,
      text: `环比 ${points(delta)}`,
      tone: delta >= 0 ? 'good' : 'bad',
    })
  }

  const costRate = rate(latest, 'cost')
  const previousCostRate = rate(previous, 'cost')
  if (costRate != null && previousCostRate != null) {
    const delta = costRate - previousCostRate
    insights.push({
      label: '采购成本率',
      value: `${costRate.toFixed(2)}%`,
      text: `环比 ${points(delta)}`,
      tone: delta <= 0 ? 'good' : 'bad',
    })
  }

  const refundRate = rate(latest, 'refund')
  const previousRefundRate = rate(previous, 'refund')
  if (refundRate != null && previousRefundRate != null) {
    const delta = refundRate - previousRefundRate
    insights.push({
      label: '退款率',
      value: `${refundRate.toFixed(2)}%`,
      text: `环比 ${points(delta)}`,
      tone: delta <= 0 ? 'good' : 'bad',
    })
  }

  return insights
})

// ── 数据源状态 ─────────────────────────────────────────────────
const sourceLabels = {
  pending: '等待中', running: '抓取中', success: '成功',
  failed: '失败', cancelled: '已取消', need_verify: '待人工验证',
}

function sourceStatusClass(s) {
  if (s === 'success') return 'src-ok'
  if (s === 'failed') return 'src-fail'
  if (s === 'need_verify') return 'src-warn'
  if (s === 'running') return 'src-running'
  return 'src-idle'
}

// ── RPA 触发弹窗 ───────────────────────────────────────────────
const showTrigger = ref(false)
const accounts = ref([])
const platforms = ref([])
const triggerForm = ref({ accountId: '', datasets: [], periodMonth: '' })
const triggerError = ref(null)
const triggering = ref(false)

async function openTrigger() {
  showTrigger.value = true
  triggerError.value = null
  try {
    const [acc, plat] = await Promise.all([fetchAccounts(), fetchPlatforms()])
    accounts.value = acc.items
    platforms.value = plat
    if (!triggerForm.value.accountId && acc.items.length) {
      triggerForm.value.accountId = String(acc.items[0].id)
    }
  } catch (e) {
    triggerError.value = e.message || '加载账号失败'
  }
}

const selectedPlatform = computed(() => {
  const acc = accounts.value.find(a => String(a.id) === String(triggerForm.value.accountId))
  return platforms.value.find(p => p.platform === acc?.platform) || null
})

const selectedStore = computed(() => {
  const acc = accounts.value.find(a => String(a.id) === String(triggerForm.value.accountId))
  return acc ? acc.store : 1
})

async function submitTrigger() {
  if (!triggerForm.value.accountId) { triggerError.value = '请选择平台账号'; return }
  if (!triggerForm.value.datasets.length) { triggerError.value = '请至少勾选一项要拉取的数据'; return }
  triggering.value = true
  triggerError.value = null
  try {
    const task = await createTask({
      account_id: Number(triggerForm.value.accountId),
      store: selectedStore.value,
      datasets: triggerForm.value.datasets,
      period_month: triggerForm.value.periodMonth || null,
    })
    showTrigger.value = false
    watchingTaskId.value = task.id
    showTaskLog.value = true
    triggerForm.value.datasets = []
  } catch (e) {
    triggerError.value = e.message || '创建任务失败'
  } finally {
    triggering.value = false
  }
}

// ── 任务日志弹窗 ───────────────────────────────────────────────
const showTaskLog = ref(false)
const watchingTaskId = ref(null)
const watchingTask = ref(null)
let _pollTimer = null

async function pollTask() {
  if (!watchingTaskId.value) return
  try {
    watchingTask.value = await fetchTask(watchingTaskId.value)
    const status = watchingTask.value.status
    if (['success', 'failed', 'cancelled', 'need_verify'].includes(status)) {
      loadData()
      return
    }
  } catch (e) {
    console.error(e)
  }
  _pollTimer = setTimeout(pollTask, 2500)
}

watch(showTaskLog, (open) => {
  clearTimeout(_pollTimer)
  if (open) pollTask()
})
onUnmounted(() => clearTimeout(_pollTimer))

async function doCancelTask() {
  if (!watchingTaskId.value) return
  try {
    watchingTask.value = await cancelTask(watchingTaskId.value)
    loadData()
  } catch (e) {
    alert(e.message || '取消失败')
  }
}

// ── 费用明细（手动录入） ────────────────────────────────────────
const expenses = ref([])
const showExpenseForm = ref(false)
const editingId = ref(null)
const expenseForm = ref(blankExpense())
const expenseError = ref(null)

function blankExpense() {
  return { store: 1, period_month: '', category: 'promotion', sub_category: '', amount: '', note: '' }
}

function startAdd() {
  editingId.value = null
  expenseForm.value = blankExpense()
  expenseError.value = null
  showExpenseForm.value = true
}

function startEdit(row) {
  editingId.value = row.id
  expenseForm.value = {
    store: row.store,
    period_month: row.period_month,
    category: row.category,
    sub_category: row.sub_category || '',
    amount: String(row.amount),
    note: row.note || '',
  }
  expenseError.value = null
  showExpenseForm.value = true
}

async function saveExpense() {
  expenseError.value = null
  if (!MONTH_RE.test(expenseForm.value.period_month)) {
    expenseError.value = '月份格式应为 YYYY-MM'
    return
  }
  if (!(Number(expenseForm.value.amount) >= 0)) {
    expenseError.value = '金额必须为非负数字'
    return
  }
  const payload = {
    store: Number(expenseForm.value.store),
    period_month: expenseForm.value.period_month,
    category: expenseForm.value.category,
    sub_category: expenseForm.value.sub_category || null,
    amount: Number(expenseForm.value.amount),
    note: expenseForm.value.note || null,
  }
  try {
    if (editingId.value) {
      await updateExpense(editingId.value, { amount: payload.amount, note: payload.note })
    } else {
      await createExpense(payload)
    }
    showExpenseForm.value = false
    await loadData()
  } catch (e) {
    expenseError.value = e.message || '保存失败'
  }
}

async function removeExpense(id) {
  if (!confirm('确认删除该费用记录？')) return
  try {
    await deleteExpense(id)
    await loadData()
  } catch (e) {
    alert(e.message || '删除失败')
  }
}

function categoryLabel(c) {
  return CATEGORY_OPTIONS.find(o => o.value === c)?.label || c
}

function sourceLabel(source) {
  if (source === 'rpa') return 'RPA'
  if (source === 'xlsx') return '账单'
  return '手动'
}

function sourceTagClass(source) {
  if (source === 'rpa') return 'tag-rpa'
  if (source === 'xlsx') return 'tag-xlsx'
  return 'tag-manual'
}
</script>

<template>
  <div class="pure-profit">
    <div class="page-header">
      <div>
        <h2 class="page-title">纯利润分析</h2>
        <p class="page-sub">净利润 = 收入 − 退款 − 采购成本 − 平台扣费 − 推广费 − 运费险 − 其它费用</p>
      </div>
      <button class="btn-primary" @click="openTrigger">🤖 触发 RPA 抓取</button>
    </div>

    <!-- Filter row -->
    <div class="filter-row">
      <label class="filter-label">
        开始月份
        <MonthPicker v-model="startMonth" />
      </label>
      <label class="filter-label">
        结束月份
        <MonthPicker v-model="endMonth" />
      </label>
      <button class="btn-ghost" @click="startAdd">+ 手动录入费用</button>
    </div>

    <div v-if="loading" class="status-msg">加载中…</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>

    <template v-else>
      <!-- Data source status -->
      <div class="source-row">
        <div
          v-for="src in (data?.data_sources ?? [])"
          :key="src.platform"
          class="source-chip"
          :class="sourceStatusClass(src.last_task_status)"
        >
          <span class="src-name">{{ src.label }}</span>
          <span class="src-status">
            {{ src.last_task_status ? sourceLabels[src.last_task_status] : '未抓取' }}
          </span>
          <span class="src-meta">
            {{ src.configured ? src.account_count + ' 个账号' : '未配置账号' }}
          </span>
        </div>
      </div>

      <!-- Total KPI -->
      <div class="kpi-section">
        <div class="kpi-store-label kpi-total-label">合计</div>
        <div class="kpi-grid kpi-grid--8">
          <div class="kpi-card kpi-card--total">
            <div class="kpi-label">总收入</div>
            <div class="kpi-value">¥{{ fmt(total.revenue) }}</div>
          </div>
          <div class="kpi-card kpi-card--total kpi-refund">
            <div class="kpi-label">退款</div>
            <div class="kpi-value">¥{{ fmt(total.refund) }}</div>
          </div>
          <div class="kpi-card kpi-card--total">
            <div class="kpi-label">采购成本</div>
            <div class="kpi-value">¥{{ fmt(total.cost) }}</div>
          </div>
          <div class="kpi-card kpi-card--total kpi-fee">
            <div class="kpi-label">平台扣费</div>
            <div class="kpi-value">¥{{ fmt(total.platform_fee) }}</div>
          </div>
          <div class="kpi-card kpi-card--total kpi-fee">
            <div class="kpi-label">推广费</div>
            <div class="kpi-value">¥{{ fmt(total.promotion) }}</div>
          </div>
          <div class="kpi-card kpi-card--total kpi-fee">
            <div class="kpi-label">运费险</div>
            <div class="kpi-value">¥{{ fmt(total.shipping_insurance) }}</div>
          </div>
          <div class="kpi-card kpi-card--total kpi-fee">
            <div class="kpi-label">其它费用</div>
            <div class="kpi-value">¥{{ fmt(total.other) }}</div>
          </div>
          <div class="kpi-card kpi-card--total" :class="total.profit >= 0 ? 'kpi-profit' : 'kpi-loss'">
            <div class="kpi-label">纯利润</div>
            <div class="kpi-value">¥{{ fmt(total.profit) }}</div>
            <div class="kpi-mom">环比 {{ fmtPct(kpi.profit_mom_pct) }}</div>
          </div>
        </div>
        <div class="kpi-grid kpi-grid--2">
          <div class="kpi-card">
            <div class="kpi-label">净收入（收入 − 退款）</div>
            <div class="kpi-value">¥{{ fmt(netRevenue) }}</div>
          </div>
          <div class="kpi-card" :class="(total.margin ?? 0) >= 0 ? 'kpi-profit' : 'kpi-loss'">
            <div class="kpi-label">纯利润率（纯利润 / 净收入）</div>
            <div class="kpi-value">{{ total.margin === null ? '—' : total.margin.toFixed(2) + '%' }}</div>
            <div class="kpi-mom">环比 {{ fmtPct(kpi.margin_mom_pct) }}</div>
          </div>
        </div>
      </div>

      <!-- Per-store KPI -->
      <div class="kpi-section">
        <template v-for="store in STORES" :key="store.key">
          <div class="kpi-store-label">{{ store.label }}</div>
          <div class="kpi-grid">
            <div class="kpi-card">
              <div class="kpi-label">收入</div>
              <div class="kpi-value">¥{{ fmt(kpiFor(store.key).revenue) }}</div>
            </div>
            <div class="kpi-card kpi-refund">
              <div class="kpi-label">退款</div>
              <div class="kpi-value">¥{{ fmt(kpiFor(store.key).refund) }}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">采购成本</div>
              <div class="kpi-value">¥{{ fmt(kpiFor(store.key).cost) }}</div>
            </div>
            <div class="kpi-card kpi-fee">
              <div class="kpi-label">平台扣费 + 推广 + 运费险</div>
              <div class="kpi-value">¥{{ fmt(kpiFor(store.key).platform_fee + kpiFor(store.key).promotion + kpiFor(store.key).shipping_insurance) }}</div>
            </div>
            <div class="kpi-card" :class="kpiFor(store.key).profit >= 0 ? 'kpi-profit' : 'kpi-loss'">
              <div class="kpi-label">纯利润</div>
              <div class="kpi-value">¥{{ fmt(kpiFor(store.key).profit) }}</div>
            </div>
          </div>
        </template>
      </div>

      <!-- Trend chart -->
      <div class="chart-block">
        <div class="chart-title">月度纯利润构成</div>
        <div v-if="!hasData" class="chart-empty">暂无数据</div>
        <v-chart v-else :option="trendOption" autoresize style="height: 440px; width: 100%;" />
      </div>

      <!-- Monthly detail table -->
      <div class="table-block">
        <div class="chart-title">月度明细</div>
        <div v-if="!hasData" class="chart-empty">暂无数据</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>月份</th>
              <th class="num">收入</th>
              <th class="num">退款</th>
              <th class="num">采购成本</th>
              <th class="num">平台扣费</th>
              <th class="num">推广费</th>
              <th class="num">运费险</th>
              <th class="num">其它</th>
              <th class="num">纯利润</th>
              <th class="num">纯利润率</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in data.items" :key="item.month">
              <td>{{ item.month }}</td>
              <td class="num">¥{{ fmt(item.revenue_s1 + item.revenue_s2) }}</td>
              <td class="num warn">¥{{ fmt(item.refund_s1 + item.refund_s2) }}</td>
              <td class="num">¥{{ fmt(item.cost_s1 + item.cost_s2) }}</td>
              <td class="num">¥{{ fmt(item.platform_fee_s1 + item.platform_fee_s2) }}</td>
              <td class="num">¥{{ fmt(item.promotion_s1 + item.promotion_s2) }}</td>
              <td class="num">¥{{ fmt(item.shipping_insurance_s1 + item.shipping_insurance_s2) }}</td>
              <td class="num">¥{{ fmt(item.other_s1 + item.other_s2) }}</td>
              <td class="num" :class="(item.profit_s1 + item.profit_s2) >= 0 ? 'profit' : 'loss'">
                ¥{{ fmt(item.profit_s1 + item.profit_s2) }}
              </td>
              <td class="num">
                {{ (() => {
                    const net = item.revenue_s1 + item.revenue_s2 - item.refund_s1 - item.refund_s2
                    const p = item.profit_s1 + item.profit_s2
                    return net > 0 ? (p / net * 100).toFixed(2) + '%' : '—'
                  })() }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Operations view: where revenue goes -->
      <div class="chart-block">
        <div class="chart-title">运营视角：每 100 元收入去哪了</div>
        <div class="chart-sub">
          堆叠为各项占收入比例；虚线为纯利润率（扣除退款后的净收入口径）。绿色段越大，说明同样的收入留下更多利润。
        </div>
        <v-chart
          v-if="opsStructureOption.series"
          :option="opsStructureOption"
          autoresize
          style="height: 380px; width: 100%;"
        />
        <div v-else class="chart-empty">暂无数据</div>

        <div v-if="opsInsights.length" class="insight-grid">
          <div v-for="insight in opsInsights" :key="insight.label" class="insight-card">
            <div class="insight-label">{{ insight.label }}</div>
            <div class="insight-main">
              <span class="insight-value">{{ insight.value }}</span>
              <span class="insight-delta" :class="insight.tone">{{ insight.text }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Expense records -->
      <div class="table-block">
        <div class="chart-title">额外费用明细（RPA 抓取 + 账单导入 + 手动录入）</div>
        <div v-if="expenses.length === 0" class="chart-empty">
          暂无费用记录。点击右上角「触发 RPA 抓取」自动获取、「+ 手动录入费用」，或在基础配置中导入汇总账单。
        </div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>月份</th>
              <th>店铺</th>
              <th>类别</th>
              <th>子类</th>
              <th class="num">金额</th>
              <th>来源</th>
              <th>备注</th>
              <th class="ops">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in expenses" :key="row.id">
              <td>{{ row.period_month }}</td>
              <td>{{ row.store }} 店</td>
              <td>{{ categoryLabel(row.category) }}</td>
              <td>{{ row.sub_category || '—' }}</td>
              <td class="num">¥{{ fmt(row.amount) }}</td>
              <td>
                <span class="tag" :class="sourceTagClass(row.source)">
                  {{ sourceLabel(row.source) }}
                </span>
              </td>
              <td class="note">{{ row.note || '—' }}</td>
              <td class="ops">
                <button class="btn-link" @click="startEdit(row)">编辑</button>
                <button class="btn-link danger" @click="removeExpense(row.id)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- ── RPA 触发弹窗 ─────────────────────────────────────── -->
    <div v-if="showTrigger" class="modal-mask" @click.self="showTrigger = false">
      <div class="modal">
        <div class="modal-title">触发 RPA 抓取</div>
        <div class="modal-body">
          <label class="form-label">
            平台账号
            <select v-model="triggerForm.accountId" class="form-input">
              <option v-for="a in accounts" :key="a.id" :value="String(a.id)">
                {{ a.account_label }}（{{ a.platform === 'qianniu' ? '千牛' : '阿里妈妈' }} · {{ a.username }} · {{ a.store }} 店）
              </option>
            </select>
          </label>

          <div class="form-label">
            要拉取的数据
            <div class="dataset-list" v-if="selectedPlatform">
              <label v-for="ds in selectedPlatform.datasets" :key="ds.key" class="dataset-item">
                <input type="checkbox" :value="ds.key" v-model="triggerForm.datasets" />
                <span>{{ ds.label }}</span>
              </label>
            </div>
            <div v-else class="hint">请先选择账号</div>
          </div>

          <label class="form-label">
            账期月份（可选，留空则抓取页面当前账期）
            <input v-model="triggerForm.periodMonth" type="text" placeholder="YYYY-MM" maxlength="7" class="form-input" />
          </label>

          <div class="hint">
            抓取会在本机弹出浏览器窗口。若出现滑块 / 短信验证，请在窗口中手动完成，任务会等待
            {{ 300 }} 秒。
          </div>

          <div v-if="triggerError" class="form-error">{{ triggerError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn-ghost" @click="showTrigger = false">取消</button>
          <button class="btn-primary" :disabled="triggering" @click="submitTrigger">
            {{ triggering ? '创建中…' : '开始抓取' }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── 任务日志弹窗 ─────────────────────────────────────── -->
    <div v-if="showTaskLog" class="modal-mask" @click.self="showTaskLog = false">
      <div class="modal modal--wide">
        <div class="modal-title">
          抓取任务 #{{ watchingTaskId }}
          <span class="task-status" :class="'ts-' + (watchingTask?.status ?? 'pending')">
            {{ sourceLabels[watchingTask?.status] ?? watchingTask?.status }}
          </span>
          <span v-if="watchingTask?.progress" class="task-progress">{{ watchingTask.progress }}%</span>
        </div>
        <pre class="task-log">{{ watchingTask?.log || '（暂无日志）' }}</pre>
        <div v-if="watchingTask?.error_message" class="form-error">{{ watchingTask.error_message }}</div>
        <div class="modal-footer">
          <button
            v-if="['pending','running'].includes(watchingTask?.status)"
            class="btn-ghost"
            @click="doCancelTask"
          >取消任务</button>
          <button class="btn-primary" @click="showTaskLog = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- ── 费用录入弹窗 ─────────────────────────────────────── -->
    <div v-if="showExpenseForm" class="modal-mask" @click.self="showExpenseForm = false">
      <div class="modal">
        <div class="modal-title">{{ editingId ? '编辑费用' : '手动录入费用' }}</div>
        <div class="modal-body">
          <div class="form-grid">
            <label class="form-label">
              店铺
              <select v-model="expenseForm.store" class="form-input" :disabled="!!editingId">
                <option :value="1">1 店</option>
                <option :value="2">2 店</option>
              </select>
            </label>
            <label class="form-label">
              月份
              <input v-model="expenseForm.period_month" type="text" placeholder="YYYY-MM" maxlength="7" class="form-input" :disabled="!!editingId" />
            </label>
            <label class="form-label">
              类别
              <select v-model="expenseForm.category" class="form-input" :disabled="!!editingId">
                <option v-for="o in CATEGORY_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </label>
            <label class="form-label">
              子类（可选）
              <input v-model="expenseForm.sub_category" type="text" placeholder="如：直通车" class="form-input" :disabled="!!editingId" />
            </label>
            <label class="form-label">
              金额（元）
              <input v-model="expenseForm.amount" type="number" min="0" step="0.01" class="form-input" />
            </label>
            <label class="form-label form-label--full">
              备注
              <input v-model="expenseForm.note" type="text" class="form-input" />
            </label>
          </div>
          <div v-if="expenseError" class="form-error">{{ expenseError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn-ghost" @click="showExpenseForm = false">取消</button>
          <button class="btn-primary" @click="saveExpense">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pure-profit { max-width: 1280px; margin: 0 auto; padding: 24px; }

.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.page-title { margin-bottom: 4px; }
.page-sub { font-size: 12.5px; color: var(--text-muted); margin: 0; }

.filter-row { display: flex; gap: 16px; align-items: center; margin-bottom: 20px; flex-wrap: wrap; }
.filter-label { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text-muted); }

.month-input {
  border: 1px solid var(--border); border-radius: 8px; padding: 5px 10px;
  font-size: 14px; outline: none; background: var(--surface);
  box-shadow: var(--shadow-inset); cursor: pointer;
}

/* ── Buttons ── */
.btn-primary {
  border: none; border-radius: 9999px; padding: 8px 18px; font-size: 13.5px; font-weight: 500;
  color: #fff; background: linear-gradient(180deg, #3b82f6, #2563eb); cursor: pointer;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25); transition: filter 0.15s;
}
.btn-primary:hover { filter: brightness(1.06); }
.btn-primary:disabled { opacity: 0.55; cursor: not-allowed; }

.btn-ghost {
  border: 1px solid var(--border); border-radius: 9999px; padding: 7px 16px;
  font-size: 13px; font-weight: 500; color: var(--text-muted); background: var(--surface);
  cursor: pointer; transition: color 0.15s, background 0.15s;
}
.btn-ghost:hover { color: var(--text); background: var(--bg-subtle); }

.btn-link {
  border: none; background: none; padding: 2px 6px; font-size: 12.5px;
  color: #2563eb; cursor: pointer; border-radius: 6px;
}
.btn-link:hover { background: rgba(37, 99, 235, 0.08); }
.btn-link.danger { color: #dc2626; }
.btn-link.danger:hover { background: rgba(220, 38, 38, 0.08); }

/* ── Source chips ── */
.source-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
.source-chip {
  display: flex; align-items: center; gap: 8px; padding: 7px 14px; border-radius: 9999px;
  font-size: 12.5px; background: var(--surface); border: 1px solid var(--border-subtle);
}
.src-name { font-weight: 500; color: var(--text); }
.src-status { font-weight: 500; }
.src-meta { color: var(--text-muted); font-size: 11.5px; }
.src-ok .src-status { color: var(--success); }
.src-fail .src-status { color: var(--danger); }
.src-warn .src-status { color: var(--warning); }
.src-running .src-status { color: #2563eb; }
.src-idle .src-status { color: var(--text-muted); }

/* ── KPI ── */
.kpi-section { margin-bottom: 24px; }
.kpi-store-label { font-size: 13px; font-weight: 500; color: var(--text-muted); letter-spacing: 0.5px; margin: 12px 0 6px; }
.kpi-total-label { color: var(--text); }

.kpi-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 4px; }
.kpi-grid--8 { grid-template-columns: repeat(4, 1fr); }
.kpi-grid--2 { grid-template-columns: repeat(2, 1fr); margin-top: 12px; }

.kpi-card {
  background: var(--surface); border-radius: 16px; padding: 16px 20px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.kpi-card--total { box-shadow: var(--shadow-card); }
.kpi-label { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; letter-spacing: 0.12px; }
.kpi-value { font-size: 20px; font-weight: 300; color: var(--text); letter-spacing: -0.3px; }
.kpi-mom { font-size: 11.5px; color: var(--text-muted); margin-top: 4px; }

.kpi-profit .kpi-value { color: var(--success); }
.kpi-loss .kpi-value { color: var(--danger); }
.kpi-refund .kpi-value { color: var(--warning); }
.kpi-fee .kpi-value { color: #8b5cf6; }

/* ── Charts & tables ── */
.chart-block, .table-block {
  background: var(--surface); border-radius: 16px; padding: 20px 24px;
  margin-bottom: 20px; box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.chart-title { font-size: 14px; font-weight: 500; color: var(--text); letter-spacing: 0.14px; margin-bottom: 12px; }
.chart-sub { margin: -6px 0 10px; font-size: 12px; line-height: 1.7; color: var(--text-muted); }
.chart-empty { height: 120px; display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-size: 14px; }

.insight-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin-top: 8px;
}
.insight-card {
  padding: 12px 14px;
  border-radius: 12px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
}
.insight-label { font-size: 11.5px; color: var(--text-muted); margin-bottom: 6px; }
.insight-main { display: flex; align-items: baseline; gap: 8px; }
.insight-value { font-size: 18px; font-weight: 500; color: var(--text); font-variant-numeric: tabular-nums; }
.insight-delta { font-size: 12px; font-variant-numeric: tabular-nums; }
.insight-delta.good { color: #047857; }
.insight-delta.bad { color: #b91c1c; }

.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th, .data-table td { padding: 9px 10px; text-align: left; border-bottom: 1px solid var(--border-subtle); white-space: nowrap; }
.data-table th { font-size: 12px; font-weight: 500; color: var(--text-muted); }
.data-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.data-table .ops { text-align: right; }
.data-table .warn { color: var(--warning); }
.data-table .profit { color: var(--success); font-weight: 500; }
.data-table .loss { color: var(--danger); font-weight: 500; }
.data-table .note { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-muted); }

.tag { padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 500; }
.tag-rpa { background: rgba(37, 99, 235, 0.1); color: #2563eb; }
.tag-xlsx { background: rgba(5, 150, 105, 0.1); color: #047857; }
.tag-manual { background: var(--bg-subtle); color: var(--text-muted); }

.status-msg { text-align: center; padding: 40px; color: var(--text-muted); }
.error-msg { padding: 10px 16px; color: #b91c1c; border: 1px solid #fecaca; border-radius: 10px; background: #fef2f2; font-size: 13px; }

/* ── Modals ── */
.modal-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 24px;
}
.modal {
  background: var(--surface); border-radius: 18px; width: 520px; max-width: 100%;
  max-height: 88vh; display: flex; flex-direction: column;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.25);
}
.modal--wide { width: 760px; }
.modal-title { font-size: 15px; font-weight: 600; padding: 18px 24px 12px; display: flex; align-items: center; gap: 10px; }
.modal-body { padding: 0 24px 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }
.modal-footer { padding: 14px 24px 20px; display: flex; justify-content: flex-end; gap: 10px; }

.form-label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--text-muted); }
.form-label--full { grid-column: 1 / -1; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-input {
  border: 1px solid var(--border); border-radius: 9px; padding: 7px 11px;
  font-size: 13.5px; outline: none; background: var(--surface); color: var(--text);
}
.form-input:focus { border-color: rgba(37, 99, 235, 0.5); }
.form-input:disabled { background: var(--bg-subtle); color: var(--text-muted); }

.dataset-list { display: flex; flex-direction: column; gap: 6px; }
.dataset-item { display: flex; align-items: center; gap: 8px; font-size: 13.5px; color: var(--text); }

.hint { font-size: 12px; color: var(--text-muted); line-height: 1.6; }
.form-error { font-size: 12.5px; color: #b91c1c; background: #fef2f2; border: 1px solid #fecaca; border-radius: 9px; padding: 8px 12px; }

.task-status { font-size: 12px; font-weight: 500; padding: 2px 10px; border-radius: 9999px; background: var(--bg-subtle); }
.ts-success { color: var(--success); }
.ts-failed, .ts-cancelled { color: var(--danger); }
.ts-need_verify { color: var(--warning); }
.ts-running, .ts-pending { color: #2563eb; }
.task-progress { font-size: 12px; color: var(--text-muted); }

.task-log {
  margin: 0 24px 16px; padding: 14px 16px; background: #0f172a; color: #e2e8f0;
  border-radius: 12px; font-size: 12px; line-height: 1.65; overflow: auto;
  max-height: 46vh; white-space: pre-wrap; word-break: break-all; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
