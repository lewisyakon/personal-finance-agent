# 阶段 6 语义分类合同

阶段 6 只处理规则和历史均无法可靠判定的交易。分类优先级固定为：用户确认规则、账单平台明确分类、
同商户一致历史、Semantic Agent。前三级命中后不会调用模型。

## 商户归一化与规则

- 商户名经过 Unicode NFKC、大小写归一、支付渠道前缀和分隔符清理；原始商户名仍保留在交易表。
- `merchant_rules` 以 `(owner_id, normalized_merchant)` 唯一，规则只能在所属 Owner 内生效。
- 用户确认建议或人工修改交易分类时可写入 `user_confirmed` 规则。用户规则优先于模型结果。
- 模型高置信度结果只应用到当前交易，不自动沉淀为长期规则。

## Semantic Agent 输入与输出

模型输入只包含截断后的商户/描述、候选分类和有界历史摘要，不包含 Owner、完整账单、SQL、路径或
URL。输出必须满足 `SemanticDecision` JSON Schema：

```json
{
  "category": "餐饮",
  "confidence": 0.72,
  "rationale": "商户语义更接近餐饮"
}
```

`category` 必须原样来自服务端候选集合。默认 `confidence >= 0.85` 才自动应用；低于阈值时写入
`pending` 建议，等待用户确认或拒绝。阈值由 `SEMANTIC_AUTO_APPLY_THRESHOLD` 配置。

## Evidence 与状态

- 用户规则：`merchant_rule:{rule_id}`。
- 平台分类：`transaction:{transaction_id}:platform_category`。
- 历史和模型路径：复用阶段 4 `get_merchant_history` 生成的 `ev_*` 快照。
- 建议状态为 `pending | applied | confirmed | rejected`；重复分类请求会复用尚有效的建议，避免重复模型调用。
- 分类变更继续写入 `transaction_category_changes`，金额和时间字段不由 Semantic Agent 修改。

迁移 `20260921_0004` 新增 `merchant_rules` 和 `classification_suggestions`。
