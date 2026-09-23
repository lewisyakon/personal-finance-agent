import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import ImportView from '../views/ImportView.vue'
import DashboardView from '../views/DashboardView.vue'
import TransactionsView from '../views/TransactionsView.vue'
import DeveloperView from '../views/DeveloperView.vue'
import MemoriesView from '../views/MemoriesView.vue'
import SettingsView from '../views/SettingsView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/dashboard', name: 'dashboard', component: DashboardView },
    { path: '/imports', name: 'imports', component: ImportView },
    { path: '/transactions', name: 'transactions', component: TransactionsView },
    { path: '/developer', name: 'developer', component: DeveloperView },
    { path: '/memories', name: 'memories', component: MemoriesView },
    { path: '/settings', name: 'settings', component: SettingsView },
  ],
})
