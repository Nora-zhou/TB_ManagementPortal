import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import './style.css'
import App from './App.vue'
import ProductList from './components/ProductList.vue'
import ProductDetail from './components/ProductDetail.vue'
import OrderList from './components/OrderList.vue'
import OrderDashboard from './components/OrderDashboard.vue'
import DataImport from './components/DataImport.vue'
import SupplierManagement from './components/SupplierManagement.vue'
import SupplierDashboard from './components/SupplierDashboard.vue'
import HomeDashboard from './components/HomeDashboard.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: HomeDashboard },
    { path: '/products', component: ProductList },
    { path: '/products/:id', component: ProductDetail },
    { path: '/orders', component: OrderList },
    { path: '/orders/dashboard', component: OrderDashboard },
    { path: '/import', component: DataImport },
    { path: '/suppliers', component: SupplierManagement },
    { path: '/suppliers/dashboard', component: SupplierDashboard },
  ],
})

createApp(App).use(router).mount('#app')
