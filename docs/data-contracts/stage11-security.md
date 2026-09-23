# 阶段 11：本地发行、数据生命周期与安全合同

## 发行边界

- 发行形态选用普通 Local Web：浏览器访问 `http://127.0.0.1:5173`，Nginx 反向代理后端。
- Compose 的前端和后端端口只绑定宿主机回环地址；后端 `TrustedHostMiddleware` 默认只接受
  `127.0.0.1`、`localhost`、`[::1]` 和测试客户端 Host。
- 未选择 PWA：离线缓存会增加敏感页面残留；未选择 Tauri：当前无需桌面原生能力和额外供应链。
- 前后端容器使用只读根文件系统、`no-new-privileges` 和空 capability 集；唯一持久写入位置是
  `PFA_DATA_DIR` 挂载到的 `/workspace/data`。

## 固定目录与升级

`DATA_DIR` 是数据库、短期上传、日志和备份的唯一根目录：

```text
DATA_DIR/
├── personal_finance.db
├── uploads/
├── logs/
└── backups/
```

未显式设置 `DATABASE_URL` 时，它由 `DATA_DIR/personal_finance.db` 推导。未由 Alembic 管理的
本地库如检测到 Schema 变化，会在 `create_all`/兼容变更前创建 `pre_upgrade` 备份；Alembic 管理
的旧库在普通启动时明确失败，必须执行 `python -m app.data_admin upgrade`。该命令在迁移前创建
一致性备份，已是 head 时不写入。升级不会静默覆盖旧数据。

## 备份和恢复

- SQLite 在线备份 API 生成一致性 `.sqlite3` 快照和独立 JSON manifest。
- manifest 包含随机 32 位十六进制 ID、类型、UTC 时间、字节数、SHA-256、Schema 指纹和固定文件名。
- 只列出备份目录内符合固定命名的常规文件；符号链接、路径片段和伪造文件名不参与恢复。
- 恢复前检查大小上限、SHA-256、`PRAGMA integrity_check` 和当前 Schema 兼容性。
- 覆盖数据库前自动创建 `pre_restore` 安全备份，替换后再次做完整性和 Schema 校验。
- 手工备份/恢复令牌与 Owner、动作和目标备份 ID 绑定，短时有效且仅可消费一次。

数据 JSON ZIP 导出是可携带副本，不等同于数据库恢复包。它只包含当前 Owner 的业务表数据，
不含 `bill_imports.raw_path` 和任何原始账单文件。

## 删除与原始文件策略

- 原始账单默认在导入后 60 分钟清理；事实记录和文件摘要保留。
- 原始文件删除会先解析规范路径，并验证它位于 `DATA_DIR/uploads`；数据库中的外部路径不会被删除。
- “删除全部数据”删除当前本地 Owner 的业务行，并清理 uploads、logs、backups，随后执行 SQLite
  WAL 截断和 `VACUUM`。该操作不可恢复，UI 需要警告确认和精确短语确认。
- 导出、手工备份、恢复、删除均要求 `X-PFA-Local-Action: confirm` 及一次性确认令牌。

## 文件安全

- 只接受 CSV/XLSX，并同时校验扩展名和内容结构；伪装成 CSV 的 ZIP/OLE/PDF/ELF 被拒绝。
- XLSX 作为 ZIP 容器检查条目数、单条/总解压大小、压缩比、加密标记和必需工作簿成员。
- 绝对路径、`..`、反斜杠形式的路径穿越被拒绝；服务不把归档成员写入文件系统。
- 上传文件名只保留 basename 并清洗；服务生成随机前缀，客户端不能决定存储路径。

## Agent 安全与资源上限

- 模型只获得 Registry 中 9 个只读 Tool；数据管理、文件、Shell、SQL 和网络能力不在 Tool Schema。
- Tool 输出被封装为 `security_label=untrusted_tool_data`，账单商户、描述、分类中的文字只能视为数据，
  不能修改系统提示、Tool 权限或执行流程。
- Single/Multi/Planner 均受步数、Tool 次数、模型次数、总 Token、费用、总时长限制；发送模型前还
  检查 `AGENT_MAX_CONTEXT_CHARS`。Tool 本身有超时和返回字节上限。
- Trace 不保存 API Key、完整提示、reasoning、完整账单行、原始文件内容或完整 Tool 上下文。

## 验收映射

- 升级不静默覆盖：旧本地 Schema 自动 `pre_upgrade` 备份；旧 Alembic 库拒绝普通启动。
- 备份恢复演练：创建备份、修改数据、恢复、核对旧值，并验证 `pre_restore` 安全快照。
- 原始账单策略：TTL 清理、导出排除、全量删除和目录逃逸保护均有自动化测试。
- API 默认拒绝非本机访问：Compose 回环绑定、Nginx Host 门禁、后端 Trusted Host 三层限制。
- 账单不能改变提示/权限：恶意描述作为不可信 Tool 数据进入模型，Registry 不出现写入类 Tool。
