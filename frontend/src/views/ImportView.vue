<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchImports, uploadBill } from '../api/finance'
import type { BillImport } from '../types/finance'

const imports = ref<BillImport[]>([])
const busy = ref(false)
const error = ref('')

async function refresh() {
  try {
    imports.value = (await fetchImports()).items
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取导入任务'
  }
}

async function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busy.value = true
  error.value = ''
  try {
    const result = await uploadBill(file)
    imports.value = [result, ...imports.value.filter((item) => item.id !== result.id)]
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '导入失败'
  } finally {
    busy.value = false
    input.value = ''
  }
}

onMounted(refresh)
</script>

<template>
  <main class="finance-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">IMPORTS</p>
        <h1>导入账单</h1>
        <p class="muted">上传微信导出的 CSV 或 XLSX，系统会自动解析、去重并保留导入报告。</p>
      </div>
      <label class="upload-button">
        {{ busy ? '处理中…' : '选择 CSV/XLSX' }}
        <input
          type="file"
          accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          :disabled="busy"
          @change="onFile"
        >
      </label>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <section class="panel">
      <h2>导入记录</h2>
      <div v-if="!imports.length" class="muted">还没有导入任务。</div>
      <div v-for="item in imports" :key="item.id" class="import-row">
        <div>
          <strong>{{ item.file_name }}</strong>
          <p class="muted">{{ new Date(item.created_at).toLocaleString() }} · {{ item.status }}</p>
        </div>
        <div class="counts">
          <span class="success">成功 {{ item.success_rows }}</span>
          <span class="duplicate">重复 {{ item.duplicate_rows }}</span>
          <span class="skipped">跳过 {{ item.skipped_rows }}</span>
          <span class="failed">失败 {{ item.failed_rows }}</span>
          <span class="pending">待确认 {{ item.pending_confirmation_rows }}</span>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.finance-page { max-width: 1100px; margin: 0 auto; padding: 40px 24px; }
.page-heading { display: flex; justify-content: space-between; gap: 24px; align-items: end; }
h1 { margin: 8px 0; font-size: 40px; }
.eyebrow { color: #64748b; letter-spacing: .12em; font-size: 12px; }
.muted { color: #64748b; }
.panel { margin-top: 28px; padding: 24px; background: white; border: 1px solid #e5e7eb; border-radius: 16px; }
.upload-button { cursor: pointer; color: white; background: #2563eb; padding: 11px 18px; border-radius: 9px; font-weight: 600; }
.upload-button input { display: none; }
.import-row { display: flex; justify-content: space-between; gap: 20px; align-items: center; border-top: 1px solid #f1f5f9; padding: 16px 0; }
.import-row p { margin: 5px 0 0; font-size: 13px; }
.counts { display: flex; flex-wrap: wrap; gap: 8px; font-size: 13px; }
.success { color: #15803d; } .duplicate { color: #a16207; } .skipped, .pending { color: #475569; } .failed, .error { color: #b91c1c; }
@media (max-width: 700px) { .page-heading, .import-row { align-items: flex-start; flex-direction: column; } }
</style>
