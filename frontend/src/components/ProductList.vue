<template>
  <div class="product-list-page">
    <div class="toolbar">
      <!-- Row 1: title + store tabs -->
      <div class="toolbar-row toolbar-row--top">
        <h2>商品列表</h2>
        <div class="store-filter">
          <button :class="{ active: storeFilter === null }" @click="setStore(null)">全部</button>
          <button :class="{ active: storeFilter === 1 }"    @click="setStore(1)">店铺1</button>
          <button :class="{ active: storeFilter === 2 }"    @click="setStore(2)">店铺2</button>
        </div>
      </div>
      <!-- Row 2: search + filters -->
      <div class="toolbar-row toolbar-row--filters">
        <input v-model="searchQ" class="search-input" placeholder="搜索商品名称…" @keyup.enter="applyFilters" />
        <div class="price-range">
          <input v-model.number="minPrice" type="number" placeholder="最低价" min="0" />
          <span class="range-sep">—</span>
          <input v-model.number="maxPrice" type="number" placeholder="最高价" min="0" />
        </div>
        <div class="margin-filter">
          <button
            :class="['margin-btn', { active: marginFilter === 'below20' }]"
            @click="setMarginFilter('below20')"
          >毛利率 &lt; 20%</button>
          <button
            :class="['margin-btn', { active: marginFilter === 'above60' }]"
            @click="setMarginFilter('above60')"
          >毛利率 &gt; 60%</button>
        </div>
        <div class="filter-actions">
          <button @click="applyFilters">筛选</button>
          <button v-if="hasFilter" @click="clearFilters" class="secondary">清除筛选</button>
        </div>
      </div>
    </div>

    <div v-if="error" class="error-banner">{{ error }} <button @click="error = null">×</button></div>

    <table v-if="items.length">
      <thead>
        <tr>
          <th>商品 ID</th>
          <th @click="cycleSortOrder" style="cursor:pointer">商品标题 {{ sortArrow }}</th>
          <th>当前价格</th>
          <th @click="toggleSold90dSort" style="cursor:pointer">近90天销量 {{ sold90dSortArrow }}</th>
          <th>最近更新</th>
          <th>预警</th>
          <th @click="toggleMarginSort" style="cursor:pointer">毛利率 {{ marginSortArrow }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in sortedProducts" :key="item.id"
            class="clickable"
            :class="{ 'row-warn': item.gross_margin_pct != null && item.gross_margin_pct < 20 }"
            @click="goDetail(item.id)">
          <td>{{ item.taobao_item_id }}</td>
          <td>{{ item.name }}</td>
          <td>{{ item.current_price != null ? `¥${item.current_price.toFixed(2)}` : '暂无价格数据' }}</td>
          <td>{{ item.sold_90d ?? 0 }}</td>
          <td>{{ formatDate(item.last_updated) }}</td>
          <td>
            <span v-if="item.alert_status === 'below_low'" class="badge below">价格下跌预警</span>
            <span v-else-if="item.alert_status === 'above_high'" class="badge above">价格上涨预警</span>
            <span v-else class="badge normal">—</span>
          </td>
          <td>
            <span v-if="item.gross_margin_pct != null" :class="marginClass(item.gross_margin_pct)">{{ item.gross_margin_pct.toFixed(1) }}%</span>
            <span v-else class="muted">—</span>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else-if="!loading" class="empty">暂无商品，请先<router-link to="/import">导入商品目录</router-link></div>
    <div v-if="loading" class="loading">加载中…</div>

    <div v-if="total > pageSize" class="pagination">
      <button :disabled="page <= 1" @click="changePage(page - 1)">上一页</button>
      <span>第 {{ page }} 页 / 共 {{ Math.ceil(total / pageSize) }} 页（{{ total }} 件）</span>
      <button :disabled="page * pageSize >= total" @click="changePage(page + 1)">下一页</button>
    </div>


  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchProducts } from '../api/products.js'

const router = useRouter()

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const error = ref(null)

const searchQ = ref('')
const minPrice = ref(null)
const maxPrice = ref(null)
const activeQ = ref('')
const activeMin = ref(null)
const activeMax = ref(null)
const storeFilter = ref(null)  // null = 全部, 1 = 店铺1, 2 = 店铺2
const marginFilter = ref(null) // null | 'below20' | 'above60'

function setStore(val) {
  storeFilter.value = val
  page.value = 1
  load()
}

function setMarginFilter(val) {
  marginFilter.value = marginFilter.value === val ? null : val
  page.value = 1
  load()
}

const hasFilter = computed(() => activeQ.value || activeMin.value != null || activeMax.value != null || storeFilter.value != null || marginFilter.value != null)

const sortOrder = ref('none')
const sortArrow = computed(() => {
  if (sortOrder.value === 'asc') return '↑'
  if (sortOrder.value === 'desc') return '↓'
  return '⇅'
})
const sortedProducts = computed(() => {
  if (sortOrder.value === 'none') return items.value
  return [...items.value].sort((a, b) => {
    const cmp = (a.name || '').localeCompare(b.name || '', 'zh-CN')
    return sortOrder.value === 'asc' ? cmp : -cmp
  })
})
function cycleSortOrder() {
  if (sortOrder.value === 'none') sortOrder.value = 'asc'
  else if (sortOrder.value === 'asc') sortOrder.value = 'desc'
  else sortOrder.value = 'none'
}

const marginSortBy = ref(null)   // null | 'asc' | 'desc'
const marginSortArrow = computed(() => {
  if (marginSortBy.value === 'asc') return '↑'
  if (marginSortBy.value === 'desc') return '↓'
  return '⇅'
})
function toggleMarginSort() {
  sold90dSortBy.value = null
  if (marginSortBy.value === null) marginSortBy.value = 'desc'
  else if (marginSortBy.value === 'desc') marginSortBy.value = 'asc'
  else marginSortBy.value = null
  page.value = 1
  load()
}

const sold90dSortBy = ref(null)   // null | 'asc' | 'desc'
const sold90dSortArrow = computed(() => {
  if (sold90dSortBy.value === 'asc') return '↑'
  if (sold90dSortBy.value === 'desc') return '↓'
  return '⇅'
})
function toggleSold90dSort() {
  marginSortBy.value = null
  if (sold90dSortBy.value === null) sold90dSortBy.value = 'desc'
  else if (sold90dSortBy.value === 'desc') sold90dSortBy.value = 'asc'
  else sold90dSortBy.value = null
  page.value = 1
  load()
}

function marginClass(pct) {
  if (pct == null) return ''
  if (pct < 0) return 'margin-red'
  if (pct < 10) return 'margin-orange'
  if (pct < 20) return 'margin-yellow'
  return ''
}


async function load() {
  loading.value = true
  error.value = null
  try {
    const params = { page: page.value, page_size: pageSize }
    if (activeQ.value) params.q = activeQ.value
    if (activeMin.value != null) params.min_price = activeMin.value
    if (activeMax.value != null) params.max_price = activeMax.value
    if (storeFilter.value != null) params.store = storeFilter.value
    if (marginFilter.value != null) params.margin_filter = marginFilter.value
    if (marginSortBy.value != null) {
      params.sort_by = 'gross_margin_pct'
      params.sort_order = marginSortBy.value
    } else if (sold90dSortBy.value != null) {
      params.sort_by = 'sold_90d'
      params.sort_order = sold90dSortBy.value
    }
    const data = await fetchProducts(params)
    items.value = data.items
    total.value = data.total
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  activeQ.value = searchQ.value
  activeMin.value = minPrice.value
  activeMax.value = maxPrice.value
  page.value = 1
  load()
}

// M2 — real-time debounced search (300ms)
let _debounce
watch(searchQ, (val) => {
  clearTimeout(_debounce)
  _debounce = setTimeout(() => {
    activeQ.value = val
    page.value = 1
    load()
  }, 300)
})

function clearFilters() {
  searchQ.value = ''
  minPrice.value = null
  maxPrice.value = null
  activeQ.value = ''
  activeMin.value = null
  activeMax.value = null
  storeFilter.value = null
  marginFilter.value = null
  page.value = 1
  load()
}

function changePage(n) {
  page.value = n
  load()
}

function goDetail(id) {
  router.push(`/products/${id}`)
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

onMounted(load)
</script>

<style scoped>
.product-list-page { padding: 0; }
.toolbar { display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }
.toolbar-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.toolbar-row--top { gap: 12px; }
.toolbar h2 {
  margin: 0; flex: 1;
  font-size: 22px; font-weight: 400; letter-spacing: -0.2px; color: var(--text);
}
.toolbar-row--filters {
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 10px 16px;
  gap: 10px;
  box-shadow: var(--shadow-soft);
}
.search-input {
  padding: 7px 12px; border: 1px solid var(--border); border-radius: 8px;
  width: 200px; font-size: 13px; background: var(--surface); color: var(--text);
  box-shadow: var(--shadow-inset); outline: none;
}
.search-input:focus { border-color: rgba(0,0,0,0.3); box-shadow: var(--shadow-inset), 0 0 0 3px rgba(147,197,253,0.5); }
.price-range { display: flex; align-items: center; gap: 6px; }
.price-range input {
  padding: 7px 10px; border: 1px solid var(--border); border-radius: 8px;
  width: 90px; font-size: 13px; background: var(--surface); color: var(--text);
  box-shadow: var(--shadow-inset); outline: none;
}
.price-range input:focus { border-color: rgba(0,0,0,0.3); box-shadow: var(--shadow-inset), 0 0 0 3px rgba(147,197,253,0.5); }
.range-sep { color: var(--text-muted); font-size: 13px; }
.filter-actions { display: flex; gap: 6px; margin-left: auto; }
.store-filter { display: flex; gap: 4px; }
.store-filter button {
  padding: 5px 12px; border-radius: 9999px; font-size: 12px;
  background: var(--surface); color: var(--text-secondary);
  border: 1px solid var(--border); box-shadow: var(--shadow-soft);
}
.store-filter button.active {
  background: #000; color: #fff; border-color: #000; box-shadow: var(--shadow-card);
}
button {
  padding: 7px 16px; background: #000; color: #fff; border: none;
  border-radius: 9999px; cursor: pointer; font-size: 13px; font-weight: 500;
  box-shadow: var(--shadow-card); transition: background 0.15s;
}
button:hover:not(:disabled) { background: #222; }
button.secondary {
  background: var(--surface); color: var(--text-secondary);
  border: 1px solid var(--border); box-shadow: var(--shadow-soft);
}
button.secondary:hover:not(:disabled) { background: var(--bg-subtle); }
button:disabled { opacity: 0.5; cursor: not-allowed; }

table {
  width: 100%; border-collapse: collapse;
  background: var(--surface);
  border-radius: 16px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
  overflow: hidden;
}
th, td { padding: 11px 14px; text-align: left; border-bottom: 1px solid var(--border-subtle); }
th {
  font-size: 11px; font-weight: 500; letter-spacing: 0.11px;
  color: var(--text-muted); text-transform: uppercase;
  background: var(--surface);
}
tbody tr:last-child td { border-bottom: none; }
tr.clickable { cursor: pointer; transition: background 0.12s; }
tr.clickable:hover { background: var(--bg-subtle); }

.badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 500; }
.badge.below { background: #fee2e2; color: #991b1b; }
.badge.above { background: #fef3c7; color: #92400e; }
.badge.normal { color: var(--text-muted); }

.empty { padding: 48px 0; text-align: center; color: var(--text-muted); font-size: 14px; }
.empty a { color: var(--text); text-decoration: underline; text-underline-offset: 3px; }
.loading { text-align: center; color: var(--text-muted); padding: 32px 0; font-size: 14px; }

.pagination {
  display: flex; align-items: center; gap: 12px;
  justify-content: center; margin-top: 20px;
  font-size: 13px; color: var(--text-muted);
}
.pagination button {
  padding: 5px 14px; border-radius: 9999px;
  border: 1px solid var(--border); background: var(--surface);
  box-shadow: var(--shadow-soft); color: var(--text); font-size: 13px;
}

.error-banner {
  background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c;
  padding: 10px 16px; border-radius: 10px;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px; margin-bottom: 12px;
}
.success-banner {
  background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534;
  padding: 10px 16px; border-radius: 10px;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px; margin-bottom: 12px;
}
.margin-red    { color: #ef4444; font-weight: 600; }
.margin-orange { color: #f97316; font-weight: 600; }
.margin-yellow { color: #b45309; font-weight: 600; }
.muted { color: var(--text-muted); }

.margin-filter { display: flex; gap: 4px; }
.margin-btn {
  padding: 5px 10px; border-radius: 9999px; font-size: 12px; font-weight: 500;
  background: var(--surface); color: var(--text-secondary);
  border: 1px solid var(--border); box-shadow: var(--shadow-soft); cursor: pointer;
  transition: background 0.12s;
}
.margin-btn.active { background: #000; color: #fff; border-color: #000; }
.margin-btn:hover:not(.active) { background: var(--bg-subtle); color: var(--text); }

tr.row-warn td { background: #fffbeb !important; }
tr.row-warn:hover td { background: #fef3c7 !important; }
</style>
