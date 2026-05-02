# Gcode Security Guard

**麒麟OS 智能运维 Agent** — 用自然语言管理服务器。三层安全护栏，一键部署。

```
用户自然语言 → Intent Filter(Qwen2.5) → LLM Reasoner(多模型) → MCP Server(12 Tool) → Audit(SQLite全量)
```

## 目录

- [快速开始](#快速开始)
- [一键部署](#一键部署)
- [使用方式](#使用方式)
- [三层安全架构](#三层安全架构)
- [项目架构](#项目架构)
- [模块说明](#模块说明)
- [高级用法（命令行参考）](#高级用法命令行参考)
- [API 接口](#api-接口)
- [配置参考](#配置参考)
- [启动与管理](#启动与管理)
- [测试](#测试)
- [项目结构](#项目结构)
- [故障排查](#故障排查)

## 快速开始

**不需要记命令。直接说话。**

```bash
git clone https://github.com/yGGGgGGGy/gcode-security-guard.git
cd gcode-security-guard
pip install -e .

# 交互式对话
gcode
# > gcode> 检查服务器状态
# > gcode> 磁盘满了怎么办？
# > gcode> 重启 nginx 会影响什么？

# 一句话查询
gcode "内存还剩多少？"
gcode "帮我看看 CPU 温度正常吗"

# 本地模型（Ollama，无需 API key）
ollama pull qwen2.5:7b
export GCODE_REASONER_API_KEY="ollama"
gcode

# 云端模型
export GCODE_REASONER_API_KEY="sk-xxx"
gcode "最近有哪些异常日志？"
```

> **核心设计：** `gcode` 无参数 = 交互式对话，`gcode "自然语言"` = 一句话查询。  
> 日常运维不需要记任何子命令。

## 一键部署

```bash
git clone https://github.com/yGGGgGGGy/gcode-security-guard.git
cd gcode-security-guard
sudo bash deploy/install.sh                   # 完整安装（含模型 + SELinux）
sudo bash deploy/install.sh --skip-model      # 跳过模型下载
sudo bash deploy/install.sh --skip-selinux    # 跳过 SELinux 配置
```

安装脚本自动完成：系统依赖 → 创建 gcode 用户 → 克隆代码 → Python venv → 模型下载 → systemd 服务 → SELinux 策略 → auditd 规则 → 启动验证。

部署后目录：

```
/opt/gcode/                          # 安装目录
├── venv/                            # Python 虚拟环境
├── src/                             # 源码
├── .env                             # 环境变量
└── models/                          # 模型缓存

/etc/systemd/system/
├── gcode-security-guard.service     # m1 安全层
└── gcode-mcp-server.service         # dp1 执行层

/run/gcode/                          # Unix Socket
├── gcode.sock                        # 安全层
└── gcode-dp1.sock                    # 执行层
```

部署后使用：

```bash
# 自然语言查询（通过 Unix Socket）
echo '{"query":"查看磁盘使用"}' | socat - UNIX-CONNECT:/run/gcode/gcode.sock

# 自然语言查询（如果装了 CLI）
gcode "检查服务状态"

# 查看服务日志
journalctl -u gcode-security-guard -f

# 确认服务状态
systemctl status gcode-security-guard gcode-mcp-server

# 下一步：配置 LLM API key
sudo vi /opt/gcode/.env   # 填入 GCODE_REASONER_API_KEY
```

## 使用方式

### 日常模式（自然语言）

```
gcode                          →  进入交互对话
gcode "检查服务器状态"           →  一句话查询
gcode "nginx 重启安全吗？"      →  自动调用工具分析
```

### 生产模式（Unix Socket API）

```bash
echo '{"query":"查看磁盘使用"}' | socat - UNIX-CONNECT:/run/gcode/gcode.sock
echo '{"query":"重启 nginx","user_id":"ops-01","session_id":"s-001"}' | \
  socat - UNIX-CONNECT:/run/gcode/gcode.sock
```

### Python API

```python
from gcode.core.session import SessionManager
s = SessionManager()
print(s.ask("CPU 使用率如何？"))
```

## 三层安全架构

| 层级 | 位置 | 技术 | 说明 |
|------|------|------|------|
| 意图过滤（入口） | m1 `intent/` | Qwen2.5-0.5B 13标签零样本分类 | safe / unsafe / needs-review 三层判定 |
| 最小权限（出口） | dp1 `mcp/` | 参数校验 + 注入防御 + dry-run + seccomp | Tool 分级（read_only / read_write / admin） |
| 思维链审计（全链路） | m1 `audit/` | SQLite 全量记录 + 异常检测 | 事后回溯，按用户/会话检索，DAG 回放 |

## 项目架构

```
用户输入（自然语言 / CLI / Unix Socket）
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│              m1: Gcode Security Guard (安全层)            │
│                                                         │
│  ┌─────────────────┐   ┌─────────────┐                  │
│  │ ① Intent Filter │   │ ② Reasoner  │                  │
│  │   Qwen2.5-0.5B  │──▶│   LLM 编排   │                  │
│  │   13标签分类     │   │   Claude/GPT │                  │
│  │   safe/unsafe   │   │   DeepSeek   │                  │
│  │   /needs-review │   │   Ollama     │                  │
│  └─────────────────┘   └──────┬──────┘                  │
│                               │                          │
│  ┌───────────────────────────┐│                          │
│  │ ③ Audit Logger           ││                          │
│  │   SQLite 全量记录         ││                          │
│  │   DAG 回放 + 异常检测     ││                          │
│  └───────────────────────────┘│                          │
└───────────────────────────────┼──────────────────────────┘
                                │ Unix Domain Socket
                                ▼
┌─────────────────────────────────────────────────────────┐
│              dp1: MCP Server (执行层)                     │
│                                                         │
│  ┌──────────┬──────────────┬──────────────────┐        │
│  │ 只读感知  │ 指标采集      │ 管理执行           │        │
│  │ sys_info │ cpu_usage    │ service_restart   │        │
│  │ ps_list  │ mem_usage    │ pkg_install       │        │
│  │ df_h     │ io_stat      │ service_status    │        │
│  │ netstat  │ disk_health  │                   │        │
│  │journalctl│              │                   │        │
│  └──────────┴──────────────┴──────────────────┘        │
│                         │                                │
│  ┌──────────────────────┴──────────────────────┐        │
│  │ ④ Executor + Sandbox                        │        │
│  │   参数校验 + 注入防御 + dry-run + seccomp     │        │
│  └──────────────────────┬──────────────────────┘        │
└─────────────────────────┼───────────────────────────────┘
                          │
                          ▼
      麒麟OS (systemd / rpm / journalctl / psutil)
```

### 数据流（以 "重启 nginx 会影响什么" 为例）

```
1. IntentFilter → safe_service_query, conf=0.85 → 放行
2. Reasoner → LLM 返回 tool_calls: [service_status("nginx"), ps_list()]
3. MCP Executor → systemctl status nginx + ps aux
4. LLM 汇总 → "nginx 运行正常，PID 1234，监听 80/443。重启会短暂中断连接。"
5. AuditLogger → SQLite 全量记录
```

## 模块说明

### core — Runbook 引擎 + 会话管理

自然语言查询的入口，自动路由到对应模块（监控/告警/日志）。

| 文件 | 功能 |
|------|------|
| `engine.py` | YAML Runbook 解析、逐步执行、失败重试、自动回滚 |
| `session.py` | 交互式对话、SQLite 对话历史、LLM 推理 + 关键词兜底 |
| `config.py` | YAML 配置加载、`GcodeConfig` 数据类、环境变量覆盖 |

Runbook 格式示例：

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

| 文件 | 功能 |
|------|------|
| `checkers.py` | HTTP / TCP / 进程 / 磁盘 / 内存 健康检查 |
| `evaluator.py` | 检查套件聚合（OK/WARN/FAIL 计数），失败触发告警 |
| `collector.py` | CPU / 内存 / 磁盘指标采集（psutil + /proc fallback） |

### alert — 告警引擎

| 文件 | 功能 |
|------|------|
| `engine.py` | Alert 创建/确认/解决，JSON 文件持久化 |
| `manager.py` | SQLite 规则存储、条件匹配、冷却去重、连续失败阈值 |
| `notifier.py` | stdout / webhook 多渠道通知 |

### logpipe — 日志管道

| 文件 | 功能 |
|------|------|
| `engine.py` | JSONL 日志采集、级别/关键词查询、模式聚合异常检测 |
| `pipeline.py` | SQLite 日志管道（source 管理 + 检测规则 + 增量 tail） |
| `detectors.py` | 正则检测匹配 + 日志级别启发式分类（CRITICAL→ERROR 等） |
| `sources.py` | FileSource: 文件增量 tail 读取 |

### reasoning — LLM 推理层（多 Provider）

支持多模型，统一接口，自动 tool calling：

| Provider | 模型示例 | 说明 |
|----------|---------|------|
| Anthropic | claude-sonnet-4-20250514 | 原生 Anthropic SDK |
| Qwen | qwen-plus | 阿里 DashScope（OpenAI 兼容） |
| DeepSeek | deepseek-chat | DeepSeek API（OpenAI 兼容） |
| Ollama | qwen2.5:7b | 本地部署，无需 API key |

```python
from gcode.reasoning.reasoner import Reasoner
from gcode.reasoning.providers.anthropic import AnthropicProvider

provider = AnthropicProvider(api_key="sk-ant-...", model="claude-sonnet-4-20250514")
reasoner = Reasoner(provider)
response = await reasoner.reason("磁盘满了怎么办？")
print(response.text)
```

API key 通过环境变量注入：`export GCODE_REASONER_API_KEY="sk-xxx"`

### report — 报告生成

聚合 monitor/alert/logpipe 数据，生成 daily/weekly/incident 报告。

### mcp — MCP Server（dp1 执行层）

12 个运维 Tool，三级风险标签：

| 分类 | Tool | 参数 | 风险 | 说明 |
|------|------|------|------|------|
| 只读 | `sys_info` | — | read_only | 内核版本、主机名、架构、麒麟版本 |
| 只读 | `ps_list` | — | read_only | 进程列表 |
| 只读 | `df_h` | — | read_only | 磁盘使用 |
| 只读 | `netstat` | — | read_only | 网络连接（ss -tulnp） |
| 只读 | `journalctl` | service, lines | read_only | systemd 日志 |
| 指标 | `cpu_usage` | — | read_only | CPU 使用率（总体+每核） |
| 指标 | `mem_usage` | — | read_only | 内存 + Swap |
| 指标 | `io_stat` | — | read_only | 磁盘 IO |
| 指标 | `disk_health` | path | read_only | 磁盘使用率 + 预警（>85%） |
| 管理 | `service_status` | service_name | read_only | 服务状态查看 |
| 管理 | `service_restart` | service_name | read_write | 重启服务（需用户确认） |
| 管理 | `pkg_install` | package_name | admin | 安装 RPM 包（需用户确认） |

管理类 Tool 安全措施：参数注入防御、dry-run 确认、30s 超时限制。

## 高级用法（命令行参考）

日常不需要记这些。用自然语言就够了。子命令给脚本、自动化、高级用户用的。

### 运维检查

```bash
gcode check                                  # 健康检查（磁盘/内存/TCP）
gcode report --type daily                    # 日报
gcode report --type weekly -o weekly.md      # 周报
gcode report --type incident                 # 故障报告
```

### Runbook 执行

```bash
gcode run runbook.yaml                       # 执行
gcode run runbook.yaml --dry-run             # 预览不执行
```

### 告警管理

```bash
gcode alert list                             # 活跃告警
gcode alert ack <alert-id>                   # 确认
gcode alert resolve <alert-id>               # 解决
gcode alert-config add-rule --name cpu-high --condition "cpu>90"
gcode alert-config list-rules
gcode alert-config events --active
```

### 日志管道

```bash
gcode logpipe entries --level ERROR --keyword oom
gcode logpipe stats                          # 日志统计
gcode logpipe anomalies --threshold 10       # 异常检测
gcode logpipe add-source --name syslog --type file --path /var/log/syslog
gcode logpipe scan --limit 500               # 规则扫描
```

## API 接口

### 1. Unix Socket API（生产环境）

**请求格式**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 自然语言运维查询 |
| user_id | string | 否 | 用户标识（审计用） |
| session_id | string | 否 | 会话 ID，复用保持上下文 |

**响应**：

```json
{"status": "success", "data": {...}, "audit_id": "audit-xxx"}
{"status": "rejected", "reason": "Intent classified as unsafe", "detail": "unsafe_file_delete"}
{"status": "needs_review", "reason": "Query requires human review"}
```

**处理流程**：

```
客户端 → Unix Socket → IntentClassifier (Qwen2.5)
  → [safe]           → 转发 dp1 MCP Server → AuditLogger 记录 → 返回结果
  → [unsafe]         → 拒绝 + 审计记录
  → [needs-review]   → 暂存待人工审核
```

### 2. MCP 协议（stdio 模式）

```bash
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python -m gcode.mcp.server
```

### 3. Python API

```python
from gcode.core.session import SessionManager
s = SessionManager()
print(s.ask("CPU 使用率如何？"))

from gcode.reasoning.reasoner import Reasoner
from gcode.reasoning.providers.openai_compat import create_deepseek_provider
provider = create_deepseek_provider(api_key="sk-...")
reasoner = Reasoner(provider)
response = await reasoner.reason("磁盘满了怎么办？")
```

## 配置参考

`/etc/gcode/config.yaml`（部署）或 `config.yaml`（开发）：

```yaml
reasoner:
  provider: deepseek          # ollama | deepseek | qwen | claude
  model: deepseek-chat

intent:
  model: Qwen/Qwen2.5-0.5B
  safe_threshold: 0.6

monitor:
  checks:
    - type: disk
      name: "root-usage"
      threshold: 85
  interval_sec: 60

alert:
  notifiers:
    - type: webhook
      url: "https://hooks.example.com/alert"
  rules:
    - name: cpu-high
      condition: "cpu > 90"
      severity: error

logpipe:
  sources:
    - name: syslog
      type: file
      path: /var/log/messages
```
## 系统要求

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.11+ | venv 隔离安装 |
| 操作系统 | 麒麟OS / CentOS 8+ / Ubuntu 22.04+ | systemd + SELinux 支持 |
| 内存 | 2 GB | 含 Qwen2.5-0.5B (约 1GB) |
| 磁盘 | 2 GB | 代码 + 模型 + SQLite |
| 可选 | psutil, auditd, podman | 性能采集、系统审计、容器沙箱 |

系统依赖：

```bash
# 麒麟OS / CentOS
sudo dnf install -y python3-pip python3-venv git socat audit

# Ubuntu
sudo apt-get install -y python3-pip python3-venv git socat auditd
```

## 启动与管理

```bash
# 开发调试
gcode                          # 交互式 REPL
gcode "磁盘使用情况"             # 单次查询

# systemd 生产模式
sudo systemctl start gcode-security-guard gcode-mcp-server
sudo systemctl enable --now gcode-security-guard gcode-mcp-server

# 管理
sudo systemctl status gcode-security-guard gcode-mcp-server
sudo journalctl -u gcode-security-guard -f
sudo journalctl -u gcode-mcp-server -f
sudo systemctl restart gcode-security-guard gcode-mcp-server
```

## 测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
# 56 tests passed
```

## 项目结构

```
gcode-security-guard/
├── src/
│   ├── api/server.py                    # m1: Unix Socket 接入层
│   ├── intent/                          # m1: 意图过滤器
│   │   ├── classifier.py               #     Qwen2.5-0.5B 分类
│   │   └── model.py                    #     13标签零样本模型
│   ├── audit/                           # m1: 审计系统
│   │   ├── logger.py                   #     SQLite 全量记录
│   │   └── models.py                   #     审计数据模型
│   ├── contracts/types.py               # m1↔dp1 接口契约
│   └── gcode/
│       ├── cli/main.py                  # Click CLI 入口
│       ├── core/                        # 核心框架
│       │   ├── config.py                # YAML 配置 + 默认值
│       │   ├── engine.py                # Runbook 执行引擎
│       │   └── session.py               # 会话管理 + 推理路由
│       ├── reasoning/                   # LLM 推理层（多 Provider）
│       │   ├── types.py                 # ToolDef, ReasonerRequest/Response
│       │   ├── base.py                  # LLMProvider Protocol
│       │   ├── tool_registry.py         # 12 Tool 静态注册
│       │   ├── reasoner.py              # 编排器（LLM ↔ Tool 循环）
│       │   └── providers/
│       │       ├── openai_compat.py     # Qwen / DeepSeek / Ollama
│       │       └── anthropic.py         # Claude (Anthropic SDK)
│       ├── mcp/                         # dp1: MCP Server + 执行层
│       │   ├── server.py                # FastMCP 入口
│       │   ├── executor.py              # 命令执行器 + 安全门禁
│       │   ├── sandbox.py               # seccomp + 资源限制
│       │   ├── tools_readonly.py        # 5 个只读 Tool
│       │   ├── tools_metrics.py         # 4 个指标 Tool
│       │   └── tools_management.py      # 3 个管理 Tool
│       ├── monitor/                     # dp1: 监控采集
│       │   ├── checkers.py              # HTTP/TCP/进程/磁盘/内存
│       │   ├── evaluator.py             # 检查套件聚合
│       │   └── collector.py             # CPU/内存/磁盘指标
│       ├── alert/                       # dp1: 告警引擎
│       │   ├── engine.py                # Alert 生命周期
│       │   ├── manager.py               # 规则匹配 + 去重
│       │   └── notifier.py              # stdout/webhook
│       ├── logpipe/                     # dp1: 日志管道
│       │   ├── engine.py                # JSONL 采集 + 异常检测
│       │   ├── pipeline.py              # SQLite 管道 + 规则
│       │   ├── detectors.py             # 正则 + 级别分类
│       │   └── sources.py               # FileSource 适配器
│       └── report/reporter.py           # 日报/周报/故障报告
├── tests/
├── deploy/
│   ├── install.sh                       # 一键部署脚本
│   ├── gcode-security-guard.service     # systemd: 安全层
│   ├── gcode-mcp-server.service         # systemd: 执行层
│   ├── gcode-selinux.te                 # SELinux 策略模块
│   ├── .env.example                     # 环境变量模板
│   └── README.md                        # 部署文档
├── config.yaml                          # 默认配置
├── pyproject.toml                       # 依赖 + 构建配置
└── README.md                            # 本文档
```

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| CLI 无响应 | Ollama 未运行 | `ollama list` 确认模型已加载 |
| LLM 不调用 Tool | 模型不支持 function calling | 用 qwen2.5:7b+ / deepseek-chat / Claude |
| Socket 连接拒绝 | 目录不存在或权限不足 | `sudo mkdir -p /run/gcode && sudo chmod 770 /run/gcode` |
| 意图分类全 needs-review | 阈值过高 | 降低 `safe_threshold` 到 0.4 |
| 模型下载失败 | HuggingFace 不可达 | `export HF_ENDPOINT=https://hf-mirror.com` |
| `ModuleNotFoundError: gcode` | 未安装为 editable | `pip install -e .` |
| SELinux 阻止 socket 创建 | AVC denial | `sudo semodule -i deploy/gcode-selinux.pp` |

## 配对仓库

- [gcode-security-guard](https://github.com/yGGGgGGGy/gcode-security-guard) — 安全层 + 执行层（**本项目**）
- [gcode-mcp-server](https://github.com/yGGGgGGGy/gcode-mcp-server) — 执行层独立部署（dp1）

## License

AGPL-3.0
