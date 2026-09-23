// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import DeveloperView from '../src/views/DeveloperView.vue'

vi.mock('../src/api/developer', () => ({
  fetchDeveloperRuns: vi.fn().mockResolvedValue([
    {
      id: 'run-1', status: 'succeeded', workflow: 'planner', provider: 'mock', model: 'test',
      step_count: 3, tool_call_count: 1, model_call_count: 1, total_tokens: 2,
      estimated_cost_microusd: 0, duration_ms: 12, error_code: null, started_at: '2026-01-01T00:00:00Z',
    },
  ]),
  fetchDeveloperRun: vi.fn().mockResolvedValue({
    run: {
      id: 'run-1', status: 'succeeded', workflow: 'planner', provider: 'mock', model: 'test',
      user_query: '综合分析', answer: '完成', evidence_refs: ['ev_1'], tool_names: ['get_spending_summary'],
      agent_steps: [
        { sequence: 1, node: 'planner', status: 'succeeded', input_summary: {}, output_summary: {}, duration_ms: 2, error_code: null },
        { sequence: 2, node: 'analysis', status: 'succeeded', input_summary: {}, output_summary: {}, duration_ms: 4, error_code: null },
      ],
      model_calls: [],
    },
    tool_traces: [{ evidence_id: 'ev_1', tool_name: 'get_spending_summary', status: 'success', duration_ms: 4, error_code: null, started_at: '2026-01-01T00:00:00Z' }],
    plans: [{ version: 1, status: 'valid', tasks: [{ task_id: 'summary', agent: 'analysis', tool_name: 'get_spending_summary', depends_on: [] }], validation_error_codes: [], replan_reason: null }],
    memory_accesses: [{ status: 'hit', matched_memory_ids: ['memory-1'], reason: 'matched_active_user_confirmed_memory', created_at: '2026-01-01T00:00:00Z' }],
  }),
  fetchEvaluations: vi.fn().mockResolvedValue([
    {
      id: 'eval-1', comparison_group_id: 'group-1', dataset_version: 'stage5-v1', workflow: 'multi',
      provider: 'mock', model: 'test', status: 'passed', case_count: 30, passed_count: 30,
      tool_selection_accuracy: 1, numeric_accuracy: 1, task_completion_rate: 1, evidence_coverage: 1,
      hallucination_rate: 0, routing_accuracy: 1, average_handoff_count: 3, average_latency_ms: 10,
      p50_latency_ms: 9, p95_latency_ms: 15, total_tokens: 180, estimated_cost_microusd: 0,
      started_at: '2026-01-01T00:00:00Z',
    },
  ]),
  fetchComparisons: vi.fn().mockResolvedValue([
    {
      comparison_group_id: 'comparison-stage9', dataset_version: 'stage5-v1',
      items: [
        {
          id: 'eval-1', comparison_group_id: 'comparison-stage9', dataset_version: 'stage5-v1', workflow: 'single',
          provider: 'mock', model: 'test', status: 'passed', case_count: 30, passed_count: 30,
          tool_selection_accuracy: 1, numeric_accuracy: 1, task_completion_rate: 1, evidence_coverage: 1,
          hallucination_rate: 0, routing_accuracy: 1, average_handoff_count: 0, average_latency_ms: 8,
          p50_latency_ms: 7, p95_latency_ms: 12, total_tokens: 120, estimated_cost_microusd: 0,
          started_at: '2026-01-01T00:00:00Z',
        },
      ],
    },
  ]),
  fetchFailures: vi.fn().mockResolvedValue([
    { id: 'failure-1', case_id: 'case-3', workflow: 'multi', error_stage: 'verification', error_code: 'VERIFICATION_FAILED', created_at: '2026-01-01T00:00:00Z' },
  ]),
}))

describe('stage 9 developer console', () => {
  it('renders graph, tool evidence, evaluation metrics and failure samples', async () => {
    const wrapper = mount(DeveloperView)
    await flushPromises()

    expect(wrapper.text()).toContain('Developer Console')
    expect(wrapper.text()).toContain('planner')
    expect(wrapper.text()).toContain('get_spending_summary')
    expect(wrapper.text()).toContain('stage5-v1')
    expect(wrapper.text()).toContain('架构对比')
    expect(wrapper.text()).toContain('comparison-stage9')
    expect(wrapper.text()).toContain('matched_active_user_confirmed_memory')
    expect(wrapper.text()).toContain('VERIFICATION_FAILED')
    expect(wrapper.findAll('.node')).toHaveLength(2)
  })
})
