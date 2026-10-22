"""A tiny stand in for the Claude API and an OpenAI compatible server (e.g. Ollama).

It answers every request with JSON that fits the requested schema and records the
requests, so tests can check both the request format and the pipeline behaviour.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PRODUCT_HTML = """<html><head><title>Cloud Cream | Shop</title>
<meta property="og:title" content="Cloud Cream 50ml">
<meta name="description" content="Weightless hydration for every skin type.">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
"name":"Cloud Cream","description":"72h moisture with ceramides","brand":{"name":"Soft"}}
</script></head><body><h1>Cloud Cream</h1><p>Absorbs in seconds.</p>
<script>var tracking = 1;</script></body></html>"""


def answer(schema: dict[str, Any], texts: list[str], images: int) -> dict[str, Any]:
    props = schema.get("properties", {})
    joined = "\n".join(texts)
    if "english" in props:
        return {"english": "hydrating cream"}
    if "color" in props:
        return {"color": "red" if images else "unknown"}
    if "features" in props:
        return {
            "name": "cloud cream",
            "category": "skincare",
            "features": ["Weightless hydration", "Absorbs in seconds", "72h moisture"],
            "emojis": ["🤍", "✨", "☁️"],
            "hashtags": ["#cloudcream", "skincare"],
            "audience": "dry skin",
            "idea": "calm clean girl video, show the result first",
        }
    if "shots" in props:
        ids = re.findall(r"Shot (c\d+s\d+)", joined)
        return {
            "shots": [
                {
                    "id": i,
                    "description": f"hands apply cream ({i})",
                    "shot_type": "hands_demo" if n % 2 else "product_closeup",
                    "feature": "Absorbs in seconds" if n % 2 else None,
                    "appeal": 9 - n % 5,
                    "problem": None,
                }
                for n, i in enumerate(ids)
            ]
        }
    if "variants" in props:
        ids = re.findall(r"^(c\d+s\d+) \|", joined, re.M)
        wanted = re.findall(r"^\* (hook|story|vibe):", joined, re.M)
        return {
            "variants": [
                {
                    "strategy": key,
                    "hook": f"POV: fake {key} hook 🤍",
                    "caption": f"{key} caption",
                    "shots": [
                        {"id": i, "text": None if n % 2 == 0 else f"Feature {n} ✨"}
                        for n, i in enumerate(ids[k % 2 :])
                    ]
                    + [{"id": "zz9", "text": "x"}],
                }
                for k, key in enumerate(wanted)
            ]
        }
    return {}


class FakeAi:
    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.requests: list[dict[str, Any]] = []
        self.fail_json_schema = False
        self.down = False
        handler = self._handler()
        self.server = ThreadingHTTPServer((host, port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self) -> "FakeAi":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                pass

            def _send(self, code: int, body: Any, ctype: str = "application/json") -> None:
                data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                if self.path.startswith("/product"):
                    self._send(200, PRODUCT_HTML, "text/html; charset=utf-8")
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                fake.requests.append(
                    {
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": body,
                    }
                )
                if fake.down:
                    self._send(503, {"error": "down"})
                elif self.path.split("?")[0].endswith("/v1/messages"):
                    self._anthropic(body)
                elif self.path.split("?")[0].endswith("/chat/completions"):
                    self._openai(body)
                else:
                    self._send(404, {"error": "unknown"})

            def _anthropic(self, body: dict[str, Any]) -> None:
                content = body["messages"][0]["content"]
                texts = [c["text"] for c in content if c["type"] == "text"]
                images = sum(1 for c in content if c["type"] == "image")
                schema = body["output_config"]["format"]["schema"]
                self._send(
                    200,
                    {
                        "id": "msg_fake",
                        "type": "message",
                        "role": "assistant",
                        "model": body["model"],
                        "stop_reason": "end_turn",
                        "stop_sequence": None,
                        "content": [
                            {"type": "text", "text": json.dumps(answer(schema, texts, images))}
                        ],
                        "usage": {"input_tokens": 10, "output_tokens": 10},
                    },
                )

            def _openai(self, body: dict[str, Any]) -> None:
                fmt = body.get("response_format", {})
                if fake.fail_json_schema and fmt.get("type") == "json_schema":
                    self._send(400, {"error": "response_format json_schema not supported"})
                    return
                content = body["messages"][1]["content"]
                texts = [c["text"] for c in content if c["type"] == "text"]
                images = sum(1 for c in content if c["type"] == "image_url")
                schema = json.loads(
                    body["messages"][0]["content"].split("JSON schema, and nothing else:\n")[1]
                )
                text = "```json\n" + json.dumps(answer(schema, texts, images)) + "\n```"
                self._send(
                    200,
                    {
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": text},
                            }
                        ]
                    },
                )

        return Handler
