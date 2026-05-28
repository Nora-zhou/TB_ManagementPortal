<script setup>
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <div class="app-shell">
    <header class="site-nav">
      <div class="nav-inner">
        <router-link to="/products" class="nav-brand">
          <span class="brand-icon">🌱</span>
          <span class="brand-name">电商数据分析</span>
        </router-link>

        <nav class="nav-links">
          <router-link to="/" class="nav-link" active-class="nav-link--active" exact-active-class="nav-link--active">首页</router-link>
          <router-link to="/products" class="nav-link" active-class="nav-link--active">商品列表</router-link>
          <router-link to="/orders/dashboard" class="nav-link" active-class="nav-link--active">订单分析</router-link>
          <router-link to="/orders" class="nav-link" active-class="nav-link--active" exact-active-class="nav-link--active">订单列表</router-link>
          <div class="nav-dropdown">
            <span class="nav-link nav-link--dropdown" :class="{ 'nav-link--active': route.path === '/import' || route.path.startsWith('/products/sku') }">
              基础配置 <span class="dropdown-arrow">▾</span>
            </span>
            <div class="dropdown-menu">
              <router-link to="/import" class="dropdown-item" active-class="dropdown-item--active">数据导入</router-link>
              <router-link to="/products/sku-costs" class="dropdown-item" active-class="dropdown-item--active">SKU 成本配置</router-link>
            </div>
          </div>
          <router-link to="/suppliers" class="nav-link" active-class="nav-link--active">供应商管理</router-link>
        </nav>
      </div>
    </header>

    <main class="site-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--bg);
  display: flex;
  flex-direction: column;
}

/* ── Nav ── */
.site-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border-subtle);
}

.nav-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: var(--text);
}

.brand-icon {
  font-size: 18px;
  line-height: 1;
}

.brand-name {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.15px;
  color: var(--text);
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav-link {
  padding: 6px 14px;
  border-radius: 9999px;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.14px;
  text-decoration: none;
  color: var(--text-muted);
  transition: color 0.15s, background 0.15s;
}

.nav-link:hover {
  color: var(--text);
  background: var(--bg-subtle);
}

.nav-link--active {
  color: var(--text);
  background: var(--bg-subtle);
}

/* ── Dropdown ── */
.nav-dropdown {
  position: relative;
}

.nav-link--dropdown {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 2px;
}

.dropdown-arrow {
  font-size: 10px;
  opacity: 0.6;
}

.dropdown-menu {
  display: none;
  position: absolute;
  top: 100%;
  left: 0;
  min-width: 140px;
  background: #fff;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  padding: 6px;
  padding-top: 10px;
  z-index: 200;
}

.nav-dropdown:hover .dropdown-menu {
  display: block;
}

.dropdown-item {
  display: block;
  padding: 7px 12px;
  border-radius: 7px;
  font-size: 13.5px;
  font-weight: 500;
  text-decoration: none;
  color: var(--text-muted);
  transition: color 0.12s, background 0.12s;
}

.dropdown-item:hover,
.dropdown-item--active {
  color: var(--text);
  background: var(--bg-subtle);
}

/* ── Main ── */
.site-main {
  flex: 1;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  padding: 32px 24px 64px;
}
</style>
