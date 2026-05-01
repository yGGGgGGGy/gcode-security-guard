# Gcode Security Guard (m1)

麒麟OS智能运维Agent — **安全层**。负责意图过滤（入口）和全链路审计（出口）。

## 架构角色

```
User → 接入层(m1: api/server.py)
  → 推理层(m1: intent/classifier.py)
    → [safe] → 执行层(dp1: MCP Server)
    → [unsafe/needs-review] → 拒绝
  → 审计层(m1: audit/logger.py → SQLite)
```

m1 与 dp1 通过 Unix Domain Socket 通信，协议见 [schema/gcode-protocol.json](./schema/gcode-protocol.json)。

## 三层安全护栏

| 层级 | 位置 | 技术 | 说明 |
|------|------|------|------|
| 意图过滤（入口） | m1 | Qwen2.5-0.5B 零样本分类 | safe / unsafe / needs-review 三层判定 |
| 最小权限（出口） | dp1 | SessionContext.capability_set | read_only / read_write / admin |
| 思维链审计（全链路） | m1 | SQLite 全量记录 | 事后回溯，按用户/会话检索 |

## 项目结构

```
gcode-security-guard/
├── src/
│   ├── api/server.py          # Unix Domain Socket 服务端
│   ├── intent/
│   │   ├── model.py           # Qwen2.5-0.5B 模型加载
│   │   └── classifier.py      # 意图分类 + 三层判定
│   ├── audit/
│   │   ├── models.py          # SQLite 数据模型
│   │   └── logger.py          # 全链路思维链追踪
│   └── contracts/
│       └── types.py           # SessionContext + ToolCallRecord
├── schema/
│   └── gcode-protocol.json    # m1↔dp1 接口契约
├── tests/
├── pyproject.toml
├── CONTEXT.md
└── README.md
```

## 快速开始

### 前置条件

- Python >= 3.11
- dp1 侧 gcode-mcp-server 已启动（监听 `/run/gcode/gcode-dp1.sock`）
- 可选：HuggingFace 缓存目录 `/models`（避免启动时下载模型）

### 安装

```bash
cd gcode-security-guard
pip install -e .

# 预下载模型（可选，避免首次启动延迟）
python -c "from src.intent.model import IntentModel; m = IntentModel(); m.load(); m.unload()"
```

### 启动

```bash
# 前台运行
python -m src.api.server

# 开机自启（systemd）
sudo cp contrib/gcode-security-guard.service /etc/systemd/system/
sudo systemctl enable --now gcode-security-guard
```

Unix Domain Socket 监听 `/run/gcode/gcode.sock`，转发给 `/run/gcode/gcode-dp1.sock`。

### 测试

```bash
# 发送测试请求（需要 dp1 先启动）
echo '{"query":"查看当前系统内存使用情况","user_id":"admin","session_id":"test-001"}' | nc -U /run/gcode/gcode.sock
```

## 配置

### 意图分类阈值

编辑 `src/intent/classifier.py`:

```python
SAFE_THRESHOLD = 0.6          # 高于此值 → safe
NEEDS_REVIEW_THRESHOLD = 0.4  # 低于此值 → needs-review
```

### Socket 路径

默认路径可被覆盖：

```python
from src.api.server import GcodeServer
server = GcodeServer(
    socket_path="/custom/path/m1.sock",
    dp1_socket_path="/custom/path/dp1.sock",
)
server.start()
```

## API 协议

### 客户端 → m1

```json
{
  "query": "查看 /var/log/messages 最近20行",
  "user_id": "operator1",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### m1 → 客户端（safe 通过）

```json
{
  "status": "success",
  "data": { "result": "... dp1 执行结果 ..." },
  "audit_id": "770e8400-e29b-41d4-a716-446655440001"
}
```

### m1 → 客户端（unsafe 拒绝）

```json
{
  "status": "rejected",
  "reason": "Intent classified as unsafe",
  "detail": "unsafe_file_write"
}
```

### m1 → 客户端（needs-review）

```json
{
  "status": "needs_review",
  "reason": "Query requires human review",
  "detail": "needs_review_sensitive"
}
```

## 审计查询

```python
from src.audit.models import AuditStore

store = AuditStore("gcode_audit.db")
store.init_db()

# 按会话查询
records = store.query_by_session("test-001")
for r in records:
    print(r["original_query"], r["intent_result"], r["chain_of_thought"])

# 按用户查询
records = store.query_by_user("operator1", limit=50)
```

## 麒麟OS 适配

- **SELinux 策略**: Unix Socket 路径 `/run/gcode/` 需设置 `svirt_socket_t` 类型
- **auditd 打通**: 审计表结构与 auditd 记录兼容，可通过 `audit2sql` 导入
- **rpm 打包**: `python -m build && rpmbuild -ba contrib/gcode-security-guard.spec`

## 模型说明

默认使用 `Qwen/Qwen2.5-0.5B`，CPU 推理，首次加载约 30 秒（取决于 CPU）。

切换模型：

```python
# 轻量替代
model = IntentModel("MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli")

# GPU 加速
model = IntentModel("Qwen/Qwen2.5-0.5B")
model._pipeline_device = 0  # GPU device
```

## 配对仓库

- [gcode-mcp-server](https://github.com/yGGGgGGGy/gcode-mcp-server) — MCP Server + Tool 实现 + 执行层约束 (dp1)

## License

AGPL-3.0
