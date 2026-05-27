<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { importOrders, pollImportProgress } from '../api/orders'

const props = defineProps({
  store: { type: Number, default: 1 }
})

const router = useRouter()
const selectedStore = ref(props.store)
const storeError = ref('')
const dragging = ref(false)
const loading = ref(false)
const result = ref(null)
const error = ref(null)
const progress = ref(null) // { processed, total, percent }

let pollTimer = null

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function validateStore() {
  if (!selectedStore.value) {
    storeError.value = '请选择店铺'
    return false
  }
  storeError.value = ''
  return true
}

async function handleFile(file) {
  if (!file || !file.name.endsWith('.xlsx')) {
    error.value = '请上传 .xlsx 格式的淘宝导出订单文件'
    return
  }
  if (!validateStore()) return
  error.value = null
  result.value = null
  loading.value = true
  progress.value = null

  // Start progress poll (backend is synchronous for small files;
  // poll anyway so large files show progress)
  pollTimer = setInterval(async () => {
    try {
      const p = await pollImportProgress()
      if (p.status === 'running') progress.value = p
    } catch (_) {}
  }, 500)

  try {
    const res = await importOrders(file, selectedStore.value)
    result.value = res
  } catch (e) {
    error.value = e.message
  } finally {
    stopPoll()
    progress.value = null
    loading.value = false
  }
}

function onInputChange(e) {
  const file = e.target.files[0]
  if (file) handleFile(file)
  e.target.value = ''
}

function onDrop(e) {
  dragging.value = false
  const file = e.dataTransfer.files[0]
  if (file) handleFile(file)
}
</script>

<template>
  <div class="order-import">
    <h2>导入订单数据</h2>
    <p class="hint">上传淘宝后台导出的 <strong>ExportOrderList</strong> xlsx 文件（支持批量导入，重复订单自动更新）</p>

    <!-- Store selector -->
    <div class="store-selector">
      <span class="store-label">店铺：</span>
      <label><input type="radio" :value="1" v-model="selectedStore" /> 店铺1</label>
      <label><input type="radio" :value="2" v-model="selectedStore" /> 店铺2</label>
      <span v-if="storeError" class="error-text">{{ storeError }}</span>
    </div>

    <!-- Drop zone -->
    <label
      class="drop-zone"
      :class="{ dragging, loading }"
      @dragover.prevent="dragging = true"
      @dragleave="dragging = false"
      @drop.prevent="onDrop"
    >
      <input type="file" accept=".xlsx" class="hidden-input" @change="onInputChange" :disabled="loading" />
      <span v-if="loading && progress">
        ⏳ 导入中 {{ progress.processed }}/{{ progress.total }}（{{ progress.percent }}%）
      </span>
      <span v-else-if="loading">⏳ 导入中，请稍候…</span>
      <span v-else>📂 点击选择文件或将 .xlsx 文件拖拽至此</span>
    </label>

    <!-- Progress bar -->
    <div v-if="loading && progress" class="progress-bar-wrap">
      <div class="progress-bar" :style="{ width: progress.percent + '%' }"></div>
    </div>

    <!-- Error -->
    <div v-if="error" class="import-error">⚠ {{ error }}</div>

    <!-- Result -->
    <div v-if="result" class="import-result">
      <p>✅ 导入完成</p>
      <table class="result-table">
        <tr><th>新增订单</th><td>{{ result.imported }}</td></tr>
        <tr><th>更新订单</th><td>{{ result.updated }}</td></tr>
        <tr><th>跳过行数</th><td>{{ result.skipped }}</td></tr>
        <tr v-if="result.errors.length"><th>解析错误</th><td>{{ result.errors.length }} 行（见下）</td></tr>
      </table>
      <ul v-if="result.errors.length" class="error-list">
        <li v-for="e in result.errors" :key="e">{{ e }}</li>
      </ul>
      <div class="result-actions">
        <button class="btn-primary" @click="router.push('/orders/dashboard')">查看分析仪表盘</button>
        <button class="btn-secondary" @click="router.push('/orders')">查看订单列表</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.order-import { padding: 0; }

h2 {
  font-size: 18px; font-weight: 500; letter-spacing: 0.15px;
  color: var(--text); margin-bottom: 8px;
}
.hint {
  color: var(--text-muted); font-size: 13px;
  letter-spacing: 0.13px; line-height: 1.6; margin-bottom: 16px;
}

.store-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.store-selector label {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 13px;
}
.store-label {
  font-size: 13px;
  color: var(--text-muted);
}
.error-text {
  font-size: 12px;
  color: var(--danger, #c0392b);
}

.drop-zone {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1.5px dashed var(--border);
  border-radius: 12px;
  padding: 44px 24px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  font-size: 14px;
  color: var(--text-muted);
  background: var(--bg);
  user-select: none;
}
.drop-zone:hover, .drop-zone.dragging {
  border-color: rgba(0,0,0,0.4);
  background: var(--bg-warm);
  color: var(--text);
}
.drop-zone.loading { opacity: 0.6; cursor: not-allowed; }
.hidden-input { display: none; }

.progress-bar-wrap {
  height: 3px;
  background: var(--border);
  border-radius: 9999px;
  margin-top: 12px;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: #000;
  transition: width 0.3s;
}

.import-error {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fef2f2; border: 1px solid #fecaca;
  color: #b91c1c; border-radius: 10px;
  font-size: 13px;
}
.import-result {
  margin-top: 20px;
  padding: 20px 24px;
  background: #f0fdf4; border: 1px solid #bbf7d0;
  border-radius: 12px;
}
.import-result p {
  font-size: 14px; font-weight: 500; color: #166534; margin-bottom: 12px;
}
.result-table { border-collapse: collapse; margin-bottom: 12px; }
.result-table th, .result-table td {
  padding: 6px 12px; text-align: left;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  font-size: 13px;
}
.result-table th {
  font-weight: 500; color: var(--text-secondary);
  white-space: nowrap;
}
.result-table tr:last-child th, .result-table tr:last-child td { border-bottom: none; }
.error-list {
  max-height: 120px; overflow-y: auto;
  font-size: 12px; color: var(--danger);
  padding-left: 16px;
}
.result-actions { display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
.btn-primary {
  padding: 8px 20px; background: #000; color: #fff;
  border: none; border-radius: 9999px; cursor: pointer;
  font-size: 13px; font-weight: 500;
  box-shadow: var(--shadow-card); transition: background 0.15s;
}
.btn-primary:hover { background: #222; }
.btn-secondary {
  padding: 8px 20px; background: var(--surface); color: var(--text);
  border: 1px solid var(--border); border-radius: 9999px; cursor: pointer;
  font-size: 13px; font-weight: 500;
  box-shadow: var(--shadow-soft); transition: background 0.15s;
}
.btn-secondary:hover { background: var(--bg-subtle); }
</style>
