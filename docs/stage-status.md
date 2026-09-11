# 阶段状态

## 阶段 0：工程基线

- 状态：已实现；前端与后端静态检查已通过，Docker 运行态已验证，状态接口和前端访问链路正常。
- 范围：目录骨架、FastAPI 状态接口、SQLite WAL、Alembic 配置、mock Provider、Vue 首页、VS Code 配置、基础测试。

## 阶段 1：微信账单 Parser

- 状态：已实现；前端 typecheck/Vitest/build/lint 与后端 Ruff/语法检查已通过，Docker 运行态已验证，Parser/API 链路可用。
- 范围：CSV、微信 XLSX、编码尝试、微信表头识别、金额/时间/方向/状态标准化、行级错误、3 个合成样例和 Golden Test。
- 未包含：其他 Excel 格式、ZIP、去重、入库、分类和统计。

## 阶段 2：导入、去重与交易管理

- 状态：已实现并完成运行态验收；前端 typecheck/Vitest/build/lint、后端 Ruff/语法检查、Docker 镜像构建、容器启动和前后端接口冒烟验证均已通过。
- 范围：`WorkspaceOwner`、`BillImport`、`Transaction` 和分类修改审计表；进程内导入执行器；owner 范围 HMAC-SHA256 指纹和数据库唯一约束；重复文件幂等、重试、导入报告计数、原始文件 TTL 清理；导入和交易管理 API；Vue 导入记录与交易管理页面。
- 约束：当前只接受微信 CSV/XLSX；不调用模型；模型和客户端不能指定 owner_id；金额以整数最小货币单位存储；原始文件不进入日志和数据库内容字段。
- 已知限制：导入任务为同步进程内执行；ZIP 和更复杂的分类规则属于后续阶段；SQLite 日期列由服务按带时区输入查询并在 API 中返回 ISO 时间。

验收重点：

```bash
cd backend && pytest && ruff check app tests
cd ../frontend && npm run typecheck && npm test && npm run build
```

Docker 运行态验收记录：

- `python:3.12-slim` 后端镜像构建成功，依赖安装完成。
- Compose 网络和后端容器启动成功，Uvicorn 监听容器 `8000` 端口。
- `GET /` 和 `GET /api/v1/system/status` 均返回 `200 OK`。
- 前后端接口联调通过；停止 Compose 后容器正常退出。

## 阶段 3：统计服务与 Dashboard

- 状态：实现完成，待服务器运行态验收；统计 API、统计口径文档、合成数据准确性测试和 Dashboard 已加入。
- 范围：确定性 `Stats Service`、汇总/分类/趋势/商户/大额交易/固定可变/预算/环比同比
  API、单币种校验、退款/转账/失败交易和时间边界口径、Dashboard 展示与交易下钻。
- 约束：前端只消费 API 结果，不重新计算权威统计；金额仍以整数最小货币单位存储；
  统计服务不调用模型；用户人工分类修改后统计即时读取最新分类。
- 统计口径详见 [`docs/data-contracts/stage3-stats.md`](data-contracts/stage3-stats.md)，
  API 详见 [`docs/api/stage3-stats.md`](api/stage3-stats.md)。

验收重点：

```bash
cd backend && pytest && ruff check app tests
cd ../frontend && npm run typecheck && npm test && npm run build
```
