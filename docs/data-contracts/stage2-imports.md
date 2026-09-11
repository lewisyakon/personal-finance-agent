# 阶段 2 数据契约

## BillImport

`BillImport` 表记录一次用户上传及其确定性处理结果。`owner_id + file_sha256` 唯一，保证同一工作区重复上传幂等。`raw_path` 只用于短生命周期解析，TTL 到期后置空；数据库不保存原始文件内容。

## Transaction

`Transaction` 保存标准化消费事实：

- `amount_minor` 是整数（例如人民币 12.50 元保存为 `1250`）。
- `occurred_at` 由 Parser 解析为带 `Asia/Shanghai` 时区的时间，入库转换为 UTC；SQLite 物理值不带 offset，但 ORM 读取时恢复为带 UTC offset 的时间。
- `direction`、`status` 使用 Parser 的固定枚举值。
- 微信导出的终态变体会统一映射：`已存入零钱`、`对方已收钱`、`已转账` 和 `已收钱`
  映射为 `success`；`已全额退款`、`已退款¥金额` 和 `已退款(¥金额)` 等已完成退款
  映射为 `refunded`。同一文件的 SHA-256 幂等复用不会触发重新解析；若 Parser 规则升级，
  需要删除旧导入后再上传原文件。
- `platform_category` 保留平台原始分类，`category` 和 `category_source` 供后续确定性规则、Semantic Agent 和用户确认使用。
- `owner_id + fingerprint` 唯一。fingerprint 使用配置的 `FINGERPRINT_SECRET` 做 HMAC-SHA256：优先使用平台稳定交易号；缺少交易号时使用时间、金额、方向、规范商户和描述摘要。

## TransactionCategoryChange

每次人工修改分类写入旧分类、新分类、owner、时间和 `source=user`。修改交易必须先按 owner 查询，不能通过客户端指定其他 owner。

## 删除与恢复语义

删除 `BillImport` 会级联删除该导入产生的交易和分类审计记录；这是用户主动删除导入数据的操作。原始文件 TTL 清理只删除文件并将 `raw_path` 置空，不删除标准化交易事实。
