# Agent 执行约束

## 当前阶段

阶段 0 至阶段 11 已完成实现；阶段 8 包含受校验任务图、Budget Agent 和显式确认；阶段 9 包含
本地 Developer Console、三架构量化评测和失败样本；阶段 10 包含用户确认、版本化、可删除记忆
与检索 Trace；阶段 11 包含本地发行、数据生命周期、备份恢复和安全加固。下一开发阶段为阶段 12；
一次只实施一个阶段。

## 允许修改范围

当前允许维护 ModelProvider、Single/Multi/Planner Agent、Semantic 分类、Budget、用户记忆、
本地数据生命周期、只读 Tool 编排、Trace/evidence、评测、迁移、测试和文档。不得提前实现阶段 12，不得加入真实
账单、微信登录、自动账户连接、Redis、Celery、Kubernetes 或未评测的 Agent。

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

阶段 5 至 11 还应运行 Provider 切换/失败、Agent 约束、数值 grounding、Semantic 规则优先、
Planner 校验/重规划/确认、Verifier 失败路径、记忆生命周期和 30 题三架构对比；前端未改动时仍执行
typecheck、Vitest、build 和 lint 回归；阶段 11 还需验证备份恢复、导出删除、恶意文件、Host
门禁和提示注入。服务器上使用 Docker 时，应以临时
`PFA_DATA_DIR` 验证，避免触碰真实账本目录。
