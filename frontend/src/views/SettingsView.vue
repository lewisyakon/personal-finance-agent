<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  createBackup,
  deleteAllData,
  exportData,
  fetchBackups,
  fetchLocalDataStatus,
  requestConfirmation,
  restoreBackup,
} from '../api/dataManagement'
import type { BackupRecord, DataAction, LocalDataStatus } from '../types/dataManagement'

const phrases: Record<DataAction, string> = {
  export: '导出我的数据',
  backup: '创建本地备份',
  restore: '恢复本地备份',
  delete_all: '删除全部数据',
}

const status = ref<LocalDataStatus | null>(null)
const backups = ref<BackupRecord[]>([])
const loading = ref(true)
const busy = ref(false)
const message = ref('')
const error = ref('')

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function refresh(): Promise<void> {
  const [dataStatus, backupList] = await Promise.all([
    fetchLocalDataStatus(),
    fetchBackups(),
  ])
  status.value = dataStatus
  backups.value = backupList.items
}

async function tokenFor(action: DataAction, targetId?: string): Promise<string | null> {
  if (
    (action === 'delete_all' || action === 'restore')
    && !window.confirm(action === 'delete_all'
      ? '此操作不可撤销，并会删除数据库记录、原始账单、日志和备份。确定继续吗？'
      : '恢复会覆盖当前数据库；系统会先自动创建安全备份。确定继续吗？')
  ) return null
  const phrase = phrases[action]
  const typed = window.prompt(`请输入“${phrase}”以确认此操作`)
  if (typed === null) return null
  const confirmation = await requestConfirmation(action, typed, targetId)
  return confirmation.confirmation_token
}

async function run(operation: () => Promise<void>): Promise<void> {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await operation()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '操作失败'
  } finally {
    busy.value = false
  }
}

function handleExport(): void {
  void run(async () => {
    const token = await tokenFor('export')
    if (!token) return
    const result = await exportData(token)
    const url = URL.createObjectURL(result.blob)
    const link = document.createElement('a')
    link.href = url
    link.download = result.filename
    link.click()
    URL.revokeObjectURL(url)
    message.value = '数据导出已生成；归档不包含原始账单文件。'
  })
}

function handleBackup(): void {
  void run(async () => {
    const token = await tokenFor('backup')
    if (!token) return
    await createBackup(token)
    await refresh()
    message.value = '本地 SQLite 备份已创建并完成完整性校验。'
  })
}

function handleRestore(backup: BackupRecord): void {
  void run(async () => {
    const token = await tokenFor('restore', backup.id)
    if (!token) return
    await restoreBackup(backup.id, token)
    await refresh()
    message.value = '备份已恢复；覆盖前的数据库已另存为安全备份。'
  })
}

function handleDeleteAll(): void {
  void run(async () => {
    const token = await tokenFor('delete_all')
    if (!token) return
    const result = await deleteAllData(token)
    await refresh()
    message.value = `已删除 ${result.deleted_rows} 条记录及本地原始文件、日志和备份。`
  })
}

onMounted(async () => {
  try {
    await refresh()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '设置加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="settings-page">
    <header>
      <p class="eyebrow">LOCAL DATA CONTROL</p>
      <h1>设置与数据安全</h1>
      <p>当前发行形态为仅监听本机回环地址的 Local Web；账单与模型上下文不会自动上传。</p>
    </header>

    <p v-if="loading">正在读取本地数据状态…</p>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="message" class="notice success" role="status">{{ message }}</p>

    <template v-if="status">
      <section class="panel status-grid" aria-label="本地数据状态">
        <div><span>固定数据目录</span><strong>{{ status.data_directory }}</strong></div>
        <div><span>SQLite 大小</span><strong>{{ formatBytes(status.database_size_bytes) }}</strong></div>
        <div><span>原始账单</span><strong>{{ status.raw_file_count }} 个</strong></div>
        <div><span>原始文件保留</span><strong>{{ status.raw_file_ttl_minutes }} 分钟</strong></div>
      </section>

      <section class="panel">
        <h2>导出</h2>
        <p>生成可携带的 JSON ZIP。出于最小化原则，导出不包含上传的原始账单。</p>
        <button data-testid="export" :disabled="busy" @click="handleExport">确认并导出数据</button>
      </section>

      <section class="panel">
        <div class="section-heading">
          <div>
            <h2>SQLite 备份与恢复</h2>
            <p>每次结构升级前自动备份；恢复前还会创建当前数据库的安全快照。</p>
          </div>
          <button data-testid="backup" :disabled="busy" @click="handleBackup">创建备份</button>
        </div>
        <p v-if="!backups.length" class="muted">暂无备份。</p>
        <ul v-else class="backup-list">
          <li v-for="backup in backups" :key="backup.id">
            <div>
              <strong>{{ backup.kind }}</strong>
              <span>{{ new Date(backup.created_at).toLocaleString() }} · {{ formatBytes(backup.size_bytes) }}</span>
              <code>{{ backup.id }}</code>
            </div>
            <button
              :data-testid="`restore-${backup.id}`"
              class="secondary"
              :disabled="busy"
              @click="handleRestore(backup)"
            >
              恢复
            </button>
          </li>
        </ul>
      </section>

      <section class="panel danger-zone">
        <h2>危险操作</h2>
        <p>永久删除全部工作区记录、原始账单、日志与备份。需要两次明确确认，且无法撤销。</p>
        <button data-testid="delete-all" class="danger" :disabled="busy" @click="handleDeleteAll">
          删除全部本地数据
        </button>
      </section>
    </template>
  </main>
</template>

<style scoped>
.settings-page { max-width: 960px; margin: 0 auto; padding: 56px 24px 80px; }
header { margin-bottom: 28px; }
.eyebrow { color: #2563eb; font-size: 12px; font-weight: 800; letter-spacing: .14em; }
h1 { margin: 6px 0 10px; font-size: clamp(30px, 5vw, 46px); color: #0f172a; }
h2 { margin: 0 0 8px; color: #0f172a; }
p { color: #64748b; line-height: 1.6; }
.panel { margin-top: 18px; padding: 24px; border: 1px solid #e2e8f0; border-radius: 18px; background: white; box-shadow: 0 10px 28px rgb(15 23 42 / 5%); }
.status-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.status-grid div { min-width: 0; }
.status-grid span, .backup-list span { display: block; margin-bottom: 6px; color: #64748b; font-size: 13px; }
.status-grid strong { display: block; overflow-wrap: anywhere; color: #0f172a; }
.section-heading, .backup-list li { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
button { border: 0; border-radius: 10px; padding: 10px 16px; background: #2563eb; color: white; cursor: pointer; font-weight: 700; }
button:disabled { cursor: wait; opacity: .55; }
button.secondary { background: #e2e8f0; color: #1e293b; }
.backup-list { margin: 20px 0 0; padding: 0; list-style: none; }
.backup-list li { padding: 15px 0; border-top: 1px solid #e2e8f0; }
.backup-list code { color: #475569; font-size: 11px; }
.danger-zone { border-color: #fecaca; }
button.danger { background: #b91c1c; }
.notice { padding: 12px 16px; border-radius: 10px; }
.notice.error { background: #fee2e2; color: #991b1b; }
.notice.success { background: #dcfce7; color: #166534; }
.muted { font-style: italic; }
@media (max-width: 640px) {
  .status-grid { grid-template-columns: 1fr; }
  .section-heading, .backup-list li { align-items: flex-start; flex-direction: column; }
}
</style>
