import type { BillImport, ImportList, Transaction, TransactionList } from '../types/finance'

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: { message?: string } } | null
    throw new Error(body?.detail?.message || `请求失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<T>
}

export async function uploadBill(file: File): Promise<BillImport> {
  const data = new FormData()
  data.append('file', file)
  return parseResponse<BillImport>(await fetch('/api/v1/imports', { method: 'POST', body: data }))
}

export async function fetchImports(): Promise<ImportList> {
  return parseResponse<ImportList>(await fetch('/api/v1/imports?page_size=50'))
}

export async function fetchTransactions(filters: {
  page?: number
  pageSize?: number
  category?: string
  merchant?: string
} = {}): Promise<TransactionList> {
  const params = new URLSearchParams({ page: String(filters.page || 1), page_size: String(filters.pageSize || 50) })
  if (filters.category) params.set('category', filters.category)
  if (filters.merchant) params.set('merchant', filters.merchant)
  return parseResponse<TransactionList>(await fetch(`/api/v1/transactions?${params}`))
}

export async function fetchTransaction(id: number): Promise<Transaction> {
  return parseResponse<Transaction>(await fetch(`/api/v1/transactions/${id}`))
}

export async function updateTransactionCategory(id: number, category: string | null): Promise<Transaction> {
  const response = await fetch(`/api/v1/transactions/${id}/category`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category }),
  })
  const result = await parseResponse<{ transaction: Transaction }>(response)
  return result.transaction
}
