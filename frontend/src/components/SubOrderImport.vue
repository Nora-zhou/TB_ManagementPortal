<template>
  <div class="sub-order-import">
    <h3>订单信息导入</h3>
    <p class="hint">上传淘宝后台导出的订单明细 Excel 文件（支持 .xlsx 格式）。</p>
    <div class="file-area">
      <label class="file-label">
        <input
          ref="fileInput"
          type="file"
          accept=".xlsx"
          @change="onFileChange"
          :disabled="loading"
          class="file-input"
        />
        <span class="file-btn">选择文件</span>
        <span class="file-name">{{ selectedFile ? selectedFile.name : '未选择文件' }}</span>
      </label>
      <button @click="upload" :disabled="!selectedFile || loading" class="btn-primary">
        {{ loading ? '上传中...' : '上传' }}
      </button>
    </div>

    <div v-if="result" class="result-box">
      <p>✅ 导入完成</p>
      <ul>
        <li>新增：{{ result.imported }} 条</li>
        <li>更新：{{ result.updated }} 条</li>
        <li>跳过：{{ result.skipped }} 条</li>
        <li v-if="result.errors.length > 0">无效行：{{ result.errors.length }} 条</li>
      </ul>
      <details v-if="result.errors.length > 0">
        <summary>查看无效行详情</summary>
        <ul class="error-list">
          <li v-for="(e, i) in result.errors" :key="i">{{ e }}</li>
        </ul>
      </details>
    </div>

    <div v-if="errorMsg" class="error-box">
      ❌ {{ errorMsg }}
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { importSubOrders } from '../api/sub_orders.js'

const props = defineProps({
  store: { type: Number, default: 1 }
})

const fileInput = ref(null)
const selectedFile = ref(null)
const loading = ref(false)
const result = ref(null)
const errorMsg = ref(null)

function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
  result.value = null
  errorMsg.value = null
}

async function upload() {
  if (!selectedFile.value) return
  loading.value = true
  result.value = null
  errorMsg.value = null
  try {
    result.value = await importSubOrders(selectedFile.value, props.store)
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.sub-order-import { padding: 0; }

h3 {
  font-size: 18px; font-weight: 500; letter-spacing: 0.15px;
  color: var(--text); margin-bottom: 8px;
}

.hint {
  font-size: 13px; color: var(--text-muted); line-height: 1.6; margin-bottom: 20px;
}

.file-area {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  padding: 14px 18px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: 12px;
}

.file-label {
  display: flex; align-items: center; gap: 10px; cursor: pointer; flex: 1;
}
.file-input { display: none; }
.file-btn {
  padding: 7px 16px;
  border: 1px solid var(--border); border-radius: 9999px;
  font-size: 13px; font-weight: 500; cursor: pointer;
  background: var(--surface); color: var(--text);
  transition: background 0.15s; white-space: nowrap;
}
.file-label:hover .file-btn { background: var(--border); }
.file-name { font-size: 13px; color: var(--text-muted); }

.btn-primary {
  padding: 9px 24px;
  background: #000; color: #fff;
  border: none; border-radius: 9999px; cursor: pointer;
  font-size: 13px; font-weight: 500;
  box-shadow: var(--shadow-card); transition: background 0.15s;
  white-space: nowrap; flex-shrink: 0;
}
.btn-primary:hover:not(:disabled) { background: #222; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.result-box {
  margin-top: 0; padding: 16px 20px;
  background: #f0fdf4; border: 1px solid #bbf7d0;
  border-radius: 12px; font-size: 13px;
}
.result-box p { font-weight: 500; color: #166534; margin-bottom: 8px; }
.result-box ul { padding-left: 16px; color: var(--text-secondary); line-height: 1.7; }

.error-box {
  margin-top: 16px; padding: 12px 16px;
  background: #fef2f2; border: 1px solid #fecaca;
  border-radius: 10px; color: var(--danger);
  font-size: 13px;
}

details summary {
  cursor: pointer; font-size: 12px;
  color: var(--text-muted); margin-top: 8px;
}
.error-list {
  max-height: 160px; overflow-y: auto;
  font-size: 12px; color: var(--danger);
  padding-left: 16px; margin-top: 6px;
  line-height: 1.6;
}
</style>
