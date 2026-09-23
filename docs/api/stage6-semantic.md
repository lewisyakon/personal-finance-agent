# 阶段 6 Semantic API

所有端点位于 `/api/v1/semantic`，Owner 由服务端上下文注入。

## 分类与建议

- `POST /transactions/{transaction_id}/classify`：按规则、平台分类、历史、模型的固定优先级分类。
- `GET /suggestions?status=pending&page=1&page_size=20`：分页查询建议。
- `POST /suggestions/{suggestion_id}/confirm`：确认建议，可修正类别并保存商户规则。
- `POST /suggestions/{suggestion_id}/reject`：拒绝建议。

确认请求：

```json
{
  "category": "餐饮/咖啡",
  "save_rule": true
}
```

分类响应包含 `route`、`status`、`confidence`、`evidence_refs`、`model_called` 及最小化的
`rationale_summary`。`route` 为 `user_rule | platform | history | model`。

## 规则管理

- `GET /rules`：查询当前 Owner 的商户规则。
- `DELETE /rules/{rule_id}`：删除规则，成功返回 `204`。

资源不存在或不属于当前 Owner 时返回 `404`。业务错误格式统一为
`{"detail":{"code":"...","message":"..."}}`；Provider 不可用返回 `503`，不会静默降级。
