<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getOrders } from '../api/orders'

const router = useRouter()

const STATUS_OPTIONS = [
  '',
  '交易成功',
  '交易关闭',
  '卖家已发货，等待买家确认',
  '买家已付款,等待卖家发货',
  '等待买家付款',
  '卖家部分发货',
]

const STATUS_COLORS = {
  '交易成功': '#4caf50',
  '交易关闭': '#9e9e9e',
  '卖家已发货，等待买家确认': '#2196f3',
  '买家已付款,等待卖家发货': '#ff9800',
  '等待买家付款': '#ff5722',
  '卖家部分发货': '#9c27b0',
}

const items = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref(null)

const page = ref(1)
const pageSize = 5000  // load all at once; group pagination is done client-side
const groupPage = ref(1)
const groupPageSize = 30
const storeFilter = ref(null)
const statusFilter = ref('')
const keyword = ref('')
const startDate = ref('')
const endDate = ref('')
const sortBy = ref('created_at')
const sortDir = ref('desc')

const expandedDates = ref(new Set())

let debounceTimer = null

function truncate(str, n) {
  if (!str) return ''
  return str.length <= n ? str : str.slice(0, n) + '…'
}

function toggleDate(date) {
  const s = new Set(expandedDates.value)
  if (s.has(date)) s.delete(date)
  else s.add(date)
  expandedDates.value = s
}

const allGroups = computed(() => {
  const map = {}
  for (const item of items.value) {
    const date = item.created_at?.slice(0, 10) ?? '未知日期'
    if (!map[date]) map[date] = []
    map[date].push(item)
  }
  return Object.entries(map)
    .sort(([a], [b]) => sortDir.value === 'desc' ? b.localeCompare(a) : a.localeCompare(b))
    .map(([date, orders]) => ({
      date,
      orders,
      totalPaid: orders.reduce((s, o) => s + (o.buyer_paid || 0), 0),
      totalRefund: orders.reduce((s, o) => s + (o.refund_amount || 0), 0),
      count: orders.length,
    }))
})

const totalGroupPages = computed(() => Math.ceil(allGroups.value.length / groupPageSize))

const groupedItems = computed(() => {
  const start = (groupPage.value - 1) * groupPageSize
  return allGroups.value.slice(start, start + groupPageSize)
})

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await getOrders({
      page: page.value,
      page_size: pageSize,
      status: statusFilter.value || undefined,
      q: keyword.value || undefined,
      start_date: startDate.value || undefined,
      end_date: endDate.value || undefined,
      sort_by: sortBy.value,
      sort_dir: sortDir.value,
      store: storeFilter.value ?? undefined,
    })
    items.value = res.items
    total.value = res.total
  } catch (e) {
    error.value = e?.response?.data?.detail ?? e?.message ?? String(e)
  } finally {
    loading.value = false
  }
}

function resetAndLoad() {
  page.value = 1
  groupPage.value = 1
  expandedDates.value = new Set()
  load()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  startDate.value = ''
  endDate.value = ''
  storeFilter.value = null
  sortDir.value = 'desc'
  resetAndLoad()
}

function onKeywordInput() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(resetAndLoad, 300)
}

watch([statusFilter, startDate, endDate, sortBy, sortDir, storeFilter], resetAndLoad)

onMounted(load)

const grandTotal = computed(() => {
  const paid   = allGroups.value.reduce((s, g) => s + g.totalPaid, 0)
  const refund = allGroups.value.reduce((s, g) => s + g.totalRefund, 0)
  return {
    profit: Math.max(0, paid - refund),
    paid,
    refund,
    orders: allGroups.value.reduce((s, g) => s + g.count, 0),
    days:   allGroups.value.length,
  }
})
</script>

<template>
  <div class="order-list">
    <div class="toolbar">
      <!-- Row 1: title + store tabs -->
      <div class="toolbar-row toolbar-row--top">
        <h2>订单列表</h2>
        <div class="store-filter">
          <button :class="{ active: storeFilter === null }" @click="storeFilter = null; resetAndLoad()">全部</button>
          <button :class="{ active: storeFilter === 1 }" @click="storeFilter = 1; resetAndLoad()">店铺1</button>
          <button :class="{ active: storeFilter === 2 }" @click="storeFilter = 2; resetAndLoad()">店铺2</button>
        </div>
      </div>
      <!-- Row 2: filters + actions -->
      <div class="toolbar-row toolbar-row--filters">
        <input
          v-model="keyword"
          class="input-search"
          placeholder="搜索商品标题…"
          @input="onKeywordInput"
        />
        <select v-model="statusFilter" class="select-status">
          <option value="">全部状态</option>
          <option v-for="s in STATUS_OPTIONS.slice(1)" :key="s" :value="s">{{ s }}</option>
        </select>
        <input v-model="startDate" type="text" placeholder="YYYY-MM-DD" maxlength="10" class="input-date" title="开始日期" />
        <span class="date-sep">~</span>
        <input v-model="endDate" type="text" placeholder="YYYY-MM-DD" maxlength="10" class="input-date" title="结束日期" />
        <select v-model="sortDir" class="select-sort">
          <option value="desc">最新在前</option>
          <option value="asc">最早在前</option>
        </select>
        <div class="filter-actions">
          <button
            v-if="keyword || statusFilter || startDate || endDate"
            class="btn-reset"
            @click="resetFilters"
          >重置</button>
          <button class="btn-import" @click="router.push('/orders/import')">+ 导入订单</button>
        </div>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <!-- Summary bar -->
    <div v-if="allGroups.length" class="summary-bar">
      <span class="summary-item"><span class="summary-label">订单数</span><strong>{{ grandTotal.orders }}</strong></span>
      <span class="summary-sep"></span>
      <span class="summary-item"><span class="summary-label">利润</span><strong>¥{{ grandTotal.profit.toFixed(2) }}</strong></span>
      <span class="summary-sep"></span>
      <span class="summary-item"><span class="summary-label">实付</span><strong>¥{{ grandTotal.paid.toFixed(2) }}</strong></span>
      <span class="summary-sep"></span>
      <span class="summary-item refund-item"><span class="summary-label">退款</span><strong>{{ grandTotal.refund > 0 ? '¥' + grandTotal.refund.toFixed(2) : '—' }}</strong></span>
    </div>

    <!-- Grouped list -->
    <div class="table-wrap">
      <template v-if="groupedItems.length">
        <table class="order-table">
          <thead>
            <tr>
              <th style="width:32px"></th>
              <th>订单编号</th>
              <th>商品标题</th>
              <th class="num">利润</th>
              <th class="num">实付金额</th>
              <th class="num">退款金额</th>
              <th class="num">店铺</th>
            </tr>
          </thead>
          <tbody v-for="group in groupedItems" :key="group.date">
            <!-- Date summary row -->
            <tr class="date-group-row" @click="toggleDate(group.date)">
              <td class="toggle-cell">
                <span class="toggle-icon" :class="{ open: expandedDates.has(group.date) }">▸</span>
              </td>
              <td class="date-label">{{ group.date }}</td>
              <td class="date-count">{{ group.count }} 单</td>
              <td class="num date-stat">¥{{ Math.max(0, group.totalPaid - group.totalRefund).toFixed(2) }}</td>
              <td class="num date-stat">¥{{ group.totalPaid.toFixed(2) }}</td>
              <td class="num" :class="group.totalRefund > 0 ? 'refund' : 'date-muted'">{{ group.totalRefund > 0 ? '¥' + group.totalRefund.toFixed(2) : '—' }}</td>
              <td></td>
            </tr>
            <!-- Detail rows -->
            <template v-if="expandedDates.has(group.date)">
              <tr v-for="item in group.orders" :key="item.id" class="detail-row">
                <td></td>
                <td class="mono">{{ item.order_id?.slice(0, 10) }}…</td>
                <td :title="item.product_title">{{ truncate(item.product_title, 36) }}</td>
                <td class="num">¥{{ Math.max(0, (item.buyer_paid || 0) - (item.refund_amount || 0)).toFixed(2) }}</td>
                <td class="num">¥{{ item.buyer_paid?.toFixed(2) ?? '—' }}</td>
                <td class="num refund">{{ item.refund_amount > 0 ? '¥' + item.refund_amount.toFixed(2) : '—' }}</td>
                <td class="num">店铺{{ item.store ?? 1 }}</td>
              </tr>
            </template>
          </tbody>
        </table>
      </template>
      <div v-else-if="!loading" class="empty-state">
        暂无订单数据，请先<a @click="router.push('/orders/import')">导入订单文件</a>
      </div>
      <div v-if="loading" class="loading-mask">加载中…</div>
    </div>

    <!-- Pagination -->
    <div v-if="totalGroupPages > 1" class="pagination">
      <button :disabled="groupPage <= 1" @click="groupPage--; expandedDates = new Set()">‹ 上一页</button>
      <span>第 {{ groupPage }} / {{ totalGroupPages }} 页（共 {{ allGroups.length }} 天）</span>
      <button :disabled="groupPage >= totalGroupPages" @click="groupPage++; expandedDates = new Set()">下一页 ›</button>
    </div>
    <div v-else-if="allGroups.length > 0" class="pagination-info">共 {{ allGroups.length }} 天 · {{ total }} 条订单</div>
  </div>
</template>

<style scoped>
.order-list { padding: 0; }
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
.toolbar-row--filters {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 10px 16px;
  box-shadow: var(--shadow-soft);
}
.filter-actions { display: flex; gap: 6px; margin-left: auto; }
.btn-import {
  padding: 7px 16px; background: #000; color: #fff;
  border: none; border-radius: 9999px; cursor: pointer;
  font-size: 13px; font-weight: 500;
  box-shadow: var(--shadow-card); transition: background 0.15s;
}
.btn-import:hover { background: #222; }
.input-search, .select-status, .input-date, .select-sort {
  padding: 7px 12px; border: 1px solid var(--border); border-radius: 8px;
  font-size: 13px; background: var(--surface); color: var(--text);
  box-shadow: var(--shadow-inset); outline: none;
}
.input-search { min-width: 180px; }
.input-search:focus, .select-status:focus, .input-date:focus, .select-sort:focus {
  border-color: rgba(0,0,0,0.3);
  box-shadow: var(--shadow-inset), 0 0 0 3px rgba(147,197,253,0.5);
}
.date-sep { color: var(--text-muted); font-size: 13px; }
.btn-reset {
  padding: 7px 14px; border: 1px solid var(--border); border-radius: 9999px;
  background: var(--surface); color: var(--text-muted); cursor: pointer;
  font-size: 12px; font-weight: 500; transition: all 0.15s;
  box-shadow: var(--shadow-soft);
}
.btn-reset:hover { background: var(--bg-subtle); color: var(--text); }

.error-banner {
  padding: 10px 16px; background: #fef2f2; border: 1px solid #fecaca;
  color: #b91c1c; margin-bottom: 12px; border-radius: 10px;
  font-size: 13px;
}

.summary-bar {
  display: flex; align-items: center; gap: 0;
  padding: 10px 18px; margin-bottom: 12px;
  background: var(--surface); border-radius: 12px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
  font-size: 13px;
}
.summary-item {
  display: flex; flex-direction: column; align-items: center;
  padding: 2px 20px;
}
.summary-item strong { font-size: 15px; font-weight: 600; color: var(--text); }
.summary-label { font-size: 11px; color: var(--text-muted); margin-bottom: 1px; }
.refund-item strong { color: var(--danger); }
.summary-sep {
  width: 1px; height: 28px; background: var(--border-subtle);
}

.table-wrap {
  position: relative; overflow-x: auto;
  background: var(--surface); border-radius: 16px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
}
.order-table { width: 100%; border-collapse: collapse; font-size: 13px; letter-spacing: 0.13px; }
.order-table th {
  padding: 11px 14px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 11px; font-weight: 500; letter-spacing: 0.11px;
  color: var(--text-muted); text-transform: uppercase; background: var(--surface);
  text-align: left; white-space: nowrap;
}
.order-table td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
  text-align: left; white-space: nowrap;
}

/* Date group header row */
.date-group-row {
  cursor: pointer; user-select: none;
  background: var(--bg-subtle);
}
.date-group-row:hover { background: #e8edf5; }
.date-group-row td { border-bottom: 1px solid var(--border); }

.toggle-cell { width: 32px; padding: 10px 6px 10px 14px; }
.toggle-icon {
  display: inline-block; font-size: 10px; color: var(--text-muted);
  transition: transform 0.18s;
}
.toggle-icon.open { transform: rotate(90deg); }

.date-label { font-weight: 600; font-size: 13px; color: var(--text); }
.date-stat { font-weight: 600; color: var(--text); }
.date-count { color: var(--text-muted); font-size: 12px; padding-left: 8px; }
.date-muted { color: var(--text-muted); }

/* Detail rows */
.detail-row { background: var(--surface); }
.detail-row:hover { background: #f7f9fc; }
.detail-row:last-child td { border-bottom: 1px solid var(--border); }

.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--text-muted); font-size: 12px; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.refund { color: var(--danger); }

.empty-state { padding: 48px 0; text-align: center; color: var(--text-muted); font-size: 14px; }
.empty-state a { color: var(--text); cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }
.loading-mask {
  position: absolute; inset: 0;
  background: rgba(255,255,255,0.7); border-radius: 16px;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted); font-size: 13px;
}

.pagination {
  display: flex; gap: 12px; align-items: center;
  justify-content: center; margin-top: 20px;
  font-size: 13px; color: var(--text-muted);
}
.pagination button {
  padding: 5px 14px; border: 1px solid var(--border);
  border-radius: 9999px; cursor: pointer; background: var(--surface);
  font-size: 13px; color: var(--text); box-shadow: var(--shadow-soft);
  transition: background 0.12s;
}
.pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.pagination button:not(:disabled):hover { background: var(--bg-subtle); }
.pagination-info { text-align: center; margin-top: 12px; color: var(--text-muted); font-size: 13px; }
</style>
