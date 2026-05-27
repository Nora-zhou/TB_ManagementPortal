<template>
  <div v-if="snapshots.length >= 2">
    <v-chart class="chart" :option="chartOption" autoresize />
  </div>
  <div v-else class="no-data">
    价格历史数据不足，请等待更多快照记录后再查看走势
  </div>
</template>

<script setup>
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer])

const props = defineProps({
  snapshots: { type: Array, default: () => [] },
  alertLow: { type: Number, default: null },
  alertHigh: { type: Number, default: null },
})

const chartOption = computed(() => {
  const dates = props.snapshots.map(s =>
    new Date(s.recorded_at).toLocaleString('zh-CN', { hour12: false })
  )
  const prices = props.snapshots.map(s => s.price)

  const markLines = []
  if (props.alertLow != null) {
    markLines.push({ yAxis: props.alertLow, name: `下限 ¥${props.alertLow}`, lineStyle: { color: '#cf1322' } })
  }
  if (props.alertHigh != null) {
    markLines.push({ yAxis: props.alertHigh, name: `上限 ¥${props.alertHigh}`, lineStyle: { color: '#d46b08' } })
  }

  return {
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const p = params[0]
        return `${p.axisValue}<br/>价格：¥${p.value.toFixed(2)}`
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: dates, boundaryGap: false },
    yAxis: { type: 'value', name: '价格（元）', axisLabel: { formatter: '¥{value}' } },
    series: [{
      type: 'line',
      data: prices,
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      markLine: markLines.length ? { data: markLines, label: { show: true } } : undefined,
    }],
  }
})
</script>

<style scoped>
.chart { width: 100%; height: 360px; }
.no-data { padding: 2rem; text-align: center; color: #999; background: #fafafa; border-radius: 6px; }
</style>
