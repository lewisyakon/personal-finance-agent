// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MemoriesView from '../src/views/MemoriesView.vue'
import { createMemory, deleteMemory, fetchMemories, updateMemory } from '../src/api/memory'

vi.mock('../src/api/memory', () => ({
  fetchMemories: vi.fn(),
  createMemory: vi.fn(),
  updateMemory: vi.fn(),
  deleteMemory: vi.fn(),
}))

const item = {
  id: 'memory-1',
  scope: 'long_term' as const,
  kind: 'budget_preference',
  key: '2026-01-01:2026-02-01',
  value: { budget_minor: 120000 },
  source: 'user_confirmed' as const,
  source_ref_type: 'budget_plan',
  source_ref_id: 'budget-1',
  status: 'active' as const,
  version: 1,
  supersedes_id: null,
  expires_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('stage 10 user-controlled memory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchMemories).mockResolvedValue([item])
    vi.mocked(createMemory).mockResolvedValue(item)
    vi.mocked(updateMemory).mockResolvedValue({ ...item, version: 2 })
    vi.mocked(deleteMemory).mockResolvedValue()
  })

  it('shows provenance and lets the user version or delete a memory', async () => {
    const wrapper = mount(MemoriesView)
    await flushPromises()

    expect(wrapper.text()).toContain('只有明确确认的内容会进入长期记忆')
    expect(wrapper.text()).toContain('user_confirmed')
    expect(wrapper.text()).toContain('2026-01-01:2026-02-01')

    await wrapper.get('article textarea').setValue('{"budget_minor":130000}')
    await wrapper.get('.actions button').trigger('click')
    await flushPromises()
    expect(updateMemory).toHaveBeenCalledWith('memory-1', { budget_minor: 130000 })

    await wrapper.get('.danger').trigger('click')
    await flushPromises()
    expect(deleteMemory).toHaveBeenCalledWith('memory-1')
  })
})
