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
          <router-link to="/products" class="nav-link" active-class="nav-link--active">商品列表</router-link>
          <router-link to="/orders/dashboard" class="nav-link" active-class="nav-link--active">订单分析</router-link>
          <router-link to="/orders" class="nav-link" active-class="nav-link--active" exact-active-class="nav-link--active">订单列表</router-link>
          <router-link to="/import" class="nav-link nav-link--pill" active-class="nav-link--pill-active">数据导入</router-link>
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

.nav-link--pill {
  background: #000;
  color: #fff !important;
  padding: 6px 16px;
}

.nav-link--pill:hover {
  background: #222;
  color: #fff;
}

.nav-link--pill-active {
  background: #222;
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
