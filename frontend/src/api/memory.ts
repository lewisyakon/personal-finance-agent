import type { MemoryRecord } from '../types/memory'

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: { message?: string } } | null
    throw new Error(body?.detail?.message || `请求失败（HTTP ${response.status}）`)
  }
  return response.status === 204 ? (undefined as T) : (response.json() as Promise<T>)
}

export async function fetchMemories(): Promise<MemoryRecord[]> {
  const result = await parseResponse<{ items: MemoryRecord[] }>(await fetch('/api/v1/memories'))
  return result.items
}

export async function createMemory(payload: {
  scope: MemoryRecord['scope']
  kind: string
  key: string
  value: Record<string, unknown>
}): Promise<MemoryRecord> {
  return parseResponse<MemoryRecord>(await fetch('/api/v1/memories', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }))
}

export async function updateMemory(id: string, value: Record<string, unknown>): Promise<MemoryRecord> {
  return parseResponse<MemoryRecord>(await fetch(`/api/v1/memories/${id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ value }),
  }))
}

export async function deleteMemory(id: string): Promise<void> {
  await parseResponse<void>(await fetch(`/api/v1/memories/${id}`, { method: 'DELETE' }))
}
