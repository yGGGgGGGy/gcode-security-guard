# Gcode Security Guard

麒麟OS 智能运维 Agent — 对话式运维 + 三层安全护栏 + 一键部署。

```
User → API(Unix Socket) → Intent Filter(Qwen2.5) → Agent(Runbook/Monitor/Logpipe) → Audit(SQLite)
```

## 三层安全架构

| 层级 | 位置 | 技术 | 说明 |
|---|---|---|---|
| 意图过滤（入口） | m1 | Qwen2.5-0.5B 零样本分类 | safe / unsafe / needs-review 三层判定 |
| 最小权限（出口） | dp1 | SessionContext.capability_set | read_only / read_write / admin |
| 思维链审计（全链路） | m1 | SQLite 全量记录 | 事后回溯，按用户/会话检索 |

## 环境要求

| 依赖 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.11+ | venv 隔离安装 |
| 操作系统 | 麒麟OS / CentOS 8+ / Ubuntu 22.04+ | systemd + SELinux 支持 |
| Git | 2.30+ | 克隆代码 |
| pip | 23.0+ | 包管理 |
| 磁盘空间 | ~2GB | 含 Qwen2.5-0.5B 模型 (~1GB) |
| 可选 | psutil, auditd, SELinux | 性能采集、审计、安全加固 |

## 一键部署

```bash
# 1. 克隆代码
git clone https://github.com/yGGGgGGGy/gcode-security-guard.git
cd gcode-security-guard

# 2. 一键安装（需要 root）
sudo bash deploy/install.sh

# 3. 可选参数
sudo bash deploy/install.sh --skip-model      # 跳过模型下载
sudo bash deploy/install.sh --skip-selinux    # 跳过 SELinux 配置
```

安装脚本自动完成：
- 检查 Python 3.11+
- 安装系统依赖（自动识别 dnf/yum/apt）
- 创建 gcode 系统用户
- 克隆代码 + 创建 Python 虚拟环境
- 预下载 Qwen2.5-0.5B 模型
- 安装 systemd 服务
- 配置 SELinux 策略 + auditd 规则
- 启动双服务

## 手动安装

```bash
# 创建虚拟环境
python3 -m venv /opt/gcode/venv
/opt/gcode/venv/bin/pip install -e .

# 初始化配置
mkdir -p /etc/gcode /var/log/gcode /var/lib/gcode /run/gcode
cp config.yaml /etc/gcode/config.yaml

# 手动启动（调试用）
/opt/gcode/venv/bin/python -m gcode.cli.main serve
```

## 项目架构

```
┌─────────────────────────────────────────────────────────┐
│                     客户端 (CLI / API)                    │
└─────────────────┬───────────────────────────────────────┘
                  │  Unix Domain Socket
                  ▼
┌─────────────────────────────────────────────────────────┐
│              m1: Security Guard (安全层)                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐  │
│  │ Intent   │  │ Session  │  │ Audit Logger          │  │
│  │ Filter   │──│ Manager  │──│ (SQLite 全量记录)      │  │
│  │ Qwen2.5  │  │          │  │                       │  │
│  └──────────┘  └──────────┘  └───────────────────────┘  │
└─────────────────┬───────────────────────────────────────┘
                  │  Unix Domain Socket
                  ▼
┌─────────────────────────────────────────────────────────┐
│              dp1: MCP Server (执行层)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ 12 Tools │  │ Sandbox  │  │ Capability Control   │  │
│  │ (RO/RW)  │  │ (proc)   │  │ (read_only/write)    │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│              Gcode Agent CLI (运维工具层)                  │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌────────┐ ┌──────────┐   │
│  │Core  │ │Monitor│ │Alert │ │Logpipe │ │ Report   │   │
│  │Runbook│ │Health │ │Notify│ │Collect │ │ Daily/   │   │
│  │Session│ │Check  │ │Route │ │Detect  │ │ Weekly   │   │
│  └──────┘ └──────┘ └──────┘ └────────┘ └──────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 模块说明

### core — Runbook 引擎 + 会话管理

```bash
gcode serve              # 交互式 REPL
gcode ask "内存使用"      # 单次查询，自动路由到模块
gcode run runbook.yaml   # 执行 Runbook（支持重试、回滚）
```

- `engine.py`: YAML 解析、步骤执行、失败重试、自动回滚
- `session.py`: 交互式对话、SQLite 持久化、LLM推理 + 关键词兜底
- `config.py`: 统一配置加载（YAML + 默认值），`GcodeConfig` 数据类

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

### monitor — 健康检查引擎

```bash
gcode check              # 运行默认检查（磁盘、内存、TCP）
```

- `checkers.py`: HTTP / TCP / 进程 / 磁盘 / 内存 检查
- `evaluator.py`: 检查套件 + 整体健康评估（OK/WARN/FAIL 计数）
- `collector.py`: CPU / 内存 / 磁盘指标采集（psutil + /proc 回退）
- 检查失败自动触发告警（monitor → alert 桥接）

### alert — 告警引擎

```bash
gcode alert list                   # 查看活跃告警
gcode alert ack <alert-id>         # 确认告警
gcode alert resolve <alert-id>     # 解决告警
gcode alert summary                # 告警统计
gcode alert-config add-rule ...    # 添加告警规则
gcode alert-config events          # 查看告警事件
```

- `engine.py`: Alert 创建/确认/解决，JSON 持久化
- `manager.py`: SQLite 规则存储、条件匹配、冷却去重
- `notifier.py`: stdout/webhook 多渠道通知
- 条件类型: `fail`, `warn`, `always`

### logpipe — 日志管道

```bash
gcode log query --level ERROR --keyword timeout
gcode log stats                     # 日志统计
gcode log anomalies --threshold 10  # 异常检测
gcode logpipe add-source --name syslog --type file --path /var/log/syslog
gcode logpipe collect               # 采集日志
gcode logpipe scan --limit 500      # 规则扫描
```

- `engine.py`: JSONL 存储、级别/关键词查询、模式聚合异常检测
- `pipeline.py`: SQLite 采集 + 检测规则 + 增量文件读取
- `detectors.py`: 正则模式匹配、日志级别启发式分类
- `sources.py`: FileSource 文件日志适配器

### report — 报告生成

```bash
gcode report --type daily
gcode report --type weekly --output weekly.txt
gcode report --type incident
```

报告自动拉取 monitor/alert/logpipe 实时数据，包含：
- 服务健康状态 + 各项指标
- 活跃告警列表
- 日志异常检测结果

### reasoning — LLM 推理层

支持多模型：
- **API**: Claude (Anthropic), GPT (OpenAI), DeepSeek
- **本地**: Ollama (Qwen, Llama, Mistral 等)

```yaml
# config.yaml
reasoner:
  provider: anthropic        # anthropic / openai / deepseek / ollama
  api_key: sk-xxx
  model: claude-sonnet-4-6
  # ollama 不需要 api_key
```

## API 接口

### MCP Server (dp1 执行层)

```bash
python -m gcode.mcp.server    # stdio 模式
```

提供 12 个 Tool：

| 分类 | Tool | 功能 | 权限 |
|---|---|---|---|
| 只读 | `sys_info` | 系统概况 | read_only |
| | `ps_list` | 进程列表 | read_only |
| | `df_h` | 磁盘使用 | read_only |
| | `netstat` | 网络连接 | read_only |
| | `journalctl` | 系统日志 | read_only |
| 指标 | `cpu_usage` | CPU 使用率 | read_only |
| | `mem_usage` | 内存使用率 | read_only |
| | `io_stat` | IO 统计 | read_only |
| | `disk_health` | 磁盘健康 | read_only |
| 管理 | `service_status` | 服务状态 | read_only |
| | `service_restart` | 服务重启 | read_write |
| | `pkg_install` | 软件包安装 | admin |

### Security Guard API (m1 安全层)

```bash
python -m src.api.server     # Unix Domain Socket: /run/gcode/gcode.sock
```

**请求格式：**
```json
{
  "query": "查看 /var/log/messages 最近20行",
  "user_id": "operator1",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**响应：**
```json
{"status": "success", "data": {...}}          // safe
{"status": "rejected", "reason": "..."}       // unsafe
{"status": "needs_review", "reason": "..."}   // 需人工审核
```

**请求流程：**
```
客户端 → Unix Socket → IntentClassifier (Qwen2.5)
  → [safe] → 转发 dp1 MCP Server → AuditLogger 记录
  → [unsafe] → 拒绝
  → [needs-review] → 暂存待审核
```

## 启动服务

```bash
# 开发调试
python -m gcode.cli.main serve         # CLI REPL 模式
python -m gcode.cli.main check         # 健康检查

# systemd 生产模式
sudo systemctl start gcode-security-guard gcode-mcp-server

# 查看状态
systemctl status gcode-security-guard gcode-mcp-server

# 查看日志
journalctl -u gcode-security-guard -f
```

## 测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
# 56 passed
```

## 测试连接

```bash
echo '{"query":"查看磁盘使用"}' | socat - UNIX-CONNECT:/run/gcode/gcode.sock
```

## 项目结构

```
src/
├── api/server.py              # Unix Domain Socket 服务端
├── gcode/
│   ├── cli/main.py            # CLI 入口 (Click)
│   ├── core/                  # Runbook引擎 + 会话管理 + 配置
│   ├── monitor/               # 健康检查引擎
│   ├── alert/                 # 告警引擎
│   ├── logpipe/               # 日志管道
│   ├── report/                # 报告生成
│   ├── mcp/                   # MCP Server (12 Tools)
│   └── reasoning/             # LLM 推理层
├── contracts/types.py         # SessionContext + ToolCallRecord
├── deploy/
│   ├── install.sh             # 一键部署脚本
│   ├── gcode-security-guard.service
│   ├── gcode-mcp-server.service
│   └── gcode-selinux.te       # SELinux 策略
├── tests/                     # 56 个单元测试
├── config.yaml                # 配置模板
└── pyproject.toml
```

## 配对仓库

- [gcode-mcp-server](https://github.com/yGGGgGGGy/gcode-mcp-server) — MCP Server + Tool 实现 + 执行层约束 (dp1)

## License

AGPL-3.0
