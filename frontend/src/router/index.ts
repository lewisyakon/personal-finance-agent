import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import ImportView from '../views/ImportView.vue'
import TransactionsView from '../views/TransactionsView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/imports', name: 'imports', component: ImportView },
    { path: '/transactions', name: 'transactions', component: TransactionsView },
  ],
})
