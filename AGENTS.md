# Agent 执行约束

## 当前阶段

阶段 0、阶段 1 和阶段 2 已完成实现；当前正在收尾阶段 3（统计服务与 Dashboard）。
阶段 3 的变更集中在确定性统计、统计 API、统计口径文档、合成核对夹具和 Vue Dashboard；
一次只实施一个阶段。

## 允许修改范围

当前阶段允许修改工程基线、微信 CSV/XLSX Parser、导入/交易/统计 Service、API、Vue 导入、
交易与 Dashboard 页面、测试、文档和合成示例数据。不得加入真实账单、微信登录、自动账户
连接、Redis、Celery、Kubernetes 或未评测的 Agent。

## 约束

- 金额使用整数最小货币单位，不使用浮点数。
- 时间必须带时区，默认 `Asia/Shanghai`。
- Parser 只做格式转换，不调用 LLM、不做统计解释。
- 测试夹具只能是脱敏或合成账单。
- 不记录 API Key、ZIP 密码、完整账单行或完整模型上下文。
- 本地服务只监听回环地址。

## 验收命令

```bash
cd backend && pytest && ruff check app tests
cd ../frontend && npm run typecheck && npm test && npm run build
```

阶段 3 还应执行前端 lint；服务器上使用 Docker 时，应以临时 `PFA_DATA_DIR` 完成后端
测试和统计 API 运行态冒烟，避免触碰真实账本目录。
