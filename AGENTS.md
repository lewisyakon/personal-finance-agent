# Agent 执行约束

## 当前阶段

阶段 0 至阶段 5 已完成实现；当前阶段 5 包含可切换 ModelProvider、有界 Single-Agent、
Agent Trace、API 和 30 题评测基线。阶段 6 尚未开始；一次只实施一个阶段。

## 允许修改范围

当前阶段允许修改 ModelProvider、Single-Agent、只读 Tool 编排、Trace/evidence 持久化、
迁移、测试和文档。不得提前实现阶段 6 多 Agent，不得加入真实账单、微信登录、自动账户
连接、Redis、Celery、Kubernetes 或未评测的 Agent。

## 约束

- 金额使用整数最小货币单位，不使用浮点数。
- 时间必须带时区，默认 `Asia/Shanghai`。
- Parser 只做格式转换，不调用 LLM、不做统计解释。
- Tool 参数不接受 owner_id、任意 SQL、任意文件路径或任意 URL；Owner 由服务端上下文注入。
- Tool Trace 不记录 API Key、完整账单行、文件路径或完整模型上下文。
- Model Trace 不保存完整 prompt、Tool 上下文或 reasoning；Provider 不得静默降级。
- 测试夹具只能是脱敏或合成账单。
- 不记录 API Key、ZIP 密码、完整账单行或完整模型上下文。
- 本地服务只监听回环地址。

## 验收命令

```bash
cd backend && pytest && ruff check app tests
cd ../frontend && npm run typecheck && npm test && npm run build
```

阶段 5 还应运行 Provider 切换/失败、Single-Agent 约束、数值 grounding 和 30 题评测；前端未改动时仍执行
typecheck、Vitest、build 和 lint 回归。服务器上使用 Docker 时，应以临时
`PFA_DATA_DIR` 验证，避免触碰真实账本目录。
