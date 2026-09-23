# 阶段 8：Planner 与 Budget Agent 合同

## 任务图

Planner 只能输出结构化 `TaskGraph`，包含最多 8 个 `PlanTask`。每个任务必须声明稳定的
`task_id`、Agent、目标、只读 Tool、严格参数和显式依赖。运行前必须拒绝：

- 未注册 Agent 或 Tool；
- Agent 无权使用的 Tool；
- Tool 参数 Schema 不合法或越权参数；
- 未知依赖、自依赖和循环依赖。

校验器把图转换为拓扑执行波次。同一波中无依赖任务可并行，后继任务必须等依赖波完成；任一
Tool 失败后不再执行后续波。计划、校验错误和重规划原因写入 `agent_plan_traces`，不保存完整
prompt 或 reasoning。

## 重规划与边界

只有计划显式允许且首轮 Evidence 已返回时才可重规划，默认最多一次。重规划仍经过同一校验器，
且共享单次 Run 的步数、模型调用、Tool 调用、Token、费用估算和总时长上限。超过任何上限均
显式失败，不静默绕过。

## Budget Agent

预算基线只来自 `get_spending_summary` 的确定性 Evidence。金额使用整数最小货币单位：

`proposed_budget_minor = baseline_expense_minor * (10000 - reduction_bp) // 10000`

预算先以 `draft` 保存并创建 `budget` 类型确认请求。只有用户选择 `confirm` 后才成为
`confirmed`；同周期旧预算会标记为 `superseded`。拒绝后为 `rejected`。模型不能直接确认预算。

## 分歧处理

任务结果的周期或币种不一致时，Run 返回 `needs_confirmation` 并创建 `disagreement` 确认请求，
不得自动选择其中一个结果。确认记录均按 Owner 隔离。

