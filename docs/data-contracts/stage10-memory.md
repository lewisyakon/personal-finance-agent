# 阶段 10：用户可控记忆合同

## 类型与来源

记忆明确区分：

- `session`：会话状态，Value 必须包含 `session_id`，默认 24 小时过期，并仅在同一会话匹配；
- `long_term`：用户确认的长期偏好，如预算偏好或商户规则；
- `knowledge`：用户显式录入的知识。

唯一允许的来源是 `user_confirmed`。模型分类、推测、低置信度建议或未确认预算不得自动写入
长期记忆。已确认预算和用户选择“保存规则”的商户分类可携带 `source_ref_type/id` 写入。

## 冲突、版本和生命周期

同一 Owner、scope、kind、key 的新值创建新版本，旧版本标记 `superseded` 并由
`supersedes_id` 串联。会话或显式到期记忆标记为 `expired`；用户删除为软删除 `deleted`。
检索只能使用 `active` 且未过期记录。删除商户规则记忆还会停用对应规则，确保后续分类和 Planner
均不再使用它；从规则管理接口删除商户规则也会同步删除对应记忆。已确认预算被用户修改时，
对应预算偏好生成新记忆版本，避免预算记录与 Planner 上下文不一致。

单条 JSON Value 最大 8 KiB。Owner 由服务端注入；所有列表、修改、删除和检索都按 Owner
隔离。

## 可解释检索

每次 Planner 检索写入 `memory_access_traces`，记录 `hit`/`miss`、匹配记忆 ID 和原因。查询本身
只保存 SHA-256 指纹，不保存原文。Developer Console 可查看命中/未命中原因，模型上下文最多
注入 20 条有效且用户确认的记忆。
