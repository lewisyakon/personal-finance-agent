# 阶段 2 导入与交易 API

所有接口前缀为 `/api/v1`。本地 MVP 使用 `LOCAL_OWNER_ID` 作为工作区 owner；客户端不能通过请求体、查询参数或模型上下文覆盖 owner。

## 导入

`POST /imports` 使用 multipart 字段 `file` 上传微信 CSV 或 XLSX。`source` 默认为 `wechat`；`format` 可省略，服务会根据文件扩展名自动识别，也可以显式传 `format=csv` 或 `format=xlsx`。显式格式必须和文件扩展名一致。接口在本地进程内执行器中同步解析并返回导入报告：

```json
{
  "id": "uuid",
  "status": "completed",
  "total_rows": 3,
  "success_rows": 3,
  "duplicate_rows": 0,
  "skipped_rows": 0,
  "failed_rows": 0,
  "pending_confirmation_rows": 0,
  "file_sha256": "sha256",
  "raw_file_available": true,
  "idempotent_reuse": false
}
```

状态包括 `pending`、`processing`、`completed`、`partial`、`failed` 和 `cancelled`。解析行错误只返回行号和短错误摘要，不保存完整原始行。重复提交相同文件时，按 owner + SHA-256 复用既有 `BillImport`；响应中的 `idempotent_reuse` 为 `true`。

- `GET /imports?page=1&page_size=20`：分页列表。
- `GET /imports/{id}`：任务详情。
- `POST /imports/{id}/retry`：重试 `pending`、`processing`、`partial` 或 `failed` 任务；服务会按任务文件名纠正旧版本记录中的格式，唯一指纹保证中断后重试不重复入账。
- `DELETE /imports/{id}`：删除任务、关联交易和仍存在的原始文件。

## 交易

- `GET /transactions`：分页查询。支持 `from`、`to`（ISO-8601；日期值的结束日包含在内）、`direction`、`status`、`category`、`merchant`、`search`、`min_amount` 和 `max_amount`（均为最小货币单位）。
- `GET /transactions/{id}`：交易详情。
- `PATCH /transactions/{id}/category`：请求体 `{ "category": "餐饮" }`；传 `null` 或空字符串可清除分类。兼容 `PATCH /transactions/{id}` 和 `{ "category_name": "餐饮" }`。

分类修改响应同时包含 `previous_category`、`new_category` 和 `source=user`，并写入 `transaction_category_changes` 审计表。

金额字段始终为整数最小货币单位；SQLite 文件物理存储 UTC-naive 时间（SQLite 限制），SQLAlchemy 和 API 会恢复并返回带 `+00:00` 偏移的 ISO 时间。原始文件受 `RAW_FILE_TTL_MINUTES` 控制，事实表不随原始文件清理而删除。
