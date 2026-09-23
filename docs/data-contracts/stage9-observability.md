# 阶段 9：可观测性与评测合同

## Developer Console

开发视图关联展示 Run、节点步骤、模型调用、Tool Evidence、计划版本、记忆命中以及错误码。Trace
只包含摘要、计数、状态、延迟和稳定引用，不返回完整 prompt、reasoning、Tool 原始参数/结果、
账单行或 API Key。

Developer API 只在 `DEVELOPER_ENABLED=true` 且 `APP_MODE` 为 `local`、`development` 或 `test`
时开放；其他环境统一返回 404。

## 架构对比

固定 `stage5-v1` 30 题数据集可对比：

- `single`：Single-Agent；
- `multi_unverified`：Multi-Agent，不启用 Verifier；
- `multi`：Multi-Agent + Verifier。

每组对比共享 `comparison_group_id`，持久化准确率、任务完成率、Evidence 覆盖率、幻觉率、路由
准确率、平均 Handoff、P50/P95 延迟、Token 和估算费用。失败样本按数据集版本、题目、工作流、
失败阶段和错误码保存最小摘要。只有量化指标显示收益时才应保留额外 Agent/Verifier。

当前验收按用户要求只运行确定性 mock；真实 Ollama 和远程模型应在模型/API Key 可用后用同一
版本数据集补充基线，不得把 mock 指标宣称为真实模型质量。

