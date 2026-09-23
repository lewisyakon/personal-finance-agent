# 阶段 7 Multi-Agent API

阶段 7 扩展 `/api/v1/agent`，原会话和 Run 查询端点保持兼容。

## 选择工作流

`POST /chat` 请求新增 `workflow`：

```json
{
  "message": "分析2026年1月每天的支出趋势",
  "session_id": null,
  "workflow": "auto"
}
```

- `auto`：简单查询使用 Single-Agent，复杂分析使用 Multi-Agent。
- `single`：强制阶段 5 快路径。
- `multi`：强制固定 Supervisor -> Analysis -> Verifier 图。

响应新增 `workflow` 和 `agent_steps`。`agent_steps` 只暴露节点、状态、最小化摘要、耗时和错误码。

## 对比

`POST /compare`

```json
{
  "message": "对比2026年1月与前一周期的支出"
}
```

接口对同一问题依次强制运行 Single 和 Multi，返回两个完整 `AgentRunResponse`，以及
`same_status`、`same_tools`、等价 Evidence 数量、延迟差和 Token 差。两次运行均单独留痕。

Multi-Agent 验证失败仍返回 HTTP `200`，但 Run 的 `status=failed`、
`error_code=VERIFICATION_FAILED`。请求字段或工作流模式非法返回 `400`。
