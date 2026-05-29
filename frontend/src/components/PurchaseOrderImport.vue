<template>
  <div class="po-import">
    <h3>1688采购订单导入</h3>
    <p class="hint">上传从 1688 导出的采购订单 xlsx 文件（仅解析主订单行，续行自动忽略）。</p>
    <div class="store-selector">
      <span class="store-label">店铺：</span>
      <label><input type="radio" :value="1" v-model="selectedStore" /> 店铺1</label>
      <label><input type="radio" :value="2" v-model="selectedStore" /> 店铺2</label>
      <span v-if="storeError" class="error-text">{{ storeError }}</span>
    </div>
    <div class="file-area">
      <label class="file-label">
        <input
          ref="fileInput"
          type="file"
          accept=".xlsx"
          :disabled="loading"
          @change="onFileChange"
          class="file-input"
        />
        <span class="file-btn">选择文件</span>
        <span class="file-name">{{ selectedFile ? selectedFile.name : '未选择文件' }}</span>
      </label>
      <button :disabled="!selectedFile || loading" class="btn-primary" @click="upload">
        {{ loading ? '上传中...' : '上传' }}
      </button>
    </div>

    <div v-if="result" class="result-box">
      <p>✅ 导入完成</p>
      <ul>
        <li>新增：{{ result.imported }} 条</li>
        <li>更新：{{ result.updated }} 条</li>
        <li v-if="result.errors > 0">无效行：{{ result.errors }} 条</li>
      </ul>
    </div>

    <div v-if="errorMsg" class="error-box">
      ❌ {{ errorMsg }}
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { importPurchaseOrders } from '../api/purchase_orders.js'

const fileInput = ref(null)
const selectedFile = ref(null)
const selectedStore = ref(null)
const storeError = ref('')
const loading = ref(false)
const result = ref(null)
const errorMsg = ref(null)

function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
  result.value = null
  errorMsg.value = null
}

function validateStore() {
  if (!selectedStore.value) {
    storeError.value = '请选择店铺'
    return false
  }
  storeError.value = ''
  return true
}

async function upload() {
  if (!selectedFile.value) return
  if (!validateStore()) return
  loading.value = true
  result.value = null
  errorMsg.value = null
  try {
    result.value = await importPurchaseOrders(selectedFile.value, selectedStore.value)
  } catch (e) {
    errorMsg.value = e?.detail || e?.message || '导入失败，请重试'
  } finally {
    loading.value = false
    if (fileInput.value) fileInput.value.value = ''
    selectedFile.value = null
  }
}
</script>

<style scoped>
.po-import { padding: 0; }

h3 {
  font-size: 18px; font-weight: 500; letter-spacing: 0.15px;
  color: var(--text); margin-bottom: 8px;
}

.hint {
  font-size: 13px; color: var(--text-muted); line-height: 1.6; margin-bottom: 20px;
}

.store-selector {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: var(--bg-subtle);
  border-radius: 10px;
  border: 1px solid var(--border);
}
.store-selector label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 14px;
}
.store-label {
  font-size: 14px; font-weight: 500;
  color: var(--text-muted);
}
.error-text {
  font-size: 12px;
  color: var(--danger, #c0392b);
}

.file-area {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  padding: 14px 18px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: 16px;
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
  background: #f0faf4; border: 1px solid #b7e4c7;
  border-radius: 10px; font-size: 13px; color: #1a6b3a;
}
.result-box p { margin: 0 0 6px; font-weight: 500; }
.result-box ul { margin: 0; padding-left: 18px; }
.result-box li { margin-bottom: 2px; }

.error-box {
  margin-top: 16px; padding: 12px 16px;
  background: #fff5f5; border: 1px solid #f5c6c6;
  border-radius: 10px; font-size: 13px; color: #c0392b;
}
</style>
