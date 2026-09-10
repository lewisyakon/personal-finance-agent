# Agent 执行约束

## 当前阶段

阶段 0、阶段 1 和阶段 2 已完成实现。阶段 2 的本次变更集中在导入、去重与交易管理；一次只实施一个阶段。

## 允许修改范围

当前阶段允许修改工程基线、微信 CSV Parser、导入/交易 Service、API、Vue 导入与交易页面、测试、文档和示例数据。不得加入真实账单、微信登录、自动账户连接、Redis、Celery、Kubernetes 或未评测的 Agent。

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
