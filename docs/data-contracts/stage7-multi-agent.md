# 阶段 7 Multi-Agent 合同

复杂查询使用固定、无回边的 LangGraph：

`START -> Supervisor -> Analysis -> Verifier -> END`

简单查询仍走阶段 5 Single-Agent 快路径。显式 `workflow=single|multi` 可用于复现和对比；
`workflow=auto` 仅对包含分析、原因、异常、比较、趋势、建议等复杂意图的请求选择 Multi-Agent。

## Registry、共享状态与 Handoff

Agent Registry 固定注册三个角色，并限制其可写命名空间：

| Agent | 职责 | 核心可写状态 |
| --- | --- | --- |
| Supervisor | 规范化意图、时间/方向约束和只读 Tool 计划 | `normalized_intent`、`constraints`、`plan`、`supervisor_handoff` |
| Analysis | 执行阶段 4 Tool 并形成带证据的回答 | `task_results`、`statistics`、`findings`、`evidence_refs`、`analysis_handoff` |
| Verifier | 校验计划、金额、时间、方向和 Evidence | `verification` |

共享状态还包含 `classification_candidates`、`budget_draft`、`errors`、步数/Tool/模型调用计数和
Token 使用量。跨命名空间更新会被拒绝。

Supervisor 和 Analysis 之间使用严格 JSON Schema Handoff。计划只能选择 Registry 中的只读
Tool；Owner、SQL、路径、URL 和完整推理不得进入 Handoff 或 Trace。

## Verifier 与终止条件

Verifier 是确定性代码，不再调用模型。以下任一条件失败都返回 `VERIFICATION_FAILED` 和
“无法确定”，不会放行未经验证的答案：

- Analysis 未成功或缺少 Evidence；
- 答案中的金额、笔数或比例无法由 Tool 结果支持；
- 未执行 Supervisor 要求的 Tool；
- Evidence 时间范围与 Handoff 不一致；
- Evidence 中明确的收支方向与 Handoff 不一致。

图没有循环边，另有 LangGraph recursion limit，以及阶段 5 的总步数、模型调用、Tool 调用、
Token 和总时间限制，因此成功和失败路径都会有界终止。

## Trace 与对比

`agent_step_traces` 为每个节点记录序号、状态、最小输入/输出摘要、耗时和错误码，不保存原始查询、
完整上下文或 reasoning。`agent_runs.workflow` 和 `agent_evaluation_runs.workflow` 标识执行模式。

单请求可通过 `/api/v1/agent/compare` 对比；固定 30 题数据集可运行：

```bash
cd backend
python -m app.evals.runner --workflow compare --fixture ../datasets/sanitized_samples/stage3_stats_fixture.csv
```

报告分别持久化 Single/Multi 的通过率、Tool 选择、数值准确率、平均延迟和 Token，并给出差值。
迁移 `20260922_0005` 新增工作流字段和节点 Trace 表。
