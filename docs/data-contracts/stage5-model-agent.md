# 阶段 5 ModelProvider 与 Single-Agent 契约

## Provider

`ModelProvider` 对上层暴露统一的 `health()` 和 `complete()`，请求支持普通消息、函数 Tool
Schema 和 JSON Schema 结构化输出，响应统一包含 Provider、模型、延迟、尝试次数和 Token
用量。实现不读取或保存供应商返回的 reasoning 字段。

| `LLM_PROVIDER` | 用途 | 地址约束 | Key |
| --- | --- | --- | --- |
| `mock` | 无模型开发与确定性测试 | 不访问网络 | 不需要 |
| `local` | Ollama 等 OpenAI-compatible 本地服务 | 只允许 `localhost`、`127.0.0.1`、`::1` | 可不配置 |
| `remote` | 远程 OpenAI-compatible 服务 | 非回环地址必须使用 HTTPS | 必须配置 |

`LLM_BASE_URL` 应包含兼容 API 的版本前缀，例如 `http://127.0.0.1:11434/v1`。Provider
调用 `GET {base_url}/models` 做健康检查，调用 `POST {base_url}/chat/completions` 完成推理。
远程、本地或配置错误都会返回显式错误，绝不自动切换到 mock 或另一 Provider。

超时和网络错误，以及 HTTP `408`、`409`、`429`、`5xx`，最多按
`LLM_MAX_RETRIES` 有界重试；其他 `4xx` 不重试。取消令牌会在请求前、重试等待中和响应后
检查。同步 HTTP 请求本身不能被强制中断，因此最坏取消延迟受 `LLM_TIMEOUT_SECONDS` 限制。

Tool 调用遵循 OpenAI-compatible function calling 结构，发送
`parallel_tool_calls=false`，Single-Agent 每轮也只接受一个 Tool 调用。Tool 参数仍由服务端
Pydantic 合同重新校验，不能把模型输出当作可信输入。接口形状参考
[OpenAI Chat API](https://developers.openai.com/api/reference/cli/resources/chat) 和
[Function calling 指南](https://developers.openai.com/zh-Hans/api/docs/guides/function-calling)。

## Single-Agent

阶段 5 只有一个有界 LangGraph：

```text
START -> model -> (一个 Tool -> model)* -> 有证据的最终回答 -> END
```

- 模型只能看到阶段 4 的 9 个只读 Tool Schema；`owner_id` 始终由服务端注入。
- Tool 名称和参数必须通过 Registry/Pydantic 校验；不能传 SQL、文件路径、URL 或写操作。
- 涉及交易、金额、数量、比例或趋势的答案必须至少有一个成功 Tool evidence。
- 最终答案中带“元、分、%、笔”的关键数值会与本次 Tool 结果做确定性核验；不匹配时运行以
  `UNGROUNDED_NUMERIC_CLAIM` 失败，不把幻觉数值返回给用户。
- 最终成功回答附带 `evidence_id`，可以按 Owner 重放调用时的不可变快照。
- `AGENT_MAX_STEPS`、Tool/模型调用次数、总运行时间和总 Token 都有独立上限。
- Provider、Tool 或证据不足时返回“无法确定”和稳定错误码，不让模型补算或猜测。

## 持久化与隐私

- `agent_sessions`：Owner 范围内的会话标题与时间。
- `agent_runs`：问题、最终回答、状态、Evidence、使用的 Tool、延迟和 Token 聚合。
- `model_call_traces`：只保存 Provider/模型、延迟、Token、选中的 Tool 和错误码。
- `tool_traces.run_id`：把阶段 4 Evidence 关联到 Agent Run。
- `agent_evaluation_runs`：30 题评测的聚合指标与逐题最小结果。

不会在模型 Trace 中持久化完整 prompt、Tool 上下文、隐藏 reasoning、API Key 或完整账单行。
用户问题和最终回答会保存在会话历史；它们属于 Owner 隔离的数据。

## 30 题评测基线

固定数据集位于
[`backend/evals/stage5_questions.json`](../../backend/evals/stage5_questions.json)，只能配合
脱敏的 `stage3_stats_fixture.csv` 使用。数据集覆盖全部 9 个 Tool，预设通过率门槛为 80%。

评测不相信模型自报数值，而是重放每个 `evidence_id`，从 Tool 快照核验期望金额、数量和
比例；同时记录 Tool 选择准确率、数值准确率、平均延迟、总 Token 和逐题错误码。默认 mock
基线用于验证编排和证据链；切换 local/remote 后应在同一数据集上另跑模型质量基线。

建议使用隔离数据库，并通过显式 `--fixture` 导入仓库内的合成数据：

```bash
cd backend
EVAL_DIR="$(mktemp -d)"
DATABASE_URL="sqlite:///$EVAL_DIR/stage5.db" DATA_DIR="$EVAL_DIR" \
  python -m app.evals.runner \
  --owner-id stage5-eval-owner \
  --fixture ../datasets/sanitized_samples/stage3_stats_fixture.csv
```

命令退出码为 `0` 表示达到门槛，`1` 表示未达到；无论结果如何都会写入
`agent_evaluation_runs`。若不传 `--fixture`，评测只读取当前数据库中该 Owner 已有的数据。
