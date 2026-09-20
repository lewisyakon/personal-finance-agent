# 阶段 4 受控 Tool 数据契约

阶段 4 提供模型不可直接控制 Owner、SQL、文件路径或 URL 的第一批只读 Tool。Tool 由后端
进程内部调用，阶段 4 不新增公开 HTTP 接口，也不接入模型；ModelProvider 和 Single-Agent
属于阶段 5。

## 运行边界

- 调用方必须通过可信运行时传入 `OwnerContext`；任何 Tool 参数 Schema 都不包含
  `owner_id`。参数中额外传入 `owner_id` 会得到 `INVALID_ARGUMENTS`。
- 时间周期必须显式传入带时区的 `from` 和 `to`，并统一使用左闭右开区间
  `[from, to)`。默认业务时区仍是 `Asia/Shanghai`。
- 金额全部使用整数最小货币单位，不接受浮点金额。
- 统计 Tool 直接复用阶段 3 `Stats Service`，退款、转账、失败交易、多币种和固定/可变
  支出口径不另行实现。
- 列表 Tool 强制分页或数量上限：交易搜索和商户历史每页最多 50 条，排行和大额交易
  最多 100 条。
- 默认执行超时由 `TOOL_TIMEOUT_SECONDS` 控制，序列化结果大小由
  `TOOL_MAX_RESULT_BYTES` 控制。超时或过大结果会被丢弃，并返回可追踪的结构化错误。

## 第一批只读 Tool

| Tool | 关键参数 | 权威数据源 |
| --- | --- | --- |
| `get_spending_summary` | `from`、`to`、可选 `budget_minor` | Stats Service |
| `get_category_breakdown` | `from`、`to`、`direction` | Stats Service |
| `get_trend` | `from`、`to`、`granularity` | Stats Service |
| `get_top_merchants` | `from`、`to`、`direction`、`limit` | Stats Service |
| `get_large_transactions` | `from`、`to`、`direction`、`threshold_minor`、`limit` | Stats Service |
| `search_transactions` | 周期、受控筛选、`page`、`page_size` | Transaction Service |
| `compare_periods` | 当前周期和显式比较周期 | Stats Service |
| `get_budget_status` | `from`、`to`、`budget_minor` | Stats Service |
| `get_merchant_history` | `from`、`to`、`merchant`、分页 | Transaction Service |

`search_transactions` 只允许日期、方向、状态、分类、商户、文本、金额区间和分页条件，
不接受 SQL。返回的交易只含分析需要的有限字段，描述截断到 160 个字符，不返回指纹、
导入 ID、平台交易号或完整账单行。

`get_merchant_history` 对去除首尾空格后的商户名做精确匹配，金额按币种分别汇总，
同时返回分类分布、人工修正后的类别及次数和有限分页记录，不跨币种相加。

## 统一结果

每次调用返回：

- `evidence_id`、`tool_name` 和 `contract_version`；
- `status=success|error`；
- 成功时的结构化 `data` 和 `methodology`；
- 失败时的 `error.code`、安全错误消息和可选字段级详情；
- 开始/结束时间与 `duration_ms`。

`methodology` 明确权威 Service、`[from, to)` 周期语义、业务时区、金额单位和相关口径。
模型只能解释这些结果，不能自行重新计算权威金额。

## Trace 与 evidence_id

每次调用（包括参数错误、未知 Tool、业务校验失败和超时）都会在 `tool_traces` 表中记录
Owner、Tool 名、版本、状态、耗时和经过最小化的请求/响应快照。Trace 不记录 API Key、
文件路径、账单原始行或模型上下文；Owner 单独来自运行上下文，不混入参数 JSON。

请求和响应快照分别保存 SHA-256 摘要。`ToolExecutor.replay(evidence_id, context)` 只有在
Owner 匹配且响应摘要校验通过时才返回原始快照；它不会使用当前数据库重新计算。因此，
即使交易随后被修改，旧 `evidence_id` 仍指向当时的证据结果。跨 Owner 查询表现为不存在，
避免泄露其他工作区是否持有该证据。

## 结构化错误

| 错误代码 | 含义 |
| --- | --- |
| `UNKNOWN_TOOL` | Tool 未注册 |
| `INVALID_ARGUMENTS` | 参数不符合 Pydantic Schema，包括额外字段 |
| `TOOL_VALIDATION_ERROR` | 参数通过 Schema，但确定性 Service 拒绝该业务组合 |
| `TOOL_TIMEOUT` | 超过受控执行时间 |
| `TOOL_RESULT_TOO_LARGE` | 结果超过配置上限，应缩短周期或收紧筛选 |
| `TOOL_EXECUTION_ERROR` | 其他执行失败；不回传数据库、路径或异常细节 |

错误也具有 `evidence_id` 并写入 Trace，便于后续 Agent 运行审计。
