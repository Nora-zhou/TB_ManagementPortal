<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import {
  fetchProducts,
  fetchSKUList,
  fetchSKUCosts,
  saveSKUCosts,
  fetchSKUCostSuggest,
} from '../api/products.js'

// ── Product list ──
const products = ref([])
const loadingProducts = ref(false)
const loadError = ref(null)

// ── Search / filter ──
const searchQuery = ref('')
const showUnconfiguredOnly = ref(false)

// ── Per-product accordion state ──
// productState[taobao_item_id] = { loading, expanded, skuItems, savedSnapshot,
//   configuredCount, totalCount, saving, saveMsg, saveError, suggestData }
const productState = reactive({})

function getOrInitState(tid) {
  if (!productState[tid]) {
    productState[tid] = {
      loading: false,
      expanded: false,
      skuItems: [],
      savedSnapshot: [],
      configuredCount: 0,
      totalCount: 0,
      saving: false,
      saveMsg: null,
      saveError: null,
      suggestData: null,
    }
  }
  return productState[tid]
}

// ── Derived filtered list ──
const filteredProducts = computed(() => {
  let list = products.value
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(p =>
      (p.name || '').toLowerCase().includes(q) ||
      String(p.taobao_item_id).includes(q)
    )
  }
  if (showUnconfiguredOnly.value) {
    list = list.filter(p => {
      const s = productState[p.taobao_item_id]
      // If expanded and loaded, use live data (more accurate)
      if (s?.skuItems.length > 0) return s.configuredCount < s.totalCount
      // Otherwise rely on the field from the products API
      return !p.sku_cost_configured
    })
  }
  return list
})

// ── Load all products on mount ──
async function loadProducts() {
  loadingProducts.value = true
  loadError.value = null
  try {
    const data = await fetchProducts({ page_size: 5000 })
    products.value = data.items || []
  } catch (e) {
    loadError.value = e.message
  } finally {
    loadingProducts.value = false
  }
}

// ── SKU helpers ──
function deepClone(arr) {
  return arr.map(r => ({ ...r }))
}

function buildSkuItems(baseList, costMap) {
  if (baseList.length === 0) {
    return [{
      sku_id: '', sku_name: '默认（无规格）',
      purchase_cost: '', isDirty: false, hasError: false, errorMsg: '',
    }]
  }
  return baseList.map(s => ({
    sku_id: s.sku_id,
    sku_name: s.sku_name || s.sku_id || '默认（无规格）',
    purchase_cost: costMap[s.sku_id]?.purchase_cost ?? '',
    isDirty: false,
    hasError: false,
    errorMsg: '',
  }))
}

async function loadSKUsForProduct(product) {
  const s = productState[product.taobao_item_id]
  s.loading = true
  s.saveError = null
  try {
    const [skuList, costs] = await Promise.all([
      fetchSKUList(product.id),
      fetchSKUCosts(product.id),
    ])
    const costMap = Object.fromEntries((costs || []).map(c => [c.sku_id, c]))
    const baseList = (skuList || []).length > 0
      ? skuList
      : (costs || []).map(c => ({ sku_id: c.sku_id, sku_name: c.sku_name }))

    s.skuItems = buildSkuItems(baseList, costMap)
    s.savedSnapshot = deepClone(s.skuItems)
    s.configuredCount = (costs || []).filter(c => c.purchase_cost != null).length
    s.totalCount = s.skuItems.length

    // non-blocking suggest
    fetchSKUCostSuggest(product.id)
      .then(d => { s.suggestData = d })
      .catch(() => {})
  } catch (e) {
    s.saveError = e.message
  } finally {
    s.loading = false
  }
}

// ── Toggle expand/collapse ──
async function toggleExpand(product) {
  const s = getOrInitState(product.taobao_item_id)
  if (s.expanded) {
    if (hasDirtyItems(s)) {
      if (!window.confirm('有未保存的修改，确定要收起并放弃更改吗？')) return
    }
    s.expanded = false
    return
  }
  s.expanded = true
  if (s.skuItems.length === 0) {
    await loadSKUsForProduct(product)
  }
}

// ── Input & validation ──
function onCostInput(s, item) {
  item.isDirty = true
  validateItem(item)
}

function validateItem(item) {
  const v = item.purchase_cost
  if (v === '' || v == null) {
    item.hasError = false; item.errorMsg = ''
    return
  }
  const num = Number(v)
  if (isNaN(num) || num < 0) {
    item.hasError = true; item.errorMsg = '采购成本须为非负数字'
  } else if (!/^\d+(\.\d{0,2})?$/.test(String(v).trim())) {
    item.hasError = true; item.errorMsg = '最多两位小数'
  } else {
    item.hasError = false; item.errorMsg = ''
  }
}

// ── Save ──
async function saveProduct(product) {
  const s = productState[product.taobao_item_id]
  s.skuItems.forEach(validateItem)
  if (s.skuItems.some(r => r.hasError)) return

  s.saving = true; s.saveMsg = null; s.saveError = null
  try {
    const items = s.skuItems.map(r => ({
      sku_id: r.sku_id,
      sku_name: r.sku_name || r.sku_id || '默认',
      purchase_cost: (r.purchase_cost === '' || r.purchase_cost == null)
        ? 0
        : Number(r.purchase_cost),
    }))
    const saved = await saveSKUCosts(product.id, items)
    const costMap = Object.fromEntries(saved.map(c => [c.sku_id, c]))
    s.skuItems.forEach(item => {
      item.purchase_cost = costMap[item.sku_id]?.purchase_cost ?? item.purchase_cost
      item.isDirty = false
    })
    s.savedSnapshot = deepClone(s.skuItems)
    s.configuredCount = saved.filter(c => c.purchase_cost != null).length
    s.saveMsg = '保存成功'
    setTimeout(() => { s.saveMsg = null }, 3000)
  } catch (e) {
    s.saveError = `保存失败: ${e.message}`
  } finally {
    s.saving = false
  }
}

// ── Smart suggest ──
function applySuggest(s) {
  if (!s.suggestData?.available) return
  s.skuItems.forEach(item => {
    item.purchase_cost = String(s.suggestData.suggested_cost ?? '')
    item.isDirty = true
    validateItem(item)
  })
}

// ── Expand / collapse all ──
async function expandAll() {
  for (const p of filteredProducts.value) {
    const s = getOrInitState(p.taobao_item_id)
    s.expanded = true
    if (s.skuItems.length === 0) {
      loadSKUsForProduct(p)
    }
  }
}

function collapseAll() {
  for (const id in productState) {
    productState[id].expanded = false
  }
}

// ── Dirty helpers ──
function hasDirtyItems(s) { return s.skuItems.some(r => r.isDirty) }
function hasAnyDirty() { return Object.values(productState).some(s => hasDirtyItems(s)) }

// ── Copy ID ──
const copiedId = ref(null)
function copyId(id, event) {
  event.stopPropagation()
  navigator.clipboard.writeText(String(id)).then(() => {
    copiedId.value = id
    setTimeout(() => { copiedId.value = null }, 1800)
  })
}

// ── Badge helper ──
function skuBadgeClass(product) {
  const s = productState[product.taobao_item_id]
  if (s?.skuItems.length > 0) {
    if (s.configuredCount === 0) return 'sku-badge--none'
    if (s.configuredCount === s.totalCount) return 'sku-badge--done'
    return 'sku-badge--partial'
  }
  return product.sku_cost_configured ? 'sku-badge--done' : 'sku-badge--none'
}

// ── Route leave guard ──
onBeforeRouteLeave((_to, _from, next) => {
  if (hasAnyDirty()) {
    if (!window.confirm('有未保存的修改，确定要离开并放弃更改吗？')) {
      next(false)
      return
    }
  }
  next()
})

onMounted(loadProducts)
</script>

<template>
  <div class="sku-cost-page">
    <div class="page-header">
      <h1 class="page-title">SKU 成本配置</h1>
      <p class="page-desc">为所有商品的 SKU 批量配置采购成本，用于计算商品毛利率。</p>
    </div>

    <!-- Toolbar -->
    <div class="toolbar">
      <div class="search-wrap">
        <input
          v-model="searchQuery"
          class="search-input"
          type="text"
          placeholder="搜索商品名称或 ID…"
        />
        <button
          v-if="searchQuery"
          class="search-clear"
          title="清除搜索"
          @click="searchQuery = ''"
        >×</button>
      </div>
      <label class="filter-check">
        <input v-model="showUnconfiguredOnly" type="checkbox" />
        <span>仅显示未完全配置成本的商品</span>
      </label>
      <div class="toolbar-actions">
        <button class="btn btn-sm" @click="expandAll">展开全部</button>
        <button class="btn btn-sm" @click="collapseAll">收起全部</button>
      </div>
    </div>

    <!-- Loading / error -->
    <div v-if="loadingProducts" class="state-msg">加载商品列表中…</div>
    <div v-else-if="loadError" class="state-msg state-msg--error">加载失败：{{ loadError }}</div>
    <div v-else-if="filteredProducts.length === 0" class="state-msg">暂无匹配商品</div>

    <!-- Product list -->
    <div v-else class="product-list">
      <div
        v-for="product in filteredProducts"
        :key="product.taobao_item_id"
        class="product-card"
        :class="{ 'product-card--expanded': productState[product.taobao_item_id]?.expanded }"
      >
        <!-- Row header (click to toggle) -->
        <div class="product-row" @click="toggleExpand(product)">
          <span class="chevron">{{ productState[product.taobao_item_id]?.expanded ? '▾' : '▸' }}</span>
          <span class="product-title">{{ product.name }}</span>
          <span
            class="product-id"
            :title="copiedId === product.taobao_item_id ? '已复制！' : '点击复制完整 ID'"
            @click="copyId(product.taobao_item_id, $event)"
          >
            <span class="product-id-text">{{ product.taobao_item_id }}</span>
            <span class="product-id-copy">{{ copiedId === product.taobao_item_id ? '✓' : '⎘' }}</span>
          </span>
          <span class="sku-badge" :class="skuBadgeClass(product)">
            <template v-if="productState[product.taobao_item_id]?.skuItems.length > 0">
              <template v-if="productState[product.taobao_item_id].configuredCount === 0">
                未配置（共 {{ productState[product.taobao_item_id].totalCount }} 个 SKU）
              </template>
              <template v-else-if="productState[product.taobao_item_id].configuredCount === productState[product.taobao_item_id].totalCount">
                全部已配置（{{ productState[product.taobao_item_id].totalCount }} 个 SKU）
              </template>
              <template v-else>
                {{ productState[product.taobao_item_id].configuredCount }} / {{ productState[product.taobao_item_id].totalCount }} SKU 已配置
              </template>
            </template>
            <template v-else-if="product.sku_cost_configured">已配置</template>
            <template v-else>未配置</template>
          </span>
        </div>

        <!-- Expanded content -->
        <div v-if="productState[product.taobao_item_id]?.expanded" class="product-expanded">
          <div v-if="productState[product.taobao_item_id].loading" class="state-msg state-msg--sm">
            加载 SKU 数据中…
          </div>
          <template v-else>
            <!-- No SKU notice -->
            <div
              v-if="productState[product.taobao_item_id].skuItems.length === 1 && productState[product.taobao_item_id].skuItems[0].sku_id === '' && productState[product.taobao_item_id].configuredCount === 0 && productState[product.taobao_item_id].totalCount <= 1"
              class="notice notice--warn"
            >
              暂无 SKU 数据，请先导入该商品的子订单
            </div>

            <!-- All costs unset notice -->
            <div
              v-if="productState[product.taobao_item_id].configuredCount === 0 && productState[product.taobao_item_id].totalCount > 0"
              class="notice notice--info"
            >
              成本未设置，利润分析将无法显示
            </div>

            <!-- SKU table -->
            <table class="sku-table">
              <thead>
                <tr>
                  <th>SKU 规格</th>
                  <th>采购成本（元）</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in productState[product.taobao_item_id].skuItems"
                  :key="item.sku_id"
                  :class="{ 'row--dirty': item.isDirty, 'row--error': item.hasError }"
                >
                  <td class="sku-name">{{ item.sku_name }}</td>
                  <td class="sku-cost-cell">
                    <input
                      v-model="item.purchase_cost"
                      class="cost-input"
                      :class="{ 'cost-input--error': item.hasError }"
                      type="text"
                      placeholder="未设置"
                      @input="onCostInput(productState[product.taobao_item_id], item)"
                    />
                    <span v-if="item.hasError" class="inline-error">{{ item.errorMsg }}</span>
                  </td>
                </tr>
              </tbody>
            </table>

            <!-- Actions row -->
            <div class="expanded-actions">
              <button
                v-if="productState[product.taobao_item_id].suggestData?.available"
                class="btn btn-sm btn-suggest"
                @click.stop="applySuggest(productState[product.taobao_item_id])"
              >
                智能建议
              </button>
              <span class="spacer" />
              <span
                v-if="productState[product.taobao_item_id].saveMsg"
                class="save-msg"
              >{{ productState[product.taobao_item_id].saveMsg }}</span>
              <span
                v-if="productState[product.taobao_item_id].saveError"
                class="save-error"
              >{{ productState[product.taobao_item_id].saveError }}</span>
              <button
                class="btn btn-primary btn-sm"
                :disabled="productState[product.taobao_item_id].saving || productState[product.taobao_item_id].skuItems.some(r => r.hasError)"
                @click.stop="saveProduct(product)"
              >
                {{ productState[product.taobao_item_id].saving ? '保存中…' : '保存' }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sku-cost-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header { display: flex; flex-direction: column; gap: 4px; }
.page-title  { font-size: 22px; font-weight: 700; margin: 0; color: var(--text); }
.page-desc   { font-size: 14px; color: var(--text-muted); margin: 0; }

/* Toolbar */
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.search-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.search-input {
  padding: 7px 30px 7px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  font-size: 14px;
  width: 220px;
  outline: none;
  transition: border-color 0.15s;
}
.search-input:focus { border-color: #888; }

.search-clear {
  position: absolute;
  right: 8px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  color: #aaa;
  padding: 0;
  transition: color 0.12s;
}
.search-clear:hover { color: #555; }

.filter-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13.5px;
  color: var(--text-muted);
  cursor: pointer;
  user-select: none;
}

.toolbar-actions { display: flex; gap: 8px; margin-left: auto; }

/* Buttons */
.btn {
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid var(--border-subtle);
  background: var(--bg-subtle, #f5f5f5);
  color: var(--text);
  transition: background 0.12s;
}
.btn:hover { background: #e8e8e8; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-primary {
  background: #000;
  color: #fff;
  border-color: #000;
}
.btn-primary:hover:not(:disabled) { background: #222; }

.btn-suggest {
  background: #f0f6ff;
  border-color: #b3d0ff;
  color: #1a6fd4;
}
.btn-suggest:hover { background: #ddeeff; }

/* State messages */
.state-msg {
  text-align: center;
  color: var(--text-muted);
  padding: 40px 0;
  font-size: 14px;
}
.state-msg--error { color: #c0392b; }
.state-msg--sm    { padding: 16px 0; }

/* Product list */
.product-list { display: flex; flex-direction: column; gap: 6px; }

.product-card {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
  transition: box-shadow 0.12s;
}
.product-card--expanded { box-shadow: 0 2px 12px rgba(0,0,0,0.07); }

.product-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
}
.product-row:hover { background: var(--bg-subtle, #f8f8f8); }

.chevron      { font-size: 12px; color: var(--text-muted); flex-shrink: 0; }
.product-title { font-size: 14px; font-weight: 500; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.product-id {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  padding: 2px 7px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
  user-select: none;
}
.product-id:hover {
  background: #f0f4ff;
  border-color: #c5d5f5;
}
.product-id-text {
  font-size: 11.5px;
  font-family: 'Courier New', Courier, monospace;
  color: #555;
  letter-spacing: 0.3px;
}
.product-id-copy {
  font-size: 12px;
  color: #aaa;
  line-height: 1;
  transition: color 0.12s;
}
.product-id:hover .product-id-copy { color: #4a7ef5; }
.sku-badge    { font-size: 12px; color: #888; background: #f2f2f2; padding: 2px 8px; border-radius: 20px; flex-shrink: 0; }
.sku-badge--done    { background: #e6f9ee; color: #1a8c4e; }
.sku-badge--partial { background: #fff4e0; color: #b07800; }
.sku-badge--none    { background: #f2f2f2; color: #999; }

/* Expanded section */
.product-expanded {
  border-top: 1px solid var(--border-subtle);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Notices */
.notice {
  font-size: 13px;
  padding: 8px 12px;
  border-radius: 7px;
}
.notice--warn { background: #fff8e1; color: #a0522d; border: 1px solid #ffe082; }
.notice--info { background: #e8f4fd; color: #1565c0; border: 1px solid #90caf9; }

/* SKU table */
.sku-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
}
.sku-table th {
  text-align: left;
  padding: 6px 10px;
  color: var(--text-muted);
  font-weight: 600;
  border-bottom: 1px solid var(--border-subtle);
}
.sku-table td { padding: 6px 10px; }
.sku-table tr + tr td { border-top: 1px solid var(--border-subtle); }

.sku-name { color: var(--text); }

.sku-cost-cell { display: flex; align-items: center; gap: 8px; }

.cost-input {
  padding: 5px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  font-size: 13.5px;
  width: 120px;
  outline: none;
  transition: border-color 0.12s;
}
.cost-input:focus { border-color: #888; }
.cost-input--error { border-color: #e74c3c; }

.inline-error { color: #e74c3c; font-size: 12px; }

.row--dirty td { background: #fffbf0; }
.row--error td { background: #fff5f5; }

/* Actions row */
.expanded-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.spacer { flex: 1; }

.save-msg   { font-size: 13px; color: #27ae60; }
.save-error { font-size: 13px; color: #e74c3c; }
</style>
