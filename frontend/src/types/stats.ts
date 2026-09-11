export type StatsDirection = 'expense' | 'income'
export type StatsGranularity = 'day' | 'week' | 'month' | 'year'

export interface StatsPeriod {
  start: string
  end: string
  timezone: string
}

export interface BudgetStatus {
  budget_minor: number
  used_minor: number
  remaining_minor: number
  over_budget_minor: number
  utilization_percent: number
}

export interface StatsSummary {
  period: StatsPeriod
  currency: string
  transaction_count: number
  expense_count: number
  income_count: number
  transfer_count: number
  refund_count: number
  excluded_count: number
  expense_minor: number
  income_minor: number
  refund_minor: number
  net_flow_minor: number
  fixed_expense_count: number
  variable_expense_count: number
  fixed_expense_minor: number
  variable_expense_minor: number
  budget: BudgetStatus | null
}

export interface CategoryBreakdownItem {
  category: string
  primary_category: string
  secondary_category: string | null
  amount_minor: number
  transaction_count: number
  share_percent: number
}

export interface CategoryBreakdown {
  period: StatsPeriod
  currency: string
  direction: StatsDirection
  items: CategoryBreakdownItem[]
}

export interface TrendItem {
  bucket_start: string
  bucket_end: string
  label: string
  transaction_count: number
  expense_count: number
  income_count: number
  transfer_count: number
  refund_count: number
  expense_minor: number
  income_minor: number
  refund_minor: number
  net_flow_minor: number
  fixed_expense_minor: number
  variable_expense_minor: number
}

export interface TrendResponse {
  period: StatsPeriod
  currency: string
  granularity: StatsGranularity
  items: TrendItem[]
}

export interface MerchantRankingItem {
  merchant: string
  amount_minor: number
  transaction_count: number
  share_percent: number
}

export interface MerchantRanking {
  period: StatsPeriod
  currency: string
  direction: StatsDirection
  items: MerchantRankingItem[]
}

export interface LargeTransactionItem {
  id: number
  occurred_at: string
  merchant: string
  description: string
  direction: StatsDirection
  amount_minor: number
  currency: string
  status: string
  category: string | null
}

export interface LargeTransactionResponse {
  period: StatsPeriod
  currency: string
  direction: StatsDirection
  threshold_minor: number
  items: LargeTransactionItem[]
}

export interface FixedVariableBreakdown {
  period: StatsPeriod
  currency: string
  fixed_count: number
  variable_count: number
  fixed_minor: number
  variable_minor: number
}

export interface ComparisonMetric {
  current: number
  comparison: number
  delta: number
  delta_percent: number | null
}

export interface ComparisonResponse {
  current: StatsSummary
  comparison: StatsSummary
  comparison_mode: 'previous' | 'yoy'
  metrics: Record<string, ComparisonMetric>
}

export interface BudgetResponse {
  period: StatsPeriod
  budget: BudgetStatus
}
