<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { fetchSystemStatus } from '../api/system'
import type { SystemStatus } from '../types/system'

const status = ref<SystemStatus | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    status.value = await fetchSystemStatus()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法获取系统状态'
  }
})
</script>

<template>
  <main class="page">
    <header>
      <p class="eyebrow">LOCAL-FIRST PERSONAL FINANCE</p>
      <h1>个人消费分析</h1>
      <p class="subtitle">阶段 2 导入、去重与交易管理</p>
    </header>

    <section class="status-card" aria-labelledby="status-title">
      <h2 id="status-title">系统状态</h2>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div v-else-if="!status" class="muted">正在检查 API、数据库和模型……</div>
      <div v-else class="status-grid">
        <div v-for="(component, name) in status" :key="name" class="status-item">
          <span class="status-dot" :class="{ healthy: component.available }" aria-hidden="true" />
          <div>
            <strong>{{ name }}</strong>
            <p>{{ component.available ? '可用' : '不可用' }} · {{ component.message }}</p>
          </div>
        </div>
      </div>
    </section>
    <nav class="quick-links" aria-label="主要功能">
      <RouterLink to="/imports">导入账单</RouterLink>
      <RouterLink to="/transactions">交易管理</RouterLink>
    </nav>
  </main>
</template>

<style scoped>
.page { max-width: 960px; margin: 0 auto; padding: 64px 24px; }
.eyebrow { color: #64748b; font-size: 12px; letter-spacing: .12em; }
h1 { margin: 8px 0; font-size: clamp(32px, 6vw, 56px); }
.subtitle, .muted { color: #64748b; }
.status-card { margin-top: 48px; padding: 24px; background: white; border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 10px 30px rgb(15 23 42 / 5%); }
.status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
.status-item { display: flex; gap: 12px; align-items: flex-start; padding: 16px; border-radius: 12px; background: #f8fafc; }
.status-item p { margin: 6px 0 0; color: #64748b; font-size: 14px; }
.status-dot { width: 10px; height: 10px; margin-top: 5px; border-radius: 50%; background: #ef4444; }
.status-dot.healthy { background: #22c55e; }
.error { color: #b91c1c; }
.quick-links { display: flex; gap: 12px; margin-top: 20px; }
.quick-links a { color: #2563eb; text-decoration: none; padding: 10px 14px; border: 1px solid #bfdbfe; border-radius: 8px; background: #eff6ff; }
</style>
