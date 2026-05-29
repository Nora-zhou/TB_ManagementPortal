<template>
  <div class="product-detail-page">
    <button class="back-btn" @click="router.push('/products')">← 返回列表</button>

    <div v-if="error" class="error-banner">{{ error }} <button @click="error = null">×</button></div>
    <div v-if="saveMsg" class="success-banner">{{ saveMsg }}</div>

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

      <h3>价格预警阈值</h3>
      <div class="alert-form">
        <label>
          价格下限（¥）
          <input v-model.number="alertLow" type="number" min="0" placeholder="不设置请留空" />
        </label>
        <label>
          价格上限（¥）
          <input v-model.number="alertHigh" type="number" min="0" placeholder="不设置请留空" />
        </label>
        <div class="alert-actions">
          <button @click="saveAlert" :disabled="savingAlert">保存</button>
          <button class="secondary" @click="clearAlert" :disabled="savingAlert">清除阈值</button>
        </div>
      </div>
    </div>

    <div v-else-if="!error" class="loading">加载中…</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchProduct, updateAlert } from '../api/products.js'
import OrderPriceChart from './OrderPriceChart.vue'
import ProductProfitAnalysis from './ProductProfitAnalysis.vue'

const route = useRoute()
const router = useRouter()

const product = ref(null)
const alertLow = ref(null)
const alertHigh = ref(null)
const error = ref(null)
const saveMsg = ref(null)
const savingAlert = ref(false)

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
    alertLow.value = prod.alert_low
    alertHigh.value = prod.alert_high
  } catch (e) {
    error.value = e.message
  }
}

async function saveAlert() {
  savingAlert.value = true
  saveMsg.value = null
  error.value = null
  // H2 — treat empty string from v-model.number as null
  const low = (alertLow.value === '' || alertLow.value == null) ? null : alertLow.value
  const high = (alertHigh.value === '' || alertHigh.value == null) ? null : alertHigh.value
  try {
    await updateAlert(route.params.id, { alert_low: low, alert_high: high })
    product.value.alert_low = low
    product.value.alert_high = high
    saveMsg.value = '预警阈值已保存'
  } catch (e) {
    error.value = e.message
  } finally {
    savingAlert.value = false
  }
}

async function clearAlert() {
  alertLow.value = null
  alertHigh.value = null
  await saveAlert()
}

onMounted(load)
</script>

<style scoped>
.product-detail-page { padding: 0; max-width: 820px; }
.back-btn {
  background: none; border: none; cursor: pointer;
  font-size: 13px; font-weight: 500; color: var(--text-muted);
  padding: 0; margin-bottom: 20px; letter-spacing: 0.13px;
  display: flex; align-items: center; gap: 4px;
  transition: color 0.15s;
}
.back-btn:hover { color: var(--text); }
h2 {
  margin-bottom: 8px;
  font-size: 24px; font-weight: 300; letter-spacing: -0.3px; color: var(--text);
}
h3 {
  margin: 24px 0 12px;
  font-size: 15px; font-weight: 500; letter-spacing: 0.15px; color: var(--text);
}
.info-table {
  border-collapse: collapse; width: 100%; margin-bottom: 20px;
  background: var(--surface); border-radius: 16px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
  overflow: hidden;
}
.info-table th {
  text-align: left; padding: 10px 16px;
  background: var(--surface); width: 160px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 12px; font-weight: 500; letter-spacing: 0.12px;
  color: var(--text-muted);
}
.info-table td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 13px; color: var(--text-secondary);
}
.info-table tr:last-child th, .info-table tr:last-child td { border-bottom: none; }
.alert-form { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.alert-form label {
  display: flex; flex-direction: column; gap: 4px;
  font-size: 13px; color: var(--text-secondary);
}
.alert-form input {
  padding: 7px 12px; border: 1px solid var(--border); border-radius: 8px;
  width: 160px; font-size: 13px; background: var(--surface); color: var(--text);
  box-shadow: var(--shadow-inset); outline: none;
}
.alert-form input:focus { border-color: rgba(0,0,0,0.3); box-shadow: var(--shadow-inset), 0 0 0 3px rgba(147,197,253,0.5); }
.alert-actions { display: flex; gap: 8px; }
button {
  padding: 7px 16px; background: #000; color: #fff;
  border: none; border-radius: 9999px; cursor: pointer;
  font-size: 13px; font-weight: 500;
  box-shadow: var(--shadow-card); transition: background 0.15s;
}
button:hover:not(:disabled) { background: #222; }
button.secondary {
  background: var(--surface); color: var(--text-secondary);
  border: 1px solid var(--border); box-shadow: var(--shadow-soft);
}
button.secondary:hover:not(:disabled) { background: var(--bg-subtle); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.muted { color: var(--text-muted); }
.loading { text-align: center; color: var(--text-muted); padding: 48px 0; font-size: 14px; }
.error-banner {
  background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c;
  padding: 10px 16px; border-radius: 10px;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px; margin-bottom: 12px;
}
.success-banner {
  background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534;
  padding: 10px 16px; border-radius: 10px;
  font-size: 13px; margin-bottom: 12px;
}
</style>
