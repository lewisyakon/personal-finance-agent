# 阶段 5 Agent API

所有端点位于 `/api/v1/agent`。本地 MVP 的 Owner 来自服务端 `LOCAL_OWNER_ID`，请求体不能
指定或切换 Owner。聊天接口当前为同步调用；HTTP 返回时本次运行已经进入终态。

## 发起查账

`POST /api/v1/agent/chat`

```json
{
  "message": "2026年1月总支出是多少？",
  "session_id": null
}
```

`session_id` 省略或为 `null` 时创建会话；继续会话时传已有 UUID。成功和可解释的 Agent
失败都返回 `200` 的 `AgentRunResponse`，调用方应读取 `status`、`error_code` 和
`error_message`：

```json
{
  "id": "run-uuid",
  "session_id": "session-uuid",
  "status": "succeeded",
  "user_query": "2026年1月总支出是多少？",
  "answer": "本期支出为82.00元。\n\n证据：ev_...",
  "error_code": null,
  "error_message": null,
  "provider": "local",
  "model": "qwen-model",
  "evidence_refs": ["ev_..."],
  "tool_names": ["get_spending_summary"],
  "metrics": {
    "step_count": 3,
    "tool_call_count": 1,
    "model_call_count": 2,
    "prompt_tokens": 100,
    "completion_tokens": 30,
    "total_tokens": 130,
    "duration_ms": 800
  },
  "cancellation_requested": false,
  "started_at": "2026-09-20T10:00:00Z",
  "completed_at": "2026-09-20T10:00:01Z",
  "model_calls": []
}
```

`model_calls` 只含元数据，不含 prompt、上下文或 reasoning。

## 查询与取消

- `GET /api/v1/agent/sessions?page=1&page_size=20`：Owner 范围内的会话列表。
- `GET /api/v1/agent/sessions/{session_id}`：会话及其运行历史。
- `GET /api/v1/agent/runs/{run_id}`：单次运行和模型调用元数据。
- `POST /api/v1/agent/runs/{run_id}/cancel`：请求协作式取消；终态运行保持原状态。

不存在或不属于当前 Owner 的会话/运行统一返回 `404`，不会泄露另一 Owner 是否拥有该 ID。

## 错误

HTTP 层错误保持 `{ "detail": { "code": "...", "message": "..." } }`：

- `MODEL_CONFIG_ERROR`：Provider 模式、地址或 Key 配置错误，HTTP `503`。
- `AGENT_SESSION_NOT_FOUND`、`AGENT_RUN_NOT_FOUND`：资源不存在，HTTP `404`。
- `INVALID_REQUEST`：消息为空、过长或字段不合法，HTTP `400`。

运行层错误出现在 `AgentRunResponse` 中，包括 `MODEL_TIMEOUT`、`MODEL_UNAVAILABLE`、
`AGENT_*_LIMIT`、`EVIDENCE_REQUIRED`、`UNGROUNDED_NUMERIC_CLAIM`、`MODEL_CANCELLED` 等。
模型服务不可用时不会切换 Provider。
