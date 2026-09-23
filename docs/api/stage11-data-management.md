# 阶段 11 本地数据管理 API

基址：`/api/v1/data`。全部端点只在 `APP_MODE=local|development|test` 时存在；其他模式返回 404。
所有动作都作用于服务端 OwnerContext，客户端不能传 `owner_id`。

## 状态与备份列表

- `GET /status`：固定数据目录、SQLite 大小、原始文件/备份数、原始文件 TTL 和升级策略。
- `GET /backups`：最多返回 200 个通过 manifest 路径校验的备份，按创建时间倒序。

## 二次确认协议

先调用 `POST /confirmations`，同时发送 Header：

```http
X-PFA-Local-Action: confirm
Content-Type: application/json
```

请求中的精确短语如下：

| action | confirmation_text | target_id |
|---|---|---|
| `export` | `导出我的数据` | 禁止 |
| `backup` | `创建本地备份` | 禁止 |
| `restore` | `恢复本地备份` | 必须为备份 ID |
| `delete_all` | `删除全部数据` | 禁止 |

响应的 `confirmation_token` 默认 5 分钟过期，与 Owner/action/target 绑定且仅可使用一次。实际动作
请求也必须携带相同 Header，请求体为 `{"confirmation_token":"..."}`。

## 动作

- `POST /exports`：返回 `application/zip`，设置 `Cache-Control: no-store`；不包含原始账单文件。
- `POST /backups`：创建经过完整性检查的手工 SQLite 备份，返回 `201`。
- `POST /backups/{backup_id}/restore`：返回被恢复备份和覆盖前自动创建的安全备份。
- `POST /delete-all`：返回删除的行、原始文件、日志文件和备份文件数。

常见错误码包括 `CONFIRMATION_TEXT_MISMATCH`、`CONFIRMATION_INVALID`、
`CONFIRMATION_SCOPE_MISMATCH`、`BACKUP_NOT_FOUND`、`BACKUP_DIGEST_MISMATCH`、
`BACKUP_SCHEMA_INCOMPATIBLE`、`EXPORT_TOO_LARGE` 和 `LOCAL_ACTION_HEADER_REQUIRED`。
