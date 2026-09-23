export type DataAction = 'export' | 'delete_all' | 'backup' | 'restore'

export interface LocalDataStatus {
  release_mode: 'local_web'
  data_directory: string
  database_size_bytes: number
  raw_file_count: number
  backup_count: number
  raw_file_ttl_minutes: number
  upgrade_strategy: 'backup_before_schema_change'
}

export interface BackupRecord {
  id: string
  kind: 'manual' | 'pre_restore' | 'pre_upgrade'
  created_at: string
  size_bytes: number
  sha256: string
  schema_fingerprint: string
}

export interface BackupList {
  items: BackupRecord[]
  total: number
}

export interface ConfirmationToken {
  action: DataAction
  target_id: string | null
  confirmation_token: string
  expires_at: string
}

export interface RestoreResult {
  restored_backup: BackupRecord
  safety_backup: BackupRecord
}

export interface DeleteAllResult {
  deleted_rows: number
  deleted_raw_files: number
  deleted_backup_files: number
  deleted_log_files: number
}

export interface DataExport {
  blob: Blob
  filename: string
}
