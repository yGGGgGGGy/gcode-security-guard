"""Unix Domain Socket 服务器 — 接入层 + 推理层入口。

架构:
  用户请求 → Unix Socket → api/server.py
    → intent/classifier.py (意图过滤)
      → [safe] → 推理层（LLM 选择 Tool → 执行）
      → [unsafe] → 拒绝
      → [needs-review] → 拒绝，建议人工审核
    → audit/logger.py (全量记录)
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import uuid
from typing import Any

from ..audit.logger import AuditLogger
from ..intent.classifier import IntentClassifier
from ..contracts.types import SessionContext, ToolCallRecord
from ..gcode.core.config import GcodeConfig, load_config

SOCKET_PATH = "/run/gcode/gcode.sock"
DP1_SOCKET_PATH = "/run/gcode/gcode-dp1.sock"


class GcodeServer:
    """Gcode安全守卫服务器。

    监听Unix Domain Socket，接收用户请求，执行意图过滤后通过推理层执行。
    """

    def __init__(
        self,
        socket_path: str = SOCKET_PATH,
        dp1_socket_path: str = DP1_SOCKET_PATH,
        config: GcodeConfig | None = None,
    ):
        self._socket_path = socket_path
        self._dp1_socket_path = dp1_socket_path
        self._classifier = IntentClassifier()
        self._audit = AuditLogger()
        self._config = config or load_config()
        self._sock: socket.socket | None = None

    def start(self) -> None:
        """启动服务器。"""
        self._classifier.load()

        # 确保socket目录存在
        os.makedirs(os.path.dirname(self._socket_path), exist_ok=True)

        # 清理旧socket
        try:
            os.unlink(self._socket_path)
        except OSError:
            pass

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self._socket_path)
        os.chmod(self._socket_path, 0o660)
        self._sock.listen(5)

        print(f"Gcode Security Guard listening on {self._socket_path}")

        try:
            self._accept_loop()
        finally:
            self.shutdown()

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while True:
            conn, _ = self._sock.accept()
            try:
                self._handle(conn)
            except Exception as e:
                print(f"Handler error: {e}")
            finally:
                conn.close()

    def _handle(self, conn: socket.SocketType) -> None:
        """处理单条请求: 意图过滤 → 转发执行 → 审计记录。"""
        raw = conn.recv(65536)
        if not raw:
            return

        request = json.loads(raw)
        session_id = request.get("session_id", str(uuid.uuid4()))
        user_id = request.get("user_id", "unknown")
        query = request.get("query", "")

        # Step 1: 意图分类
        classification = self._classifier.classify(query)
        record = self._audit.create_record(
            user_id=user_id,
            session_id=session_id,
            original_query=query,
            intent_result=classification.intent,
            intent_confidence=classification.confidence,
            intent_categories=classification.categories,
        )
        self._audit.trace_event(record, f"Intent: {classification.intent} ({classification.top_label}, {classification.confidence:.2f})")

        with self._audit.trace(record):
            # Step 2: 安全决策
            if classification.intent == "unsafe":
                self._audit.finalize(
                    record,
                    tools_called=[],
                    request_ids=[],
                    results_summary="Rejected by intent filter",
                    final_status="rejected_by_intent",
                    duration_total_ms=0,
                )
                self._send_json(conn, {
                    "status": "rejected",
                    "reason": "Intent classified as unsafe",
                    "detail": classification.top_label,
                })
                return

            if classification.intent == "needs-review":
                self._audit.finalize(
                    record,
                    tools_called=[],
                    request_ids=[],
                    results_summary="Needs human review",
                    final_status="rejected_by_intent",
                    duration_total_ms=0,
                )
                self._send_json(conn, {
                    "status": "needs_review",
                    "reason": "Query requires human review",
                    "detail": classification.top_label,
                })
                return

            # Step 3: safe — 通过推理层执行
            ctx = self._build_session_context(request, classification)
            self._audit.trace_event(record, f"Reasoning with context: {ctx.to_dict()}")

            response_text, tool_records = asyncio.run(
                self._reason(ctx)
            )

            tools_called = [r.tool_name for r in tool_records]
            request_ids = [r.audit_id for r in tool_records]

            self._audit.finalize(
                record,
                tools_called=tools_called,
                request_ids=request_ids,
                results_summary=response_text[:500],
                final_status="success",
                duration_total_ms=record.duration_total_ms,
            )

            self._send_json(conn, {
                "status": "success",
                "data": {"response": response_text},
                "audit_id": record.audit_id,
            })

    def _build_session_context(self, request: dict, classification: Any) -> SessionContext:
        """从意图分类结果构建 dp1 所需的 SessionContext。"""
        session_id = request.get("session_id", str(uuid.uuid4()))
        user_id = request.get("user_id", "unknown")
        query = request.get("query", "")

        return SessionContext(
            session_id=session_id,
            filtered_input=query,
            risk_score=1.0 - classification.confidence,
            risk_verdict=classification.intent,
            capability_set=classification.categories,
            reason=f"Intent: {classification.top_label} (conf={classification.confidence:.2f})",
            user_id=user_id,
        )

    async def _reason(self, ctx: SessionContext) -> tuple[str, list[ToolCallRecord]]:
        """通过推理层执行：LLM 选择 Tool → 执行 → 返回结果。"""
        from ..gcode.reasoning import create_reasoner

        reasoner = create_reasoner(self._config)
        response = await reasoner.reason(ctx.filtered_input, allow_write=False)

        # 构建 ToolCallRecord 供审计
        records: list[ToolCallRecord] = []
        for tr in response.tool_results:
            records.append(ToolCallRecord(
                session_id=ctx.session_id,
                tool_name=tr["tool"],
                params={},
                result={"output": tr["result"][:200]},
            ))

        result_text = response.text or ""
        if response.tool_calls:
            tool_outputs = []
            for tr in response.tool_results:
                tool_outputs.append(f"[{tr['tool']}]\n{tr['result']}")
            if tool_outputs:
                result_text = (result_text + "\n\n" if result_text else "") + "\n\n".join(tool_outputs)

        return result_text or "[reasoner] 无响应", records

    def _forward_to_dp1(self, ctx: SessionContext, tool_name: str, params: dict) -> tuple[dict, list[ToolCallRecord]]:
        """转发请求给dp1 MCP Server（保留作为回退）。"""
        try:
            dp1_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            dp1_sock.settimeout(30)
            dp1_sock.connect(self._dp1_socket_path)

            dp1_sock.sendall(json.dumps(ctx.to_dict()).encode() + b"\n")

            raw = dp1_sock.recv(65536)
            dp1_sock.close()
            response_data = json.loads(raw)

            records = self._extract_tool_records(response_data, ctx.session_id)
            return response_data, records
        except FileNotFoundError:
            return {"error": "MCP Server (dp1) not available", "status": "error"}, []
        except Exception as e:
            return {"error": str(e), "status": "error"}, []

    @staticmethod
    def _extract_tool_records(response: dict, session_id: str) -> list[ToolCallRecord]:
        """从dp1响应中提取ToolCallRecord列表。"""
        raw_records = response.get("tool_calls", [])
        if isinstance(raw_records, list):
            return [ToolCallRecord.from_dict(r) for r in raw_records]
        return []

    @staticmethod
    def _send_json(conn: socket.SocketType, data: dict) -> None:
        conn.sendall(json.dumps(data, ensure_ascii=False).encode() + b"\n")

    def shutdown(self) -> None:
        self._classifier.unload()
        if self._sock:
            self._sock.close()
        try:
            os.unlink(self._socket_path)
        except OSError:
            pass
        print("Gcode Security Guard stopped")


def main() -> None:
    server = GcodeServer()
    server.start()


if __name__ == "__main__":
    main()
