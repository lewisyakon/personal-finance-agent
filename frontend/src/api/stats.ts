import type {
  BudgetResponse,
  CategoryBreakdown,
  ComparisonResponse,
  FixedVariableBreakdown,
  LargeTransactionResponse,
  MerchantRanking,
  StatsDirection,
  StatsSummary,
  StatsGranularity,
  TrendResponse,
} from '../types/stats'

export interface StatsQuery {
  from?: string
  to?: string
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: { message?: string } }
      | null
    throw new Error(body?.detail?.message || `请求失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<T>
}

function queryParams(query: StatsQuery): URLSearchParams {
  const params = new URLSearchParams()
  if (query.from) params.set('from', query.from)
  if (query.to) params.set('to', query.to)
  return params
}

function withParams(path: string, params: URLSearchParams): string {
  const value = params.toString()
  return value ? `${path}?${value}` : path
}

export async function fetchStatsSummary(
  query: StatsQuery = {},
  budgetMinor?: number,
): Promise<StatsSummary> {
  const params = queryParams(query)
  if (budgetMinor !== undefined) params.set('budget_minor', String(budgetMinor))
  return parseResponse<StatsSummary>(await fetch(withParams('/api/v1/stats/summary', params)))
}

export async function fetchCategoryBreakdown(
  query: StatsQuery = {},
  direction: StatsDirection = 'expense',
): Promise<CategoryBreakdown> {
  const params = queryParams(query)
  params.set('direction', direction)
  return parseResponse<CategoryBreakdown>(
    await fetch(withParams('/api/v1/stats/categories', params)),
  )
}

export async function fetchTrend(
  query: StatsQuery = {},
  granularity: StatsGranularity = 'day',
): Promise<TrendResponse> {
  const params = queryParams(query)
  params.set('granularity', granularity)
  return parseResponse<TrendResponse>(await fetch(withParams('/api/v1/stats/trend', params)))
}

export async function fetchMerchantRanking(
  query: StatsQuery = {},
  direction: StatsDirection = 'expense',
  limit = 10,
): Promise<MerchantRanking> {
  const params = queryParams(query)
  params.set('direction', direction)
  params.set('limit', String(limit))
  return parseResponse<MerchantRanking>(
    await fetch(withParams('/api/v1/stats/merchants', params)),
  )
}

export async function fetchLargeTransactions(
  query: StatsQuery = {},
  thresholdMinor = 10_000,
  limit = 20,
  direction: StatsDirection = 'expense',
): Promise<LargeTransactionResponse> {
  const params = queryParams(query)
  params.set('threshold_minor', String(thresholdMinor))
  params.set('limit', String(limit))
  params.set('direction', direction)
  return parseResponse<LargeTransactionResponse>(
    await fetch(withParams('/api/v1/stats/large-transactions', params)),
  )
}

export async function fetchFixedVariable(query: StatsQuery = {}): Promise<FixedVariableBreakdown> {
  return parseResponse<FixedVariableBreakdown>(
    await fetch(withParams('/api/v1/stats/fixed-variable', queryParams(query))),
  )
}

export async function fetchBudget(
  budgetMinor: number,
  query: StatsQuery = {},
): Promise<BudgetResponse> {
  const params = queryParams(query)
  params.set('budget_minor', String(budgetMinor))
  return parseResponse<BudgetResponse>(await fetch(withParams('/api/v1/stats/budget', params)))
}

export async function fetchComparison(
  query: StatsQuery = {},
  mode: 'previous' | 'yoy' = 'previous',
): Promise<ComparisonResponse> {
  const params = queryParams(query)
  params.set('mode', mode)
  return parseResponse<ComparisonResponse>(
    await fetch(withParams('/api/v1/stats/comparison', params)),
  )
}
