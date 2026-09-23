import type { DeveloperRunDetail, DeveloperRunSummary, EvaluationComparison, EvaluationSummary, FailureSample } from '../types/developer'

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: { message?: string } } | null
    throw new Error(body?.detail?.message || `请求失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<T>
}

export async function fetchDeveloperRuns(): Promise<DeveloperRunSummary[]> {
  const response = await parseResponse<{ items: DeveloperRunSummary[] }>(
    await fetch('/api/v1/developer/runs?page_size=50'),
  )
  return response.items
}

export async function fetchDeveloperRun(id: string): Promise<DeveloperRunDetail> {
  return parseResponse<DeveloperRunDetail>(await fetch(`/api/v1/developer/runs/${id}`))
}

export async function fetchEvaluations(): Promise<EvaluationSummary[]> {
  const response = await parseResponse<{ items: EvaluationSummary[] }>(await fetch('/api/v1/developer/eval-runs'))
  return response.items
}

export async function fetchComparisons(): Promise<EvaluationComparison[]> {
  const response = await parseResponse<{ items: EvaluationComparison[] }>(
    await fetch('/api/v1/developer/comparisons'),
  )
  return response.items
}

export async function fetchFailures(): Promise<FailureSample[]> {
  const response = await parseResponse<{ items: FailureSample[] }>(await fetch('/api/v1/developer/failures'))
  return response.items
}
