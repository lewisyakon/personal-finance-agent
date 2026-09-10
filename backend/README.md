# Backend

阶段 0 提供 FastAPI 状态接口和 mock ModelProvider；阶段 1 提供无模型调用的微信 CSV Parser，当前导入链路也支持微信 XLSX。

在 `backend` 目录运行：

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
