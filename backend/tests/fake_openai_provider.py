from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _response(summary: str, *, include_usage: bool = True) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "fake-response",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps({"summary": summary})}],
            }
        ],
        "output_text": json.dumps({"summary": summary}),
    }
    if include_usage:
        body["usage"] = {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}
    return body


class FakeOpenAIProviderHandler(BaseHTTPRequestHandler):
    server_version = "SignalDeckFakeOpenAI/1.0"

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("content-length") or "0")
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": {"message": "invalid json"}})
            return

        if self.path.endswith("/responses"):
            self._handle_responses(payload)
            return
        if self.path.endswith("/chat/completions"):
            self._handle_chat_completions(payload)
            return
        self._send_json(404, {"error": {"message": "unsupported fake provider route"}})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _handle_responses(self, payload: dict[str, Any]) -> None:
        model = str(payload.get("model") or "")
        if "tools-disabled" in model and payload.get("tools"):
            self._send_json(400, {"error": {"message": "tool calls are unsupported"}})
            return
        if "reasoning-disabled" in model and "reasoning" in payload:
            self._send_json(400, {"error": {"message": "reasoning is unsupported"}})
            return
        if "json-object-only" in model:
            text_format = payload.get("text", {}).get("format", {})
            if text_format.get("type") == "json_schema":
                self._send_json(400, {"error": {"message": "json_schema is unsupported"}})
                return
            self._send_json(200, _response("fake json object fallback"))
            return
        if "missing-usage" in model:
            self._send_json(200, _response("fake missing usage", include_usage=False))
            return
        self._send_json(200, _response("fake strict schema"))

    def _handle_chat_completions(self, payload: dict[str, Any]) -> None:
        model = str(payload.get("model") or "")
        if "tools-disabled" in model and payload.get("tools"):
            self._send_json(400, {"error": {"message": "tool calls are unsupported"}})
            return
        if "reasoning-disabled" in model and "reasoning_effort" in payload:
            self._send_json(400, {"error": {"message": "reasoning_effort is unsupported"}})
            return
        include_usage = "missing-usage" not in model
        body: dict[str, Any] = {
            "id": "fake-chat-completion",
            "choices": [{"message": {"content": json.dumps({"summary": "fake chat output"})}}],
        }
        if include_usage:
            body["usage"] = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
        self._send_json(200, body)

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="18081")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, int(args.port)), FakeOpenAIProviderHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
