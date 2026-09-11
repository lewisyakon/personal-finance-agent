# 阶段 3 统计 API

所有接口前缀为 `/api/v1/stats`。金额字段均为整数最小货币单位（人民币分），
统计结果由后端确定性 `Stats Service` 生成。

## 统计周期参数

各接口都支持：

- `from`：ISO-8601 开始时间，包含。
- `to`：ISO-8601 结束时间；只写 `YYYY-MM-DD` 时包含整天，带时间时为排他上界。
- 不传边界时使用当前月份；只传一边时按 30 天补齐。

## 接口

| 方法和路径 | 作用 |
| --- | --- |
| `GET /summary` | 支出、收入、退款、转账、净流量、交易数和固定/可变支出汇总 |
| `GET /categories` | 一级/二级分类构成；`direction=expense|income` |
| `GET /trend` | 日、周、月或年趋势；`granularity=day|week|month|year` |
| `GET /merchants` | 商户金额排行；支持 `direction` 和 `limit` |
| `GET /large-transactions` | 大额交易；默认支出，支持 `threshold_minor`、`limit` 和 `direction` |
| `GET /fixed-variable` | 固定支出和可变支出 |
| `GET /budget` | 预算已用、剩余和超支；必须传 `budget_minor` |
| `GET /comparison` | 环比或同比；`mode=previous|yoy`，可显式传 `compare_from`、`compare_to` |

示例：

```bash
curl 'http://127.0.0.1:8000/api/v1/stats/summary?from=2026-01-01&to=2026-01-31'
curl 'http://127.0.0.1:8000/api/v1/stats/trend?from=2026-01-01&to=2026-02-01&granularity=day'
curl 'http://127.0.0.1:8000/api/v1/stats/categories?from=2026-01-01&to=2026-02-01&direction=expense'
curl 'http://127.0.0.1:8000/api/v1/stats/budget?from=2026-01-01&to=2026-02-01&budget_minor=500000'
```

大额交易、排行和趋势中的列表数量由服务端限制，避免把大量交易行放入页面或未来
Agent 的上下文。页面下钻时应跳转到阶段 2 的 `/api/v1/transactions`，而不是在前端
重新计算统计。

非法日期、周期、方向、粒度、比较模式、预算、阈值和列表数量会返回 HTTP 400，
`detail.code` 用于前端区分错误类型；统计服务本身的校验错误统一使用
`STATS_VALIDATION_ERROR`。
