"""Unix Domain Socket 服务器 — 接入层 + 推理层入口。

架构:
  用户请求 → Unix Socket → api/server.py
    → intent/classifier.py (意图过滤)
      → [safe] → 转发给dp1 MCP Server (Unix Socket client)
      → [unsafe] → 拒绝
      → [needs-review] → 拒绝，建议人工审核
    → audit/logger.py (全量记录)
"""

from __future__ import annotations

import json
import os
import socket
import uuid
from typing import Any

from ..audit.logger import AuditLogger
from ..intent.classifier import IntentClassifier

SOCKET_PATH = "/run/gcode/gcode.sock"
DP1_SOCKET_PATH = "/run/gcode/gcode-dp1.sock"


class GcodeServer:
    """Gcode安全守卫服务器。

    监听Unix Domain Socket，接收用户请求，执行意图过滤后转发给dp1执行层。
    """

    def __init__(
        self,
        socket_path: str = SOCKET_PATH,
        dp1_socket_path: str = DP1_SOCKET_PATH,
    ):
        self._socket_path = socket_path
        self._dp1_socket_path = dp1_socket_path
        self._classifier = IntentClassifier()
        self._audit = AuditLogger()
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

            # Step 3: safe — 转发给dp1
            self._audit.trace_event(record, "Forwarding to dp1 MCP Server")
            result = self._forward_to_dp1(request, classification)

            self._send_json(conn, {
                "status": "success",
                "data": result,
            })

    def _forward_to_dp1(self, request: dict, classification: Any) -> dict:
        """转发请求给dp1 MCP Server。"""
        try:
            dp1_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            dp1_sock.settimeout(30)
            dp1_sock.connect(self._dp1_socket_path)

            payload = {
                "request_id": request.get("request_id", str(uuid.uuid4())),
                "tool_name": request.get("tool_name", ""),
                "parameters": request.get("parameters", {}),
                "user_id": request.get("user_id", ""),
                "session_id": request.get("session_id", ""),
                "permission_level": self._map_permission(classification),
            }
            dp1_sock.sendall(json.dumps(payload).encode() + b"\n")

            raw = dp1_sock.recv(65536)
            dp1_sock.close()
            return json.loads(raw)
        except FileNotFoundError:
            return {"error": "MCP Server (dp1) not available", "status": "error"}
        except Exception as e:
            return {"error": str(e), "status": "error"}

    @staticmethod
    def _map_permission(classification: Any) -> str:
        categories = classification.categories
        if any("write" in c or "delete" in c or "modify" in c or "kill" in c for c in categories):
            return "read_write"
        return "read_only"

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
