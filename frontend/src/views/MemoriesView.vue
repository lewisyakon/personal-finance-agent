<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { createMemory, deleteMemory, fetchMemories, updateMemory } from '../api/memory'
import type { MemoryRecord } from '../types/memory'

const memories = ref<MemoryRecord[]>([])
const error = ref('')
const message = ref('')
const drafts = reactive<Record<string, string>>({})
const form = reactive({ scope: 'knowledge' as MemoryRecord['scope'], kind: 'preference', key: '', value: '{}' })

function syncDrafts() {
  for (const item of memories.value) drafts[item.id] = JSON.stringify(item.value, null, 2)
}

async function load() {
  try {
    memories.value = await fetchMemories()
    syncDrafts()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '加载记忆失败'
  }
}

async function addMemory() {
  error.value = ''; message.value = ''
  try {
    await createMemory({ scope: form.scope, kind: form.kind, key: form.key, value: JSON.parse(form.value) })
    form.key = ''; form.value = '{}'; message.value = '已保存用户确认记忆'
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '保存失败' }
}

async function save(item: MemoryRecord) {
  error.value = ''; message.value = ''
  try {
    await updateMemory(item.id, JSON.parse(drafts[item.id]))
    message.value = '已创建新版本并保留来源链'
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '修改失败' }
}

async function remove(item: MemoryRecord) {
  error.value = ''; message.value = ''
  try {
    await deleteMemory(item.id)
    message.value = '已删除；后续检索不会再使用此记忆'
    await load()
  } catch (caught) { error.value = caught instanceof Error ? caught.message : '删除失败' }
}

onMounted(load)
</script>

<template>
  <main class="memory-page">
    <header>
      <p class="eyebrow">USER-CONTROLLED MEMORY</p>
      <h1>记忆与个性化</h1>
      <p>会话状态、长期偏好和知识分开保存。只有明确确认的内容会进入长期记忆。</p>
    </header>

    <p v-if="error" class="notice error">{{ error }}</p>
    <p v-if="message" class="notice success">{{ message }}</p>

    <section class="panel create-panel">
      <h2>新增确认记忆</h2>
      <label>范围<select v-model="form.scope"><option value="session">会话</option><option value="long_term">长期偏好</option><option value="knowledge">知识</option></select></label>
      <label>类型<input v-model="form.kind"></label>
      <label>Key<input v-model="form.key" placeholder="例如：报告语言"></label>
      <label class="wide">JSON Value<textarea v-model="form.value" rows="4" /></label>
      <button type="button" @click="addMemory">确认并保存</button>
    </section>

    <section class="memory-grid">
      <article v-for="item in memories" :key="item.id" class="memory-card">
        <div class="card-heading">
          <div><span>{{ item.scope }}</span><h2>{{ item.key }}</h2></div>
          <strong>v{{ item.version }}</strong>
        </div>
        <p>{{ item.kind }} · {{ item.source }}</p>
        <textarea v-model="drafts[item.id]" rows="6" aria-label="记忆 JSON" />
        <div class="actions"><button type="button" @click="save(item)">保存新版本</button><button class="danger" type="button" @click="remove(item)">删除</button></div>
        <small v-if="item.expires_at">过期：{{ item.expires_at }}</small>
      </article>
    </section>
    <p v-if="!memories.length" class="empty">尚无有效记忆。模型推测不会出现在这里。</p>
  </main>
</template>

<style scoped>
.memory-page { max-width: 1100px; margin: 0 auto; padding: 44px 24px 80px; }
header { margin-bottom: 26px; } h1 { margin: 6px 0 10px; font-size: clamp(32px,5vw,54px); }.eyebrow { color: #7c3aed; font-size: 12px; font-weight: 800; letter-spacing: .16em; }
.panel,.memory-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 18px; box-shadow: 0 12px 30px rgba(15,23,42,.05); }
.create-panel { display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; padding: 20px; }.create-panel h2,.wide { grid-column: 1 / -1; }
label { display: grid; gap: 6px; color: #475569; font-size: 13px; } input,select,textarea { width: 100%; border: 1px solid #cbd5e1; border-radius: 10px; padding: 10px; font: inherit; background: #fff; }
button { border: 0; border-radius: 10px; padding: 10px 14px; color: #fff; background: #4f46e5; cursor: pointer; }.danger { background: #fff; color: #b91c1c; border: 1px solid #fecaca; }
.memory-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(290px,1fr)); gap: 16px; margin-top: 22px; }.memory-card { padding: 18px; }.card-heading { display: flex; justify-content: space-between; gap: 16px; }.card-heading span { color: #7c3aed; font-size: 12px; text-transform: uppercase; }.card-heading h2 { margin: 4px 0; }.actions { display: flex; gap: 8px; margin-top: 10px; }.notice,.empty { color: #64748b; }.error { color: #b91c1c; }.success { color: #166534; }
@media (max-width: 700px) { .create-panel { grid-template-columns: 1fr; }.create-panel h2,.wide { grid-column: auto; } }
</style>
