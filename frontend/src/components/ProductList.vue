<template>
  <div class="product-list-page">
    <div class="toolbar">
      <h2>商品列表</h2>
      <div class="filters">
        <input v-model="searchQ" placeholder="搜索商品名称…" @keyup.enter="applyFilters" />
        <input v-model.number="minPrice" type="number" placeholder="最低价" min="0" />
        <input v-model.number="maxPrice" type="number" placeholder="最高价" min="0" />
        <button @click="applyFilters">筛选</button>
        <button v-if="hasFilter" @click="clearFilters" class="secondary">清除筛选</button>
      </div>
    </div>

    <div v-if="error" class="error-banner">{{ error }} <button @click="error = null">×</button></div>

    <table v-if="items.length">
      <thead>
        <tr>
          <th>商品 ID</th>
          <th @click="cycleSortOrder" style="cursor:pointer">商品标题 {{ sortArrow }}</th>
          <th>当前价格</th>
          <th>近90天销量</th>
          <th>最近更新</th>
          <th>预警</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in sortedProducts" :key="item.id" class="clickable" @click="goDetail(item.id)">
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
        </tr>
      </tbody>
    </table>

    <div v-else-if="!loading" class="empty">暂无商品，请先<router-link to="/products/import">导入商品目录</router-link></div>
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

const hasFilter = computed(() => activeQ.value || activeMin.value != null || activeMax.value != null)

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


async function load() {
  loading.value = true
  error.value = null
  try {
    const params = { page: page.value, page_size: pageSize }
    if (activeQ.value) params.q = activeQ.value
    if (activeMin.value != null) params.min_price = activeMin.value
    if (activeMax.value != null) params.max_price = activeMax.value
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
.toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }
.toolbar h2 {
  margin: 0; flex: 1;
  font-size: 22px; font-weight: 400; letter-spacing: -0.2px; color: var(--text);
}
.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filters input {
  padding: 7px 12px; border: 1px solid var(--border); border-radius: 8px;
  width: 140px; font-size: 13px; background: var(--surface); color: var(--text);
  box-shadow: var(--shadow-inset); outline: none;
}
.filters input:focus { border-color: rgba(0,0,0,0.3); box-shadow: var(--shadow-inset), 0 0 0 3px rgba(147,197,253,0.5); }
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
</style>
