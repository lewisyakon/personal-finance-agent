# 阶段 10：记忆 API

- `GET /api/v1/memories?scope=session|long_term|knowledge`：列出有效记忆。
- `POST /api/v1/memories`：显式确认并创建记忆。
- `PATCH /api/v1/memories/{memory_id}`：创建带来源链的新版本。
- `DELETE /api/v1/memories/{memory_id}`：软删除并从后续检索排除。
- `GET /api/v1/memories/accesses`：查看最近 200 条命中/未命中 Trace。

创建示例：

```json
{
  "scope": "knowledge",
  "kind": "preference",
  "key": "报告语言",
  "value": {"language": "zh-CN"}
}
```

可选 `expires_at` 必须带时区。更新至少包含 `value` 或 `expires_at`；修改不会覆盖旧记录，而是返回
新 ID、新版本号和 `supersedes_id`。前端 `/memories` 支持用户查看、创建、修改和删除。

