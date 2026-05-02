# Gcode Security Guard — 麒麟OS 智能运维 Agent

**对话式运维，杜绝误操作。** 通过自然语言查询系统状态、排查故障、执行运维操作。

三层安全护栏：意图过滤 → 最小权限 → 全链路审计。

## 环境要求

| 项 | 最低要求 | 推荐 |
|---|---------|------|
| 操作系统 | 麒麟OS / Linux 4.19+ | 麒麟OS V10 SP2+ |
| Python | 3.11+ | 3.12 |
| 内存 | 4 GB | 8 GB（含本地模型） |
| 磁盘 | 2 GB | 10 GB（含审计数据） |
| 可选 | podman | 用于沙箱隔离 |

## 快速开始（新手向）

如果你只想要跑起来，3 步：

```bash
# 1. 安装依赖
pip install -e "gcode-security-guard[reasoner-openai]"

# 2. 确保 Ollama 在运行（本地模型，无需 API key）
ollama pull qwen2.5:7b   # 首次需下载，约 4GB

# 3. 启动 CLI 对话
gcode ask "查看系统内存使用情况"
```

如果 Ollama 不可用，用云端模型：

```bash
export GCODE_REASONER_API_KEY="你的API密钥"
# 编辑 config.yaml，把 reasoner.provider 改为 deepseek 或 qwen
gcode ask "查看 CPU 使用率"
```

预期输出：LLM 自动调用 `mem_usage` 或 `cpu_usage` tool，返回 JSON 格式的指标数据。

## 一键部署（systemd）

```bash
git clone https://github.com/yGGGgGGGy/gcode-security-guard.git
cd gcode-security-guard
sudo bash deploy/setup.sh
sudo systemctl start gcode-security-guard gcode-mcp-server
sudo systemctl enable gcode-security-guard gcode-mcp-server
```

部署完成后，通过 Unix Socket 访问：

```bash
echo '{"query":"查看内存","user_id":"admin","session_id":"test-001"}' \
  | nc -U /run/gcode/gcode.sock
```

## 架构详解

```
用户输入（自然语言 / CLI / Socket）
          │
          ▼
┌─────────────────────────────────────────────────┐
│                  Gcode Security Guard (m1)       │
│                                                  │
│  ① 意图过滤层 (intent/)                          │
│     └ Qwen2.5-0.5B 零样本分类                      │
│       13 标签判定：safe / unsafe / needs-review       │
│                                                  │
│  ② 推理层 (gcode/reasoning/)                     │
│     └ 多模型 LLM 路由                              │
│       ├ ollama → 本地 qwen2.5:7b                  │
│       ├ deepseek → DeepSeek API                   │
│       ├ qwen → Qwen API（阿里云）                   │
│       └ claude → Anthropic Claude API             │
│     └ Tool Calling：自动选择 12 个运维 Tool          │
│                                                  │
│  ③ 审计层 (audit/)                               │
│     └ SQLite 全量记录                             │
│       每次操作：谁、什么时候、做了什么、结果如何         │
└────────────────────┬────────────────────────────┘
                     │ Unix Domain Socket
                     │ SessionContext {risk_score, capability_set, ...}
                     ▼
┌─────────────────────────────────────────────────┐
│                  Gcode MCP Server (dp1)          │
│                                                  │
│  ④ Tool 执行层 (gcode/mcp/)                      │
│     ├ 只读工具 (5): sys_info, ps, df, net, log   │
│     ├ 指标工具 (4): cpu, mem, io, disk           │
│     └ 管理工具 (3): svc_status/restart, pkg       │
│                                                  │
│  ⑤ 执行沙箱 (executor + sandbox)                  │
│     └ seccomp 白名单                             │
│     └ 资源限制（CPU 30s / 内存 512MB）              │
│     └ 高危命令正则拦截                              │
│     └ 敏感路径告警                                 │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
              麒麟OS（systemd / rpm / journalctl / ...）
```

### 数据流

1. 用户输入 → 意图分类器判定 safe/unsafe/needs-review
2. safe → 推理层根据 tool 描述选择合适 tool
3. LLM 返回 tool_call → executor 执行（含安全门禁）
4. 结果回传 → LLM 汇总成自然语言回答
5. 全链路审计写入 SQLite

## 项目结构

```
src/
├── contracts/types.py           # m1↔dp1 接口契约
├── intent/                      # 意图过滤（Qwen2.5-0.5B 零样本）
│   ├── classifier.py
│   └── model.py
├── audit/                       # 审计系统（SQLite）
│   ├── logger.py
│   └── models.py
├── api/server.py                # Unix Socket 接入层
└── gcode/
    ├── cli/main.py              # CLI 入口（Click）
    ├── core/                    # 核心
    │   ├── config.py            # 配置系统（YAML + 环境变量）
    │   ├── engine.py            # Runbook 引擎
    │   └── session.py           # 会话管理 + 推理路由
    ├── reasoning/               # 多模型推理层 ★NEW
    │   ├── types.py             # ToolDef, ReasonerRequest/Response
    │   ├── base.py              # LLMProvider Protocol
    │   ├── tool_registry.py     # 12 个 Tool 静态定义
    │   ├── reasoner.py          # 编排器（LLM → Tool → 返回）
    │   └── providers/
    │       ├── openai_compat.py # Qwen / DeepSeek / Ollama
    │       └── anthropic.py     # Claude
    ├── mcp/                     # MCP Server + 执行层
    │   ├── server.py            # FastMCP 入口
    │   ├── executor.py          # 命令执行器 + 安全门禁
    │   ├── sandbox.py           # seccomp + 资源限制
    │   ├── tools_readonly.py    # 5 个只读 Tool
    │   ├── tools_metrics.py     # 4 个指标 Tool
    │   └── tools_management.py  # 3 个管理 Tool
    ├── monitor/                 # 健康检查
    ├── alert/                   # 告警引擎
    ├── logpipe/                 # 日志管道
    └── report/                  # 报告生成
```

## 配置

### 推理层（多模型切换）

编辑 `config.yaml`：

```yaml
reasoner:
  provider: ollama           # ollama | qwen | deepseek | claude
  model: qwen2.5:7b          # 模型名
  api_key: ""                # 留空，用 GCODE_REASONER_API_KEY 环境变量
  max_tool_rounds: 3         # LLM 调用轮次上限
  timeout: 30                # HTTP 超时（秒）
```

API key 通过环境变量注入（不入 YAML）：

```bash
export GCODE_REASONER_API_KEY="sk-xxx"    # DeepSeek / Qwen
export GCODE_REASONER_API_KEY="sk-ant-xxx"  # Claude
```

### 意图分类

```yaml
intent:
  model: Qwen/Qwen2.5-0.5B
  safe_threshold: 0.6
  needs_review_threshold: 0.4
```

### 监控 / 告警 / 日志

```yaml
monitor:
  checks:
    - type: http
      url: http://localhost:8080/health
    - type: disk
      path: /
      warn_pct: 80
      crit_pct: 95

alert:
  rules:
    - name: svc-down
      monitor: http
      condition: fail
      cooldown_min: 2

logpipe:
  sources:
    - name: syslog
      type: file
      path: /var/log/syslog
```

## MCP Tool 完整列表

| 类别 | Tool | 参数 | 风险 | 说明 |
|------|------|------|------|------|
| 只读 | `sys_info` | — | read_only | 内核版本、主机名、架构 |
| 只读 | `ps_list` | — | read_only | 进程列表 |
| 只读 | `df_h` | — | read_only | 磁盘使用 |
| 只读 | `netstat` | — | read_only | 网络连接（ss） |
| 只读 | `journalctl` | service, lines | read_only | 系统日志 |
| 指标 | `cpu_usage` | — | read_only | CPU 使用率 |
| 指标 | `mem_usage` | — | read_only | 内存 + Swap |
| 指标 | `io_stat` | — | read_only | 磁盘 IO |
| 指标 | `disk_health` | path | read_only | 磁盘健康检查 |
| 管理 | `service_status` | service_name | medium | 服务状态查看 |
| 管理 | `service_restart` | service_name | admin | 重启服务（需确认） |
| 管理 | `pkg_install` | package_name | admin | 安装 RPM（需确认） |

## CLI 命令

```bash
gcode serve                  # 交互式 REPL
gcode ask "nginx 状态？"      # 单次查询（LLM 推理）
gcode run ./runbooks/restart-nginx.yaml        # Runbook 执行
gcode run ./runbooks/restart-nginx.yaml --dry-run
gcode report --type daily                       # 日报
gcode check                                     # 健康检查
```

## 安全模型

| 层 | 位置 | 机制 | 拦截什么 |
|----|------|------|---------|
| ① 意图过滤 | `intent/classifier.py` | Qwen2.5-0.5B 多标签分类 | rm -rf, mkfs, chmod 777 等 |
| ② 最小权限 | `mcp/executor.py` | 正则拦截 + dry-run + 确认门禁 | 敏感路径写入、非法字符注入 |
| ③ 执行沙箱 | `mcp/sandbox.py` | seccomp + rlimit | 非白名单 syscall、资源滥用 |
| ④ 思维链审计 | `audit/logger.py` | SQLite 全量 | 事后回溯所有操作 |

## 依赖

```bash
# 核心依赖（必需）
pip install -e .

# 云端 LLM（qwen / deepseek / claude）
pip install "gcode-security-guard[reasoner-openai]"

# 或全部推理后端
pip install "gcode-security-guard[reasoner]"

# 开发
pip install "gcode-security-guard[dev]"
```

## 故障排查

| 问题 | 检查 |
|------|------|
| CLI 无响应 | Ollama 是否运行？`ollama list` |
| LLM 不调 tool | 模型是否支持 function calling？qwen2.5:7b+ / deepseek-chat 均支持 |
| Socket 连接拒绝 | `sudo mkdir -p /run/gcode && sudo chmod 777 /run/gcode` |
| 意图分类全 needs-review | 降低 `safe_threshold` 到 0.4 |

## 配对仓库

- [Gcode（主 repo）](https://github.com/yGGGgGGGy/Gcode) — 完整部署 + submodule + systemd
- [gcode-mcp-server](https://github.com/yGGGgGGGy/gcode-mcp-server) — 执行层（dp1）

## License

AGPL-3.0
