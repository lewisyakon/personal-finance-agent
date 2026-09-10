export interface BillImport {
  id: string
  owner_id: string
  source: string
  format: string
  file_name: string
  file_sha256: string
  status: 'pending' | 'processing' | 'completed' | 'partial' | 'failed' | 'cancelled'
  error_summary: string | null
  total_rows: number
  success_rows: number
  duplicate_rows: number
  skipped_rows: number
  failed_rows: number
  pending_confirmation_rows: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  raw_file_available: boolean
  idempotent_reuse: boolean
}

export interface ImportList {
  items: BillImport[]
  total: number
  page: number
  page_size: number
}

export interface Transaction {
  id: number
  owner_id: string
  bill_import_id: string
  fingerprint: string
  platform: string
  occurred_at: string
  direction: string
  amount_minor: number
  currency: string
  status: string
  merchant: string
  description: string
  payment_method: string
  platform_category: string
  category: string | null
  category_source: string | null
  category_confidence: number | null
  source_transaction_id: string | null
  source_row: number
  created_at: string
  updated_at: string
}

export interface TransactionList {
  items: Transaction[]
  total: number
  page: number
  page_size: number
}
