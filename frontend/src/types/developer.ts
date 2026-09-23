export interface DeveloperRunSummary {
  id: string
  status: string
  workflow: string
  provider: string
  model: string
  step_count: number
  tool_call_count: number
  model_call_count: number
  total_tokens: number
  estimated_cost_microusd: number
  duration_ms: number
  error_code: string | null
  started_at: string
}

export interface AgentStep {
  sequence: number
  node: string
  status: string
  input_summary: Record<string, unknown>
  output_summary: Record<string, unknown>
  duration_ms: number
  error_code: string | null
}

export interface DeveloperRunDetail {
  run: DeveloperRunSummary & {
    user_query: string
    answer: string | null
    evidence_refs: string[]
    tool_names: string[]
    agent_steps: AgentStep[]
    model_calls: Array<{
      sequence: number
      status: string
      provider: string
      model: string
      latency_ms: number
      total_tokens: number
      error_code: string | null
    }>
  }
  tool_traces: Array<{
    evidence_id: string
    tool_name: string
    status: string
    duration_ms: number
    error_code: string | null
    started_at: string
  }>
  plans: Array<{
    version: number
    status: string
    tasks: Array<{ task_id: string; agent: string; tool_name: string; depends_on: string[] }>
    validation_error_codes: string[]
    replan_reason: string | null
  }>
  memory_accesses: Array<{
    status: string
    matched_memory_ids: string[]
    reason: string
    created_at: string
  }>
}

export interface EvaluationSummary {
  id: string
  comparison_group_id: string | null
  dataset_version: string
  workflow: string
  provider: string
  model: string
  status: string
  case_count: number
  passed_count: number
  tool_selection_accuracy: number
  numeric_accuracy: number
  task_completion_rate: number
  evidence_coverage: number
  hallucination_rate: number
  routing_accuracy: number
  average_handoff_count: number
  average_latency_ms: number
  p50_latency_ms: number
  p95_latency_ms: number
  total_tokens: number
  estimated_cost_microusd: number
  started_at: string
}

export interface EvaluationComparison {
  comparison_group_id: string
  dataset_version: string
  items: EvaluationSummary[]
}

export interface FailureSample {
  id: string
  case_id: string
  workflow: string
  error_stage: string
  error_code: string | null
  created_at: string
}
