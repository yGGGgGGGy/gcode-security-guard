# Gcode Security Guard (m1)

麒麟OS智能运维Agent — **安全层**。负责意图过滤（入口）和全链路审计（出口）。

## 架构角色

```
User → 接入层(API) → 推理层(Intent Filter) → 执行层(dp1) → 审计层(Audit)
        ↑ m1负责        ↑ m1核心            ↑ dp1负责    ↑ m1负责
```

## 功能

- **意图过滤**: Qwen2.5-0.5B 多标签零样本分类，三层判定（safe/unsafe/needs-review）
- **审计系统**: SQLite 全量记录，思维链追踪，按用户/会话检索
- **转发中间件**: Unix Domain Socket 与 dp1 MCP Server 通信

## 接口契约

参见 [schema/gcode-protocol.json](./schema/gcode-protocol.json) — m1↔dp1 完整协议定义。

## 快速开始

```bash
pip install -e .
python -m src.api.server
```

Unix Domain Socket 监听 `/run/gcode/gcode.sock`，转发给 `/run/gcode/gcode-dp1.sock`（dp1）。

## 配对仓库

- [gcode-mcp-server](https://github.com/yGGGgGGGy/gcode-mcp-server) — MCP Server + Tool实现 + 执行层约束 (dp1)
