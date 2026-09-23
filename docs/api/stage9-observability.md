# 阶段 9：Developer API

以下接口均以 `/api/v1/developer` 为前缀，并受本地开发开关保护：

- `GET /runs?page=1&page_size=20`：Run 摘要、计数、延迟、费用和错误码。
- `GET /runs/{run_id}`：节点、模型、Tool Evidence、计划版本和记忆访问详情。
- `GET /eval-runs`：版本化评测记录与完整指标。
- `GET /comparisons`：按 `comparison_group_id` 聚合架构对比。
- `GET /failures`：版本化失败样本库。

前端 `/developer` 提供对应图形化页面。接口始终按当前 Owner 隔离；生产模式下即使猜到路径也
返回 404。

运行三种架构对比：

```bash
cd backend
python -m app.evals.runner --workflow architecture \
  --fixture ../datasets/sanitized_samples/stage3_stats_fixture.csv
```
