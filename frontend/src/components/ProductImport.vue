<template>
  <div class="import-page">
    <h2>导入商品目录</h2>

    <div class="tabs">
      <button :class="{ active: tab === 'csv' }" @click="tab = 'csv'">商品导入</button>
      <button :class="{ active: tab === 'taobao' }" @click="tab = 'taobao'">淘宝 Token</button>
    </div>

    <div v-if="error" class="error-banner">{{ error }} <button @click="error = null">×</button></div>
    <div v-if="success" class="success-banner">{{ success }}</div>

    <!-- Upload Tab -->
    <div v-if="tab === 'csv'" class="tab-content">
      <p class="hint">
        上传淘宝后台导出的 <code>Goods.xlsx</code> 文件，增量导入商品数据。
        以商品 ID 去重，已有商品只更新名称和价格。
      </p>
      <div class="store-selector">
        <span class="store-label">店铺：</span>
        <label><input type="radio" :value="1" v-model="selectedStore" /> 店铺1</label>
        <label><input type="radio" :value="2" v-model="selectedStore" /> 店铺2</label>
        <span v-if="storeError" class="error-text">{{ storeError }}</span>
      </div>
      <div class="file-row">
        <label class="file-label">
          <input type="file" accept=".xlsx" @change="onFileChange" class="file-input" />
          <span class="file-btn">选择文件</span>
          <span class="file-name">{{ selectedFile ? selectedFile.name : '未选择文件' }}</span>
        </label>
      </div>
      <button :disabled="loading || !selectedFile" class="btn-import-dir" @click="submitUpload">
        {{ loading ? '导入中…' : '导入商品' }}
      </button>
    </div>

    <!-- Taobao Token Tab -->
    <div v-if="tab === 'taobao'" class="tab-content">
      <label>应用 App Key<input v-model="form.app_key" placeholder="应用 App Key" /></label>
      <label>Session Key<input v-model="form.session_key" placeholder="OAuth Session Key" /></label>
      <label>App Secret<input v-model="form.app_secret" type="password" placeholder="应用 App Secret" /></label>
      <button :disabled="!formValid || loading" @click="submitTaobao">
        {{ loading ? '连接中…' : '连接淘宝' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { importGoodsXlsx, importTaobao } from '../api/products.js'

const tab = ref('csv')
const loading = ref(false)
const error = ref(null)
const success = ref(null)
const selectedStore = ref(null)
const storeError = ref('')
const selectedFile = ref(null)
const form = ref({ session_key: '', app_key: '', app_secret: '' })

const formValid = computed(() =>
  form.value.session_key && form.value.app_key && form.value.app_secret
)

function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
}

function validateStore() {
  if (!selectedStore.value) {
    storeError.value = '请选择店铺'
    return false
  }
  storeError.value = ''
  return true
}

async function submitUpload() {
  if (!validateStore()) return
  if (!selectedFile.value) return
  error.value = null
  success.value = null
  loading.value = true
  try {
    const result = await importGoodsXlsx(selectedFile.value, selectedStore.value)
    success.value = `新增 ${result.imported} 件，更新 ${result.updated} 件`
    if (result.errors && result.errors.length) {
      error.value = result.errors.map(e => e.reason || e).join('；')
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function submitTaobao() {
  error.value = null
  success.value = null
  loading.value = true
  try {
    const result = await importTaobao(form.value)
    success.value = `导入成功：新增 ${result.imported} 件，更新 ${result.updated} 件`
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.import-page { padding: 0; }

.tabs {
  display: flex;
  gap: 3px;
  margin-bottom: 20px;
  width: fit-content;
}
.tabs button {
  padding: 5px 14px;
  border: 1px solid var(--border); border-radius: 9999px;
  cursor: pointer; background: transparent;
  font-size: 12px; font-weight: 500; letter-spacing: 0.12px;
  color: var(--text-muted);
  transition: all 0.15s;
}
.tabs button.active { background: #000; color: #fff; border-color: #000; }
.tabs button:hover:not(.active) { color: var(--text); background: var(--bg-subtle); }

.tab-content { display: flex; flex-direction: column; gap: 18px; }

.btn-import-dir {
  padding: 10px 24px;
  background: #000; color: #fff;
  border: none; border-radius: 9999px;
  font-size: 14px; font-weight: 500;
  cursor: pointer; width: fit-content;
  transition: background 0.15s;
}
.btn-import-dir:hover:not(:disabled) { background: #222; }
.btn-import-dir:disabled { opacity: 0.5; cursor: not-allowed; }

.store-selector {
  display: flex;
  align-items: center;
  gap: 16px;
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

.file-row {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 18px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.file-label {
  display: flex; align-items: center; gap: 10px;
  cursor: pointer; flex: 1;
}
.file-input { display: none; }
.file-btn {
  padding: 7px 16px;
  border: 1px solid var(--border); border-radius: 9999px;
  font-size: 13px; font-weight: 500; cursor: pointer;
  background: var(--surface); color: var(--text);
  transition: background 0.15s;
  white-space: nowrap;
}
.file-label:hover .file-btn { background: var(--border); }
.file-name { font-size: 13px; color: var(--text-muted); }

label {
  display: flex; flex-direction: column; gap: 5px;
  font-size: 13px; font-weight: 500; color: var(--text-secondary);
}
label input[type="text"],
label input[type="password"],
label input:not([type="file"]):not([type="button"]):not([type="submit"]) {
  padding: 8px 12px;
  border: 1px solid var(--border); border-radius: 8px;
  font-size: 14px; background: var(--surface); color: var(--text);
  box-shadow: var(--shadow-inset); outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
label input:focus {
  border-color: rgba(0,0,0,0.3);
  box-shadow: var(--shadow-inset), 0 0 0 3px rgba(147,197,253,0.5);
}

input[type="file"] {
  font-size: 13px; color: var(--text-secondary);
  cursor: pointer;
}

button:not(.tabs button) {
  align-self: flex-start;
  padding: 8px 20px;
  background: #000; color: #fff;
  border: none; border-radius: 9999px; cursor: pointer;
  font-size: 13px; font-weight: 500;
  box-shadow: var(--shadow-card); transition: background 0.15s;
  margin-top: 4px;
}
button:not(.tabs button):hover:not(:disabled) { background: #222; }
button:disabled { opacity: 0.5; cursor: not-allowed; }

.error-banner {
  background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c;
  padding: 10px 14px; border-radius: 10px;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px;
}
.error-banner button {
  background: none; border: none; cursor: pointer; color: #b91c1c;
  font-size: 14px; padding: 0; margin-left: 8px; box-shadow: none;
  align-self: auto; margin-top: 0;
}
.success-banner {
  background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534;
  padding: 10px 14px; border-radius: 10px; font-size: 13px;
}
.hint {
  color: var(--text-muted); font-size: 13px; letter-spacing: 0.13px;
  line-height: 1.6;
}
.hint code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px; background: var(--bg); padding: 1px 5px;
  border-radius: 4px; border: 1px solid var(--border);
}
</style>
