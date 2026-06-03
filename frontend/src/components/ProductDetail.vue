<template>
  <div class="product-detail-page">
    <button class="back-btn" @click="router.back()">← 返回</button>

    <div v-if="error" class="error-banner">{{ error }} <button @click="error = null">×</button></div>

    <div v-if="product">
      <h2>{{ product.name }}</h2>
      <table class="info-table">
        <tbody>
          <tr><th>淘宝商品 ID</th><td>{{ product.taobao_item_id }}</td></tr>
          <tr><th>商品链接</th><td><a v-if="safeUrl" :href="safeUrl" target="_blank" rel="noopener noreferrer">{{ product.url }}</a><span v-else class="muted">{{ product.url || '—' }}</span></td></tr>
          <tr>
            <th>当前价格</th>
            <td>
              <span v-if="product.current_price != null">¥{{ product.current_price.toFixed(2) }}</span>
              <span v-else class="muted">暂无价格数据</span>
            </td>
          </tr>
          <tr><th>最近更新</th><td>{{ formatDate(product.last_updated) }}</td></tr>

        </tbody>
      </table>

      <OrderPriceChart :product-id="product.id" :days="90" />

      <ProductProfitAnalysis :product-id="product.id" />

    </div>

    <div v-else-if="!error" class="loading">加载中…</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchProduct } from '../api/products.js'
import OrderPriceChart from './OrderPriceChart.vue'
import ProductProfitAnalysis from './ProductProfitAnalysis.vue'

const route = useRoute()
const router = useRouter()

const product = ref(null)
const error = ref(null)

// C1 — only render URLs that start with http(s); block javascript: etc.
const safeUrl = computed(() =>
  /^https?:\/\//i.test(product.value?.url ?? '') ? product.value.url : null
)

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  error.value = null
  try {
    const prod = await fetchProduct(route.params.id)
    product.value = prod
  } catch (e) {
    error.value = e.message
  }
}

onMounted(load)
</script>

<style scoped>
.product-detail-page { padding: 0; max-width: 860px; margin: 0 auto; }
.back-btn {
  background: none; border: none; cursor: pointer;
  font-size: 13px; font-weight: 500; color: var(--text-muted);
  padding: 0; margin-bottom: 28px; letter-spacing: 0.13px;
  display: flex; align-items: center; gap: 4px;
  transition: color 0.15s;
}
.back-btn:hover { color: var(--text); }
h2 {
  margin: 0 0 20px;
  font-size: 24px; font-weight: 500; letter-spacing: 0.1px; line-height: 1.4; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
h3 {
  margin: 32px 0 12px;
  font-size: 15px; font-weight: 500; letter-spacing: 0.15px; color: var(--text);
}
.info-table {
  border-collapse: collapse; width: 100%; margin-bottom: 28px;
  background: var(--surface); border-radius: 16px;
  box-shadow: rgba(0,0,0,0.06) 0px 0px 0px 1px, rgba(0,0,0,0.04) 0px 4px 4px;
  overflow: hidden;
}
.info-table th {
  text-align: left; padding: 12px 20px;
  background: var(--surface); width: 140px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 12px; font-weight: 500; letter-spacing: 0.12px;
  color: var(--text-muted);
}
.info-table td {
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 14px; letter-spacing: 0.14px; color: var(--text-secondary);
}
.info-table tr:last-child th, .info-table tr:last-child td { border-bottom: none; }
.alert-form { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.alert-form label {
  display: flex; flex-direction: column; gap: 4px;
  font-size: 13px; color: var(--text-secondary);
}
.alert-form input {
  padding: 8px 14px; border: 1px solid var(--border); border-radius: 8px;
  width: 160px; font-size: 13px; background: var(--surface); color: var(--text);
  box-shadow: rgba(0,0,0,0.075) 0px 0px 0px 0.5px inset; outline: none;
}
.alert-form input:focus { border-color: rgba(0,0,0,0.3); box-shadow: rgba(0,0,0,0.075) 0px 0px 0px 0.5px inset, 0 0 0 3px rgba(147,197,253,0.5); }
.alert-actions { display: flex; gap: 8px; }
button {
  padding: 8px 18px; background: #000; color: #fff;
  border: none; border-radius: 9999px; cursor: pointer;
  font-size: 13px; font-weight: 500;
  box-shadow: rgba(0,0,0,0.4) 0px 0px 1px, rgba(0,0,0,0.04) 0px 4px 4px;
  transition: background 0.15s;
}
button:hover:not(:disabled) { background: #222; }
button.secondary {
  background: var(--surface); color: var(--text-secondary);
  border: 1px solid var(--border);
  box-shadow: rgba(0,0,0,0.04) 0px 4px 4px;
}
button.secondary:hover:not(:disabled) { background: var(--bg-subtle); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.muted { color: var(--text-muted); }
.loading { text-align: center; color: var(--text-muted); padding: 64px 0; font-size: 14px; letter-spacing: 0.14px; }
.error-banner {
  background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c;
  padding: 10px 16px; border-radius: 10px;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px; margin-bottom: 16px;
}
</style>
