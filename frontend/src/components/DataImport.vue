<template>
  <div class="data-import">
    <div class="import-header">
      <h1 class="page-title">数据导入</h1>
      <p class="page-subtitle">上传导出的 Excel 文件，批量同步商品、订单与采购数据</p>
    </div>

    <div class="tab-bar">
      <button :class="{ active: activeTab === 'product' }" @click="activeTab = 'product'">商品目录</button>
      <button :class="{ active: activeTab === 'suborder' }" @click="activeTab = 'suborder'">订单信息</button>
      <button :class="{ active: activeTab === 'purchase' }" @click="activeTab = 'purchase'">采购订单</button>
    </div>

    <div class="import-panel">
      <ProductImport v-show="activeTab === 'product'" />
      <div v-show="activeTab === 'suborder'">
        <div class="store-selector">
          <span class="store-label">店铺：</span>
          <label><input type="radio" :value="1" v-model="selectedStore" /> 店铺1</label>
          <label><input type="radio" :value="2" v-model="selectedStore" /> 店铺2</label>
        </div>
        <SubOrderImport :store="selectedStore" />
      </div>
      <PurchaseOrderImport v-show="activeTab === 'purchase'" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ProductImport from './ProductImport.vue'
import SubOrderImport from './SubOrderImport.vue'
import PurchaseOrderImport from './PurchaseOrderImport.vue'

const activeTab = ref('product')
const selectedStore = ref(1)
</script>

<style scoped>
.data-import { max-width: 840px; }

.import-header { margin-bottom: 28px; }

.tab-bar {
  display: flex;
  gap: 6px;
  margin-bottom: 24px;
  background: var(--surface);
  border-radius: 12px;
  padding: 6px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
  width: fit-content;
}

.tab-bar button {
  padding: 8px 22px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.13px;
  color: var(--text-muted);
  border-radius: 8px;
  transition: color 0.15s, background 0.15s;
}

.tab-bar button.active {
  background: #000;
  color: #fff;
  box-shadow: var(--shadow-card);
}

.tab-bar button:hover:not(.active) {
  color: var(--text);
  background: var(--bg-subtle);
}

.import-panel {
  background: var(--surface);
  border-radius: 16px;
  padding: 32px 40px;
  box-shadow: var(--shadow-outline), var(--shadow-soft);
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
</style>
