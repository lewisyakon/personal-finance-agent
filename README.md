# 个人消费分析多智能体系统

本仓库按《个人消费分析多智能体系统开发规格》分阶段实现。本次交付完成：

- 阶段 0：Vue 3 + TypeScript + Vite、FastAPI、SQLite/WAL、Alembic、mock ModelProvider、VS Code 任务和基础测试。
- 阶段 1：微信账单 CSV Parser，支持 UTF-8/UTF-8 BOM/GB18030/UTF-16 尝试、表头识别、金额/时间/方向/状态标准化、行级错误和 Golden Test。

当前 Parser 只支持 CSV；Excel 和 ZIP 会在脱敏样例确实需要时按阶段扩展。Parser 不调用 LLM。

## 用户目录安装

项目不要求 root 权限。推荐使用用户目录中的 Python 3.12（例如 `uv python install 3.12`）创建虚拟环境：

```bash
cd personal-finance-agent
source scripts/user-runtime.sh
~/.local/bin/uv venv --python 3.12 .venv
source .venv/bin/activate
python -m pip install -e './backend[dev]'
cd frontend && npm install
```

如果没有 `uv`，也可以使用已经安装的 Python 3.12 创建 `.venv`。不要将真实账单、API Key 或 `.env` 提交到 Git。

## 开发命令

```bash
# 后端
cd backend && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 前端
cd frontend && npm run dev

# 后端测试与检查
cd backend && pytest && ruff check app tests

# 前端构建、测试与类型检查
cd frontend && npm run typecheck && npm test && npm run build
```

默认 API 地址为 `http://127.0.0.1:8000`，前端地址为 `http://127.0.0.1:5173`。

如果需要同时启动前后端：

```bash
./scripts/app-dev.sh
```
