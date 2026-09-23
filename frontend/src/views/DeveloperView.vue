<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchComparisons, fetchDeveloperRun, fetchDeveloperRuns, fetchEvaluations, fetchFailures } from '../api/developer'
import type { DeveloperRunDetail, DeveloperRunSummary, EvaluationComparison, EvaluationSummary, FailureSample } from '../types/developer'

const runs = ref<DeveloperRunSummary[]>([])
const detail = ref<DeveloperRunDetail | null>(null)
const evaluations = ref<EvaluationSummary[]>([])
const comparisons = ref<EvaluationComparison[]>([])
const failures = ref<FailureSample[]>([])
const loading = ref(true)
const error = ref('')

const graphNodes = computed(() => detail.value?.run.agent_steps || [])

async function selectRun(id: string) {
  detail.value = await fetchDeveloperRun(id)
}

onMounted(async () => {
  try {
    const [runItems, evalItems, comparisonItems, failureItems] = await Promise.all([
      fetchDeveloperRuns(),
      fetchEvaluations(),
      fetchComparisons(),
      fetchFailures(),
    ])
    runs.value = runItems
    evaluations.value = evalItems
    comparisons.value = comparisonItems
    failures.value = failureItems
    if (runItems[0]) await selectRun(runItems[0].id)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '加载 Developer 数据失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="developer-page">
    <header>
      <p class="eyebrow">LOCAL OBSERVABILITY</p>
      <h1>Developer Console</h1>
      <p>查看 Agent 图、节点摘要、Tool Evidence、错误与版本化评测。此页面仅在本地开发模式开放。</p>
    </header>

    <p v-if="loading" class="notice">正在加载 Trace…</p>
    <p v-else-if="error" class="notice error">{{ error }}</p>

    <template v-else>
      <section class="panel run-layout">
        <div>
          <h2>最近运行</h2>
          <button
            v-for="run in runs"
            :key="run.id"
            class="run-row"
            :class="{ active: detail?.run.id === run.id }"
            type="button"
            @click="selectRun(run.id)"
          >
            <span>{{ run.workflow }}</span>
            <strong>{{ run.status }}</strong>
            <small>{{ run.duration_ms }} ms · {{ run.total_tokens }} tokens</small>
          </button>
          <p v-if="!runs.length" class="empty">还没有 Agent Run。</p>
        </div>

        <div v-if="detail" class="trace-detail">
          <div class="trace-heading">
            <div>
              <h2>Run Trace</h2>
              <code>{{ detail.run.id }}</code>
            </div>
            <span class="status">{{ detail.run.status }}</span>
          </div>

          <div class="graph" aria-label="Agent 执行图">
            <template v-for="(step, index) in graphNodes" :key="`${step.sequence}-${step.node}`">
              <article class="node">
                <strong>{{ step.node }}</strong>
                <span>{{ step.status }}</span>
                <small>{{ step.duration_ms }} ms</small>
                <em v-if="step.error_code">{{ step.error_code }}</em>
              </article>
              <span v-if="index < graphNodes.length - 1" class="arrow">→</span>
            </template>
            <p v-if="!graphNodes.length" class="empty">Single-Agent 快路径没有节点级 Handoff。</p>
          </div>

          <h3>Tool 与 Evidence</h3>
          <div class="tool-grid">
            <article v-for="tool in detail.tool_traces" :key="tool.evidence_id" class="tool-card">
              <strong>{{ tool.tool_name }}</strong>
              <span>{{ tool.status }} · {{ tool.duration_ms }} ms</span>
              <code>{{ tool.evidence_id }}</code>
              <em v-if="tool.error_code">{{ tool.error_code }}</em>
            </article>
            <p v-if="!detail.tool_traces.length" class="empty">没有 Tool Trace。</p>
          </div>

          <h3 v-if="detail.run.model_calls.length">模型调用</h3>
          <div v-if="detail.run.model_calls.length" class="tool-grid">
            <article v-for="call in detail.run.model_calls" :key="call.sequence" class="tool-card">
              <strong>{{ call.provider }} / {{ call.model }}</strong>
              <span>{{ call.status }} · {{ call.latency_ms }} ms · {{ call.total_tokens }} tokens</span>
              <em v-if="call.error_code">{{ call.error_code }}</em>
            </article>
          </div>

          <h3 v-if="detail.plans.length">结构化计划</h3>
          <article v-for="plan in detail.plans" :key="plan.version" class="plan-card">
            <strong>v{{ plan.version }} · {{ plan.status }}</strong>
            <span v-if="plan.replan_reason">触发：{{ plan.replan_reason }}</span>
            <em v-if="plan.validation_error_codes.length">{{ plan.validation_error_codes.join(', ') }}</em>
            <ul>
              <li v-for="task in plan.tasks" :key="task.task_id">
                {{ task.task_id }} / {{ task.agent }} / {{ task.tool_name }}
                <small v-if="task.depends_on.length">依赖 {{ task.depends_on.join(', ') }}</small>
              </li>
            </ul>
          </article>

          <h3 v-if="detail.memory_accesses.length">Memory 检索</h3>
          <article v-for="(access, index) in detail.memory_accesses" :key="index" class="plan-card">
            <strong>{{ access.status }}</strong>
            <span>{{ access.reason }}</span>
            <small>匹配 {{ access.matched_memory_ids.length }} 条用户确认记忆</small>
          </article>
        </div>
      </section>

      <section class="panel">
        <h2>架构对比</h2>
        <article v-for="comparison in comparisons" :key="comparison.comparison_group_id" class="comparison-card">
          <strong>{{ comparison.dataset_version }}</strong>
          <code>{{ comparison.comparison_group_id }}</code>
          <div class="comparison-grid">
            <div v-for="item in comparison.items" :key="item.id">
              <b>{{ item.workflow }}</b>
              <span>完成 {{ (item.task_completion_rate * 100).toFixed(0) }}%</span>
              <span>幻觉 {{ (item.hallucination_rate * 100).toFixed(0) }}%</span>
              <span>P95 {{ item.p95_latency_ms }} ms</span>
              <span>{{ item.total_tokens }} tokens / {{ item.estimated_cost_microusd }} μUSD</span>
            </div>
          </div>
        </article>
        <p v-if="!comparisons.length" class="empty">尚未运行 Single/Multi/Multi+Verifier 同题对比。</p>
      </section>

      <section class="panel">
        <h2>评测指标</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>数据集</th><th>工作流</th><th>完成率</th><th>数值准确率</th><th>Evidence</th><th>幻觉率</th><th>P95</th><th>Token</th><th>成本(μUSD)</th></tr></thead>
            <tbody>
              <tr v-for="item in evaluations" :key="item.id">
                <td>{{ item.dataset_version }}</td><td>{{ item.workflow }}</td>
                <td>{{ (item.task_completion_rate * 100).toFixed(0) }}%</td>
                <td>{{ (item.numeric_accuracy * 100).toFixed(0) }}%</td>
                <td>{{ (item.evidence_coverage * 100).toFixed(0) }}%</td>
                <td>{{ (item.hallucination_rate * 100).toFixed(0) }}%</td>
                <td>{{ item.p95_latency_ms }} ms</td><td>{{ item.total_tokens }}</td>
                <td>{{ item.estimated_cost_microusd }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="!evaluations.length" class="empty">尚未运行版本化评测。</p>
      </section>

      <section class="panel">
        <h2>失败样本库</h2>
        <div class="failure-list">
          <article v-for="item in failures" :key="item.id">
            <strong>{{ item.case_id }}</strong><span>{{ item.workflow }} / {{ item.error_stage }}</span>
            <code>{{ item.error_code || 'NO_ERROR_CODE' }}</code>
          </article>
        </div>
        <p v-if="!failures.length" class="empty">当前评测没有失败样本。</p>
      </section>
    </template>
  </main>
</template>

<style scoped>
.developer-page { max-width: 1200px; margin: 0 auto; padding: 44px 24px 80px; }
header { margin-bottom: 28px; } h1 { margin: 6px 0 10px; font-size: clamp(32px, 5vw, 56px); }
.eyebrow { color: #2563eb; font-size: 12px; font-weight: 800; letter-spacing: .16em; }
.panel { background: #fff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; margin-top: 20px; box-shadow: 0 12px 32px rgba(15,23,42,.05); }
.run-layout { display: grid; grid-template-columns: 280px 1fr; gap: 24px; }
.run-row { width: 100%; display: grid; grid-template-columns: 1fr auto; gap: 4px 10px; text-align: left; padding: 12px; margin: 8px 0; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; cursor: pointer; }
.run-row small { grid-column: 1 / -1; color: #64748b; }.run-row.active { border-color: #2563eb; background: #eff6ff; }
.trace-heading { display: flex; justify-content: space-between; gap: 20px; }.status { color: #166534; font-weight: 700; }
.graph { display: flex; align-items: stretch; gap: 10px; overflow-x: auto; margin: 20px 0 26px; }
.node { min-width: 130px; display: grid; gap: 5px; padding: 14px; border-radius: 12px; color: #e2e8f0; background: #0f172a; }
.node span,.node small { color: #94a3b8; }.node em,.tool-card em { color: #ef4444; font-style: normal; }.arrow { align-self: center; color: #94a3b8; }
.tool-grid,.failure-list { display: grid; grid-template-columns: repeat(auto-fit,minmax(210px,1fr)); gap: 10px; }
.tool-card,.plan-card,.failure-list article { display: grid; gap: 7px; padding: 13px; border: 1px solid #e2e8f0; border-radius: 12px; }
.comparison-card { display: grid; gap: 8px; }.comparison-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(190px,1fr)); gap: 10px; }.comparison-grid div { display: grid; gap: 5px; padding: 12px; border-radius: 12px; background: #f8fafc; }
code { overflow-wrap: anywhere; color: #475569; }.plan-card { margin-top: 10px; }.plan-card li { margin: 6px 0; }.plan-card small { color: #64748b; margin-left: 8px; }
.table-wrap { overflow-x: auto; } table { width: 100%; border-collapse: collapse; font-size: 13px; } th,td { padding: 10px; text-align: left; border-bottom: 1px solid #e2e8f0; white-space: nowrap; }
.empty,.notice { color: #64748b; }.error { color: #b91c1c; }
@media (max-width: 760px) { .run-layout { grid-template-columns: 1fr; } }
</style>
