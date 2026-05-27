<template>
  <div class="order-price-chart">
    <div class="chart-header">
      <h3>订单实付价格走势</h3>
      <div class="controls">
        <div class="type-toggle">
          <button :class="{ active: chartType === 'scatter' }" @click="chartType = 'scatter'">散点图</button>
          <button :class="{ active: chartType === 'line' }" @click="chartType = 'line'">折线图</button>
        </div>
        <div class="range-buttons">
          <button
            v-for="opt in rangeOptions"
            :key="opt.value"
            :class="{ active: selectedDays === opt.value }"
            @click="selectDays(opt.value)"
          >{{ opt.label }}</button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="state-box">加载中…</div>
    <div v-else-if="errorMsg" class="state-box error">{{ errorMsg }}</div>
    <div v-else-if="noData" class="state-box empty">{{ emptyText }}</div>
    <div v-else>
      <div v-if="truncated" class="truncate-notice">
        ⚠️ 数据已截断，仅显示最近 1000 条记录
      </div>
      <div ref="chartEl" class="chart-area"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import * as echarts from 'echarts'
import * as ecStat from 'echarts-stat'
import { fetchOrderPriceSeries } from '../api/products.js'

const props = defineProps({
  productId: { type: Number, required: true },
  days: { type: [String, Number], default: 90 },
})

echarts.registerTransform(ecStat.transform.regression)

// T018: SKU color palette (10 colors, cycles when exceeded)
const SKU_COLORS = [
  '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
  '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#a5a5a5',
]

const rangeOptions = [
  { label: '近 30 天', value: '30' },
  { label: '近 90 天', value: '90' },
  { label: '全部', value: 'all' },
]

const selectedDays = ref(String(props.days))
const chartType = ref('scatter')   // T018: 'scatter' | 'line'
const loading = ref(false)
const errorMsg = ref(null)
const seriesData = ref(null)
const chartEl = ref(null)
let chartInstance = null

const noData = computed(() => seriesData.value !== null && seriesData.value.total === 0)
const truncated = computed(() => seriesData.value?.truncated === true)

// T014: distinguish "suborder table empty" vs "no match for this product"
const globalEmpty = ref(false)

const emptyText = computed(() => {
  if (globalEmpty.value) return '暂无订单数据，请先导入订单文件'
  return '暂无匹配订单数据，无法展示价格走势'
})

// T018: build SKU → color map based on first-appearance order in points
const skuColorMap = computed(() => {
  const points = seriesData.value?.points ?? []
  const map = {}
  let idx = 0
  for (const p of points) {
    const key = p.product_attr ?? '未知规格'
    if (!(key in map)) map[key] = SKU_COLORS[idx++ % SKU_COLORS.length]
  }
  return map
})

async function loadData() {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  loading.value = true
  errorMsg.value = null
  seriesData.value = null
  try {
    const days = selectedDays.value === 'all' ? undefined : selectedDays.value
    seriesData.value = await fetchOrderPriceSeries(props.productId, days)
    // T014: if all-time query has 0 results, mark globalEmpty
    if (!days && seriesData.value.total === 0) {
      globalEmpty.value = true
    } else if (seriesData.value.total > 0) {
      globalEmpty.value = false
    }
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}

function buildChart() {
  if (!chartEl.value || !seriesData.value || seriesData.value.total === 0) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartEl.value)
  }

  const points = seriesData.value.points
  const colorMap = skuColorMap.value
  const isLine = chartType.value === 'line'

  // Build flat data rows for regression (all points)
  const allRows = points.map(p => {
    const unitPrice = p.buyer_paid / Math.max(p.quantity, 1)
    return [p.created_at, unitPrice, p.buyer_paid, p.quantity, p.product_attr ?? '未知规格', p.sub_order_id]
  })

  // T018/T019: group by SKU
  const skuGroups = {}
  for (const row of allRows) {
    const sku = row[4]
    if (!skuGroups[sku]) skuGroups[sku] = []
    skuGroups[sku].push(row)
  }
  const skuNames = Object.keys(skuGroups)

  // T018/T019: one series per SKU
  const mainSeries = skuNames.map(sku => {
    const rawData = skuGroups[sku]
    // T019: line mode sorts each SKU group by time
    const data = isLine
      ? [...rawData].sort((a, b) => new Date(a[0]) - new Date(b[0]))
      : rawData
    return {
      name: sku,
      type: isLine ? 'line' : 'scatter',
      data,
      encode: { x: 0, y: 1 },
      symbolSize: 6,
      showSymbol: true,
      itemStyle: { color: colorMap[sku], opacity: isLine ? 1 : 0.75 },
      lineStyle: isLine ? { color: colorMap[sku], width: 2 } : undefined,
    }
  })

  // Trend line: uses regression transform on all data, excluded from legend
  const trendSeries = {
    name: '线性趋势',
    type: 'line',
    datasetIndex: 1,
    encode: { x: 0, y: 1 },
    symbol: 'none',
    lineStyle: { color: '#bbb', width: 2, type: 'dashed' },
    tooltip: { show: false },
    legendHoverLink: false,
    silent: true,
  }

  // T020: tooltip formatter with SKU color block
  function tooltipFormatter(params) {
    if (params.seriesName === '线性趋势') return null
    const d = params.data
    const dt = new Date(d[0]).toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
    const unitPrice = Number(d[1]).toFixed(2)
    const qty = d[3]
    const attr = d[4] ? `<br/>规格：${d[4]}` : ''
    const colorBlock = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${params.color};margin-right:5px;vertical-align:middle;"></span>`
    return `${colorBlock}<b>${params.seriesName}</b><br/>时间：${dt}<br/>单件均价：¥${unitPrice}<br/>购买数量：${qty}${attr}`
  }

  const option = {
    dataset: [
      { source: allRows },
      { transform: { type: 'ecStat:regression', config: { method: 'linear' } } },
    ],
    legend: {
      type: 'scroll',
      bottom: 0,
      data: skuNames,
    },
    tooltip: {
      trigger: 'item',
      formatter: tooltipFormatter,
    },
    xAxis: { type: 'time', name: '订单创建时间' },
    yAxis: { type: 'value', name: '单件均价（元）' },
    series: [...mainSeries, trendSeries],
    grid: { left: 60, right: 20, bottom: 60, top: 40 },
  }

  chartInstance.setOption(option, { notMerge: true })
}

function handleResize() {
  chartInstance?.resize()
}

function selectDays(val) {
  selectedDays.value = val
}

watch(selectedDays, () => loadData())
// T018/T019: rebuild chart on chartType change (no network request)
watch(chartType, async () => {
  if (seriesData.value && seriesData.value.total > 0) {
    await nextTick()
    buildChart()
  }
})
watch(
  () => seriesData.value,
  async () => {
    if (seriesData.value && seriesData.value.total > 0) {
      await nextTick()
      buildChart()
    }
  },
)
watch(() => props.productId, () => loadData())

onMounted(() => {
  loadData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  chartInstance?.dispose()
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.order-price-chart {
  margin-top: 24px;
}
.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.chart-header h3 {
  margin: 0;
  font-size: 1rem;
}
.controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.type-toggle {
  display: flex;
  border: 1px solid #ddd;
  border-radius: 4px;
  overflow: hidden;
}
.type-toggle button {
  padding: 4px 12px;
  border: none;
  background: #fff;
  cursor: pointer;
  font-size: 0.85rem;
  border-right: 1px solid #ddd;
}
.type-toggle button:last-child {
  border-right: none;
}
.type-toggle button.active {
  background: #409eff;
  color: #fff;
}
.range-buttons {
  display: flex;
  gap: 4px;
}
.range-buttons button {
  padding: 4px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 0.85rem;
}
.range-buttons button.active {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
}
.chart-area {
  width: 100%;
  height: 340px;
}
.state-box {
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #888;
  background: #fafafa;
  border: 1px dashed #e0e0e0;
  border-radius: 6px;
}
.state-box.error {
  color: #dc2626;
  background: #fef2f2;
  border-color: #fca5a5;
}
.state-box.empty {
  color: #6b7280;
}
.truncate-notice {
  padding: 6px 12px;
  background: #fffbeb;
  border: 1px solid #fcd34d;
  border-radius: 4px;
  font-size: 0.85rem;
  color: #92400e;
  margin-bottom: 8px;
}
</style>
