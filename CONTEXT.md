# Gcode 项目上下文

## 目标

麒麟OS智能运维Agent。MCP协议打通大模型与OS，实现对话式运维。

## 安全护栏（三层）

1. **意图过滤（入口）** — m1: Qwen2.5-0.5B 多标签分类，safe/unsafe/needs-review
2. **最小权限（出口）** — dp1: 执行层约束，read_only/read_write/admin
3. **思维链审计（全链路）** — m1: SQLite 全量记录，事后审计

## 架构（四层）

```
接入层(api/) → 推理层(intent/) → 执行层(dp1 MCP Server) → 审计层(audit/)
    Unix Domain Socket: /run/gcode/gcode.sock (m1) ↔ /run/gcode/gcode-dp1.sock (dp1)
    不同用户运行，SO_PEERCRED鉴权
```

## 技术栈

| 组件 | 技术 |
|------|------|
| API框架 | FastMCP (dp1) / Raw Unix Socket (m1) |
| 意图分类 | Qwen2.5-0.5B + HuggingFace Transformers |
| 审计存储 | SQLite |
| 模型推理 | PyTorch CPU (可替换CTranslate2/ONNX) |
| 容器化 | podman |
| OS适配 | 麒麟OS: SELinux策略、rpm/systemd、auditd |

## 目录结构

```
m1/                          dp1/
├── src/                     ├── src/
│   ├── api/server.py        │   ├── server.py (MCP Server)
│   ├── intent/              │   ├── tools/ (Tool实现)
│   │   ├── classifier.py    │   ├── executor/ (执行层)
│   │   └── model.py         │   └── sandbox/ (podman隔离)
│   └── audit/               │
│       ├── logger.py        │
│       └── models.py        │
├── schema/                  ├── schema/
│   └── gcode-protocol.json  │   └── (接口契约引用)
├── tests/                   ├── tests/
├── CONTEXT.md               ├── CONTEXT.md
└── README.md                └── README.md
```

## ADR

参见 `docs/adr/`。

### ADR-001: 选择 Unix Domain Socket 而非 REST/gRPC

**Why**: 同一主机多用户进程间通信，不需要网络栈开销。SO_PEERCRED 提供内核对端UID/GID校验，天然安全。
