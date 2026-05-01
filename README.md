# Gcode Security Guard

麒麟OS智能运维Agent — 对话式运维 + 三层安全护栏。

```
User → API(Unix Socket) → Intent Filter(Qwen2.5) → Agent(Runbook/Monitor) → Audit(SQLite)
```

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
│   ├── api/server.py              # Unix Domain Socket 服务端
│   ├── intent/                    # 意图分类 (Qwen2.5-0.5B)
│   │   ├── model.py
│   │   └── classifier.py
│   ├── audit/                     # 审计系统 (SQLite)
│   │   ├── models.py
│   │   └── logger.py
│   ├── contracts/types.py         # SessionContext + ToolCallRecord
│   └── gcode/                     # Agent CLI 工具
│       ├── cli/main.py            # CLI 入口
│       ├── core/                  # Runbook 引擎 + 会话管理
│       │   ├── engine.py
│       │   └── session.py
│       ├── monitor/               # 健康检查引擎
│       │   ├── checkers.py        # HTTP/TCP/进程/磁盘/内存检查
│       │   ├── collector.py       # 指标采集 (CPU/内存/磁盘)
│       │   ├── evaluator.py       # 检查套件 + 阈值评估
│       │   └── models.py          # CheckResult, MetricSnapshot
│       ├── alert/                 # 告警引擎
│       │   ├── engine.py          # Alert 生命周期管理
│       │   ├── manager.py         # SQLite 规则管理 + 冷却去重
│       │   ├── models.py          # AlertRule, AlertEvent
│       │   └── notifier.py        # stdout/webhook 通知
│       ├── logpipe/               # 日志管道
│       │   ├── engine.py          # JSONL 日志存储 + 异常检测
│       │   ├── pipeline.py        # SQLite 采集 + 检测规则
│       │   ├── sources.py         # 日志源适配器 (文件)
│       │   └── detectors.py       # 正则模式检测
│       └── report/reporter.py     # 日报/周报/事件报告
├── schema/gcode-protocol.json     # m1↔dp1 接口契约
├── tests/
├── pyproject.toml
├── CONTEXT.md
└── README.md
```

## 快速开始

### 安装

```bash
git clone https://github.com/yGGGgGGGy/gcode-security-guard.git
cd gcode-security-guard
pip install -e .

# 预下载模型（可选）
python -c "from src.intent.model import IntentModel; m = IntentModel(); m.load(); m.unload()"
```

### 启动 API 服务

```bash
python -m src.api.server
# Unix Domain Socket 监听 /run/gcode/gcode.sock
# 转发到 dp1: /run/gcode/gcode-dp1.sock
```

### 测试

```bash
echo '{"query":"查看系统内存","user_id":"admin","session_id":"test-001"}' | nc -U /run/gcode/gcode.sock
```

## CLI 命令

### 交互对话

```bash
# 交互式 REPL
gcode serve    # 命令: /help, /history, /quit

# 单次查询
gcode ask "nginx 是否正常？"
gcode ask "最近有什么告警？"
```

### Runbook 执行

```bash
# 预览
gcode run ./runbooks/restart-nginx.yaml --dry-run

# 执行
gcode run ./runbooks/restart-nginx.yaml
```

Runbook 格式：

```yaml
steps:
  - name: check disk
    command: df -h
    timeout: 10
    retry: 2
  - name: restart nginx
    command: systemctl restart nginx
    rollback: systemctl start nginx
```

### 报告生成

```bash
gcode report --type daily
gcode report --type weekly --output weekly.txt
gcode report --type incident
```

### 健康检查 (monitor)

```bash
# 运行默认健康检查（磁盘、内存、TCP）
gcode check
```

### 告警管理 (alert)

```bash
# 添加规则
gcode alert add-rule --name "svc-down" --monitor "nginx" --condition fail --cooldown 5

# 查看规则
gcode alert list-rules

# 查看事件
gcode alert events --limit 20

# 添加通知渠道
gcode alert add-notifier --channel stdout
gcode alert add-notifier --channel webhook --target "https://hooks.example.com/alert"
```

### 日志管道 (logpipe)

```bash
# 添加日志源
gcode logpipe add-source --name "syslog" --type file --path /var/log/syslog

# 列出日志源
gcode logpipe list-sources

# 采集日志
gcode logpipe collect --name syslog

# 查看日志
gcode logpipe entries --level ERROR --limit 50

# 添加检测规则
gcode logpipe add-rule --name "oom" --pattern "Out of memory" --severity error

# 扫描异常
gcode logpipe scan --limit 500
```

## 模块说明

### core — Runbook 引擎 + 会话管理

- `RunbookEngine`: YAML 解析、步骤执行、失败重试、自动回滚
- `SessionManager`: 交互式 REPL、SQLite 会话持久化、意图路由

### monitor — 健康检查引擎

- `Checker`: HTTP / TCP / 进程 / 磁盘 / 内存 检查
- `Evaluator`: 检查套件运行 + 整体健康评估 (OK/WARN/FAIL 计数)
- `Collector`: CPU / 内存 / 磁盘指标采集（psutil + /proc 回退）
- `ThresholdRule`: 阈值告警规则（warn_pct / fail_pct）

### alert — 告警引擎

- `AlertEngine`: Alert 创建/确认/解决，JSON 文件持久化
- `AlertManager`: SQLite 规则存储、条件匹配、冷却去重
- 条件类型: `fail`, `warn`, `always`
- 通知渠道: stdout, webhook

### logpipe — 日志管道

- `LogPipeline` (engine): JSONL 日志存储、按级别/关键词查询、模式聚合异常检测
- `LogPipeline` (pipeline): SQLite 采集 + 检测规则管理 + 增量文件读取
- `detectors`: 正则模式匹配、日志级别启发式分类
- `sources`: FileSource 文件日志适配器

### report — 报告生成

- `Reporter`: 日报（服务健康 + 告警 + 日志异常）、周报、事件报告模板

### intent — 意图分类

- `IntentClassifier`: Qwen2.5-0.5B 多标签零样本分类
- 判定逻辑: score >= 0.6 → safe, score < 0.4 → needs-review, 否则根据标签映射

### audit — 审计系统

- `AuditStore`: SQLite 全量记录
- `AuditLogger`: 思维链追踪、`trace()` 上下文管理器、自动耗时统计
- 查询接口: `query_by_session()`, `query_by_user()`

## 开发指南

### 添加新模块

1. 在 `src/gcode/<module>/` 下创建包：

```
src/gcode/<module>/
├── __init__.py    # 暴露 register_commands(cli_group)
├── <module>.py    # 核心逻辑
└── models.py      # 数据模型
```

2. `__init__.py` 模板：

```python
def register_commands(cli_group):
    @cli_group.command()
    def my_command():
        """Description."""
        pass
```

3. 在 `src/gcode/cli/main.py` 注册：

```python
from gcode.<module> import register_commands as register_<module>
register_<module>(main)
```

### 测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### 代码规范

```bash
ruff check src/ tests/
ruff format src/ tests/
```

## 配置

### 意图分类阈值

```python
# src/intent/classifier.py
SAFE_THRESHOLD = 0.6
NEEDS_REVIEW_THRESHOLD = 0.4
```

### 模型切换

```python
# 轻量替代
model = IntentModel("MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli")
# GPU 加速
model._pipeline_device = 0
```

## API 协议

客户端 → m1:

```json
{
  "query": "查看 /var/log/messages 最近20行",
  "user_id": "operator1",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

m1 → 客户端：

| 状态 | 含义 |
|------|------|
| `{"status":"success","data":{...}}` | safe，执行结果返回 |
| `{"status":"rejected","reason":"..."}` | unsafe，拒绝执行 |
| `{"status":"needs_review","reason":"..."}` | 需人工审核 |

## 麒麟OS 适配

- SELinux: `/run/gcode/` 需设 `svirt_socket_t` 类型
- auditd: 审计表结构与 auditd 兼容
- systemd: 提供 `contrib/gcode-security-guard.service`

## 配对仓库

- [gcode-mcp-server](https://github.com/yGGGgGGGy/gcode-mcp-server) — MCP Server + Tool 实现 + 执行层约束 (dp1)

## License

AGPL-3.0
