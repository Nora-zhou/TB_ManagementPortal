<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart, BarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  LegendScrollComponent,
  GridComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import {
  fetchAvailableMonths,
  fetchSupplierEvaluation,
  fetchSupplierEvaluationDetail,
  fetchRefundOrders,
} from '../api/purchase_orders.js'

use([CanvasRenderer, RadarChart, BarChart, TitleComponent, TooltipComponent, LegendComponent, LegendScrollComponent, GridComponent])

const router = useRouter()

const availableMonths = ref([])
const startMonth = ref('')
const endMonth = ref('')
const loading = ref(false)
const error = ref(null)
const suppliers = ref([])
const sortKey = ref('total_amount')  // default: sort by total amount desc
const sortDir = ref('desc')          // 'asc' | 'desc'

function setSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
}

function sortIcon(key) {
  if (sortKey.value !== key) return '⇅'
  return sortDir.value === 'desc' ? '↓' : '↑'
}

const sortedSuppliers = computed(() => {
  const list = [...suppliers.value]
  const dir = sortDir.value === 'desc' ? 1 : -1
  list.sort((a, b) => {
    const va = a[sortKey.value] ?? -Infinity
    const vb = b[sortKey.value] ?? -Infinity
    return va < vb ? dir : va > vb ? -dir : 0
  })
  return list
})
const expandedSet = ref(new Set())
const detailLoading = ref({})
const detailError = ref({})
const detailData = ref({})

function monthKey(m) {
  return `${m.year}-${String(m.month).padStart(2, '0')}`
}

function badgeStyle(score) {
  if (score === null || score === undefined) return { color: '#888' }
  if (score >= 85) return { color: 'green' }
  if (score >= 65) return { color: '#409eff' }
  if (score >= 45) return { color: '#e6a23c' }
  return { color: '#f56c6c' }
}

function trendIndicator(score) {
  if (score === null || score === undefined) return '—'
  if (score >= 70) return '↓'
  return '↑'
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

async function loadEvaluation() {
  loading.value = true
  error.value = null
  expandedSet.value = new Set()
  detailData.value = {}
  detailError.value = {}

  const params = {}
  if (startMonth.value) params.startMonth = startMonth.value
  if (endMonth.value) params.endMonth = endMonth.value

  try {
    const data = await fetchSupplierEvaluation(params)
    suppliers.value = data.suppliers
  } catch (e) {
    error.value = e?.detail || '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  loadEvaluation()
}

async function toggleDetail(sellerName) {
  const current = expandedSet.value
  if (current.has(sellerName)) {
    const next = new Set(current)
    next.delete(sellerName)
    expandedSet.value = next
    return
  }
  const next = new Set(current)
  next.add(sellerName)
  expandedSet.value = next

  if (detailData.value[sellerName]) return

  detailLoading.value[sellerName] = true
  detailError.value[sellerName] = null

  const params = {}
  if (startMonth.value) params.startMonth = startMonth.value
  if (endMonth.value) params.endMonth = endMonth.value

  try {
    const data = await fetchSupplierEvaluationDetail(sellerName, params)
    detailData.value[sellerName] = data
  } catch (e) {
    detailError.value[sellerName] = e?.detail || '加载详情失败'
  } finally {
    detailLoading.value[sellerName] = false
  }
}

function radarOption(detail) {
  const dimKeys = ['completion_rate', 'price_stability', 'activity_rate', 'price_trend_score']
  const dimLabels = ['完成率', '价格稳定性', '活跃度', '价格走势']
  return {
    title: { text: '维度得分雷达图', left: 'center', textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'item' },
    radar: {
      indicator: dimLabels.map(name => ({ name, max: 100 })),
      radius: '65%',
    },
    series: [{
      type: 'radar',
      data: [{
        name: detail.seller_name,
        value: dimKeys.map(k => detail.dimensions[k] ?? 0),
        areaStyle: { opacity: 0.3 },
      }],
    }],
  }
}

function returnRateOption(detail) {
  if (!detail.top_return_goods || detail.top_return_goods.length === 0) return {}
  // Reverse so highest count appears at top of horizontal bar chart
  const goods = [...detail.top_return_goods].reverse()
  const titles = goods.map(g => g.goods_title.length > 22 ? g.goods_title.slice(0, 22) + '…' : g.goods_title)
  const fullTitles = goods.map(g => g.goods_title)
  const counts = goods.map(g => g.return_count)
  const rates = goods.map(g => g.return_rate)
  return {
    title: { text: '退货量 Top 5 商品', textStyle: { fontSize: 13 } },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        const i = params[0].dataIndex
        return `${fullTitles[i]}<br/>退货数量：${counts[i]} 件<br/>退货率：${rates[i]}%（${goods[i].return_count}/${goods[i].total_count}）`
      },
    },
    grid: { left: '2%', right: '12%', top: '12%', bottom: '5%', containLabel: true },
    xAxis: { type: 'value', name: '退货数量（件）', minInterval: 1 },
    yAxis: { type: 'category', data: titles, axisLabel: { fontSize: 12 } },
    series: [{
      type: 'bar',
      data: counts,
      cursor: 'pointer',
      label: {
        show: true,
        position: 'right',
        formatter: params => `${params.value}件  (${rates[params.dataIndex]}%)`,
      },
      itemStyle: { color: '#f56c6c' },
    }],
  }
}

// ── Refund order modal ───────────────────────────────────────────────────
const modal = ref({ visible: false, loading: false, error: null, title: '', orders: [] })

function onBarClick(sellerName, detail, params) {
  if (params.componentType !== 'series') return
  const goods = [...detail.top_return_goods].reverse()
  const item = goods[params.dataIndex]
  if (!item) return
  openRefundModal(sellerName, item.goods_title)
}

async function openRefundModal(sellerName, goodsTitle) {
  modal.value = { visible: true, loading: true, error: null, title: goodsTitle, orders: [] }
  const params = {}
  if (startMonth.value) params.startMonth = startMonth.value
  if (endMonth.value) params.endMonth = endMonth.value
  try {
    const data = await fetchRefundOrders(sellerName, goodsTitle, params)
    modal.value.orders = data
  } catch (e) {
    modal.value.error = e?.detail || '加载失败'
  } finally {
    modal.value.loading = false
  }
}

onMounted(async () => {
  await loadMonths()
  await loadEvaluation()
})
</script>

<template>
  <div class="supplier-evaluation">
    <div class="eval-header">
      <button class="btn-back-eval" @click="router.push('/suppliers')">← 返回供应商汇总</button>
      <h2>供应商综合评估</h2>
    </div>

    <div class="filter-row">
      <label>开始月份：
        <select v-model="startMonth" @change="onFilterChange">
          <option value="">全部</option>
          <option v-for="m in availableMonths" :key="monthKey(m)" :value="monthKey(m)">
            {{ monthKey(m) }}
          </option>
        </select>
      </label>
      <label>结束月份：
        <select v-model="endMonth" @change="onFilterChange">
          <option value="">全部</option>
          <option v-for="m in availableMonths" :key="monthKey(m)" :value="monthKey(m)">
            {{ monthKey(m) }}
          </option>
        </select>
      </label>
    </div>

    <div v-if="loading" class="status-msg">加载中…</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>
    <div v-else-if="suppliers.length === 0" class="status-msg">暂无供应商数据</div>

    <table v-else class="eval-table">
      <thead>
        <tr>
          <th>#</th>
          <th>供应商</th>
          <th class="sortable" @click="setSort('score')">综合得分 {{ sortIcon('score') }}</th>
          <th>标签</th>
          <th class="sortable" @click="setSort('completion_rate')">完成率 {{ sortIcon('completion_rate') }}</th>
          <th class="sortable" @click="setSort('price_stability')">价格稳定性 {{ sortIcon('price_stability') }}</th>
          <th class="sortable" @click="setSort('activity_rate')">活跃度 {{ sortIcon('activity_rate') }}</th>
          <th>价格走势</th>
          <th class="sortable" @click="setSort('total_amount')">总采购额 {{ sortIcon('total_amount') }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(s, idx) in sortedSuppliers" :key="s.seller_name">
          <tr>
            <td>{{ idx + 1 }}</td>
            <td>{{ s.seller_name }}</td>
            <td>
              <span class="score-badge" :style="badgeStyle(s.score)">
                {{ s.score !== null ? s.score.toFixed(1) : '—' }}
              </span>
            </td>
            <td><span :style="badgeStyle(s.score)">{{ s.label }}</span></td>
            <td>{{ s.completion_rate !== null ? s.completion_rate.toFixed(1) : '--' }}</td>
            <td>{{ s.price_stability !== null ? s.price_stability.toFixed(1) : '--' }}</td>
            <td>{{ s.activity_rate !== null ? s.activity_rate.toFixed(1) : '--' }}</td>
            <td>{{ trendIndicator(s.price_trend_score) }}</td>
            <td>¥{{ s.total_amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</td>
            <td>
              <button @click="toggleDetail(s.seller_name)">
                {{ expandedSet.has(s.seller_name) ? '收起' : '查看详情' }}
              </button>
            </td>
          </tr>
          <tr v-if="expandedSet.has(s.seller_name)" class="detail-row">
            <td colspan="10">
              <div v-if="detailLoading[s.seller_name]" class="status-msg">加载详情中…</div>
              <div v-else-if="detailError[s.seller_name]" class="error-msg">{{ detailError[s.seller_name] }}</div>
              <div v-else-if="detailData[s.seller_name]" class="detail-charts">
                <v-chart
                  :option="radarOption(detailData[s.seller_name])"
                  autoresize
                  style="height:320px;width:100%;max-width:480px;"
                />
                <div style="flex:1;min-width:0;">
                  <v-chart
                    v-if="detailData[s.seller_name].top_return_goods?.length"
                    :option="returnRateOption(detailData[s.seller_name])"
                    autoresize
                    style="height:320px;width:100%;"
                    @click="(p) => onBarClick(s.seller_name, detailData[s.seller_name], p)"
                  />
                  <div v-else class="no-data-msg">
                    <span>退货率 Top 5 商品</span>
                    <p>No Data</p>
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>

    <!-- Refund order modal -->
    <div v-if="modal.visible" class="modal-overlay" @click.self="modal.visible = false">
      <div class="modal-dialog">
        <div class="modal-header">
          <h3>退款订单 &mdash; {{ modal.title }}</h3>
          <button class="modal-close" @click="modal.visible = false">×</button>
        </div>
        <div class="modal-body">
          <div v-if="modal.loading" class="status-msg">加载中…</div>
          <div v-else-if="modal.error" class="error-msg">{{ modal.error }}</div>
          <div v-else-if="modal.orders.length === 0" class="status-msg">暂无退款订单</div>
          <table v-else class="refund-table">
            <thead>
              <tr>
                <th>订单号</th>
                <th>状态</th>
                <th>实付金额</th>
                <th>数量</th>
                <th>单价</th>
                <th>下单日期</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="o in modal.orders" :key="o.order_id">
                <td class="order-id">{{ o.order_id }}</td>
                <td><span :class="['status-tag', o.status === '退款中' ? 'tag-refunding' : 'tag-closed']">{{ o.status }}</span></td>
                <td>￥{{ o.paid_amount.toFixed(2) }}</td>
                <td>{{ o.quantity ?? '—' }}</td>
                <td>{{ o.unit_price != null ? '￥' + o.unit_price.toFixed(2) : '—' }}</td>
                <td>{{ o.created_at ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.supplier-evaluation {
  padding: 16px;
}

.eval-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.btn-back-eval {
  padding: 6px 14px;
  background: #f0f0f0;
  border: 1px solid #ccc;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-back-eval:hover {
  background: #ddd;
}

.filter-row {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
  font-size: 14px;
}

.filter-row select {
  margin-left: 6px;
  padding: 4px 8px;
}

.eval-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.eval-table th,
.eval-table td {
  border: 1px solid #eee;
  padding: 8px 10px;
  text-align: center;
}

.eval-table th {
  background: #f5f7fa;
  font-weight: 600;
}

.sortable {
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.sortable:hover {
  background: #eaedf1;
}

.score-badge {
  font-weight: 700;
  font-size: 15px;
}

.detail-row td {
  background: #fafafa;
  text-align: left;
}

.detail-charts {
  display: flex;
  gap: 16px;
  padding: 12px;
  flex-wrap: wrap;
  align-items: flex-start;
}

.no-data-msg {
  height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #bbb;
  font-size: 13px;
  border: 1px dashed #e0e0e0;
  border-radius: 4px;
}

.no-data-msg span {
  font-size: 13px;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
}

.no-data-msg p {
  font-size: 20px;
  color: #ccc;
  margin: 0;
}

.status-msg {
  text-align: center;
  color: #888;
  padding: 40px;
}

.error-msg {
  text-align: center;
  color: #c00;
  padding: 40px;
}

/* ── Refund order modal ─────────────────────────────────────────────────── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-dialog {
  background: #fff;
  border-radius: 12px;
  width: min(760px, 95vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: rgba(0,0,0,0.2) 0px 8px 32px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
}

.modal-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: calc(100% - 40px);
}

.modal-close {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: none;
  background: #f0f0f0;
  border-radius: 50%;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-close:hover { background: #e0e0e0; }

.modal-body {
  overflow-y: auto;
  padding: 16px 20px;
}

.refund-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.refund-table th,
.refund-table td {
  border: 1px solid #eee;
  padding: 7px 10px;
  text-align: center;
}

.refund-table th {
  background: #f5f7fa;
  font-weight: 600;
}

.order-id {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  color: #555;
}

.status-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 500;
}

.tag-refunding { background: #fff3e0; color: #e6a23c; }
.tag-closed    { background: #fef0f0; color: #f56c6c; }
</style>
