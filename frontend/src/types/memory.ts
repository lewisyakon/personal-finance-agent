export interface MemoryRecord {
  id: string
  scope: 'session' | 'long_term' | 'knowledge'
  kind: string
  key: string
  value: Record<string, unknown>
  source: 'user_confirmed'
  source_ref_type: string | null
  source_ref_id: string | null
  status: 'active' | 'superseded' | 'deleted' | 'expired'
  version: number
  supersedes_id: string | null
  expires_at: string | null
  created_at: string
  updated_at: string
}
