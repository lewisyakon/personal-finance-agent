// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SettingsView from '../src/views/SettingsView.vue'
import {
  createBackup,
  deleteAllData,
  fetchBackups,
  fetchLocalDataStatus,
  requestConfirmation,
} from '../src/api/dataManagement'

vi.mock('../src/api/dataManagement', () => ({
  fetchLocalDataStatus: vi.fn(),
  fetchBackups: vi.fn(),
  requestConfirmation: vi.fn(),
  createBackup: vi.fn(),
  restoreBackup: vi.fn(),
  exportData: vi.fn(),
  deleteAllData: vi.fn(),
}))

const status = {
  release_mode: 'local_web' as const,
  data_directory: '/var/lib/personal-finance-agent',
  database_size_bytes: 4096,
  raw_file_count: 1,
  backup_count: 0,
  raw_file_ttl_minutes: 60,
  upgrade_strategy: 'backup_before_schema_change' as const,
}

describe('stage 11 local data controls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchLocalDataStatus).mockResolvedValue(status)
    vi.mocked(fetchBackups).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(requestConfirmation).mockResolvedValue({
      action: 'backup',
      target_id: null,
      confirmation_token: 'token-token-token-token-token-token-1234',
      expires_at: '2026-09-20T12:00:00Z',
    })
    vi.mocked(createBackup).mockResolvedValue({
      id: 'a'.repeat(32),
      kind: 'manual',
      created_at: '2026-09-20T12:00:00Z',
      size_bytes: 4096,
      sha256: 'b'.repeat(64),
      schema_fingerprint: 'c'.repeat(64),
    })
    vi.mocked(deleteAllData).mockResolvedValue({
      deleted_rows: 3,
      deleted_raw_files: 1,
      deleted_backup_files: 1,
      deleted_log_files: 1,
    })
    vi.spyOn(window, 'prompt').mockReturnValue('创建本地备份')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('shows the fixed data policy and requires the typed phrase for backup', async () => {
    const wrapper = mount(SettingsView)
    await flushPromises()

    expect(wrapper.text()).toContain('/var/lib/personal-finance-agent')
    expect(wrapper.text()).toContain('60 分钟')
    expect(wrapper.text()).toContain('导出不包含上传的原始账单')

    await wrapper.get('[data-testid="backup"]').trigger('click')
    await flushPromises()
    expect(requestConfirmation).toHaveBeenCalledWith('backup', '创建本地备份', undefined)
    expect(createBackup).toHaveBeenCalledWith('token-token-token-token-token-token-1234')
  })

  it('requires both destructive confirmation and the exact delete phrase', async () => {
    vi.mocked(window.prompt).mockReturnValue('删除全部数据')
    vi.mocked(requestConfirmation).mockResolvedValue({
      action: 'delete_all',
      target_id: null,
      confirmation_token: 'delete-token-delete-token-delete-token',
      expires_at: '2026-09-20T12:00:00Z',
    })
    const wrapper = mount(SettingsView)
    await flushPromises()

    await wrapper.get('[data-testid="delete-all"]').trigger('click')
    await flushPromises()
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(requestConfirmation).toHaveBeenCalledWith('delete_all', '删除全部数据', undefined)
    expect(deleteAllData).toHaveBeenCalledWith('delete-token-delete-token-delete-token')
  })
})
