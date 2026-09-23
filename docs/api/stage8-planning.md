# 阶段 8：Planner 与预算 API

## Agent

`POST /api/v1/agent/chat` 新增 `workflow=planner`。自动路由会把预算、规划、并行分析、重新规划或
结果分歧类问题交给 Planner。响应可为 `succeeded`、`failed` 或 `needs_confirmation`，并返回
任务节点 Trace、Evidence、调用计数、延迟、Token 和估算费用。

## 预算

- `GET /api/v1/budgets`：列出预算草案和历史版本。
- `POST /api/v1/budgets/drafts`：从统计 Evidence 创建预算草案。
- `GET /api/v1/budgets/{budget_id}`：读取预算详情。
- `PATCH /api/v1/budgets/{budget_id}`：修改草案或已确认预算的整数金额。

创建草案请求示例：

```json
{
  "from": "2026-01-01T00:00:00+08:00",
  "to": "2026-02-01T00:00:00+08:00",
  "reduction_percent": 10
}
```

## 确认

- `GET /api/v1/agent/confirmations`：列出预算和分歧确认请求。
- `POST /api/v1/agent/confirmations/{id}/resolve`：提交 `confirm` 或 `reject`。

Owner 由服务端注入；请求中的时间必须带时区。不存在的确认/预算返回结构化 404；Evidence 不可用、
比例越界或不可编辑状态返回结构化 400。

