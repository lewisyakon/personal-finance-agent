# 阶段状态

## 阶段 0：工程基线

- 状态：已实现；前端与后端静态检查已通过，Docker 运行态已验证，状态接口和前端访问链路正常。
- 范围：目录骨架、FastAPI 状态接口、SQLite WAL、Alembic 配置、mock Provider、Vue 首页、VS Code 配置、基础测试。

## 阶段 1：微信账单 Parser

- 状态：已实现；前端 typecheck/Vitest/build/lint 与后端 Ruff/语法检查已通过，Docker 运行态已验证，Parser/API 链路可用。
- 范围：CSV、编码尝试、微信表头识别、金额/时间/方向/状态标准化、行级错误、3 个合成样例和 Golden Test。
- 未包含：Excel、ZIP、去重、入库、分类和统计。

## 阶段 2：导入、去重与交易管理

- 状态：已实现并完成运行态验收；前端 typecheck/Vitest/build/lint、后端 Ruff/语法检查、Docker 镜像构建、容器启动和前后端接口冒烟验证均已通过。
- 范围：`WorkspaceOwner`、`BillImport`、`Transaction` 和分类修改审计表；进程内导入执行器；owner 范围 HMAC-SHA256 指纹和数据库唯一约束；重复文件幂等、重试、导入报告计数、原始文件 TTL 清理；导入和交易管理 API；Vue 导入记录与交易管理页面。
- 约束：当前仍只接受微信 CSV；不调用模型；模型和客户端不能指定 owner_id；金额以整数最小货币单位存储；原始文件不进入日志和数据库内容字段。
- 已知限制：导入任务为同步进程内执行；Excel/ZIP、统计服务和分类规则属于后续阶段；SQLite 日期列由服务按带时区输入查询并在 API 中返回 ISO 时间。

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
