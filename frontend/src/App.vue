<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="app-shell">
    <nav class="global-nav" aria-label="主导航">
      <RouterLink to="/" class="brand">个人消费分析</RouterLink>
      <div class="nav-links">
        <RouterLink to="/dashboard">Dashboard</RouterLink>
        <RouterLink to="/imports">导入账单</RouterLink>
        <RouterLink to="/transactions">交易管理</RouterLink>
        <RouterLink to="/developer">Developer</RouterLink>
        <RouterLink to="/memories">记忆</RouterLink>
        <RouterLink to="/settings">设置</RouterLink>
      </div>
    </nav>
    <RouterView />
  </div>
</template>

<style scoped>
.global-nav { max-width: 1200px; margin: 0 auto; padding: 18px 24px 0; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.brand { color: #0f172a; font-weight: 700; text-decoration: none; }
.nav-links { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 16px; }
.nav-links a { color: #475569; text-decoration: none; font-size: 14px; }
.nav-links a.router-link-active { color: #2563eb; font-weight: 600; }
</style>
