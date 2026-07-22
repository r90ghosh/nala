"""Shared fixtures: a threading fake backlog HTTP server (in-memory, never
the real :8421) and a tmp NALA_DATA_DIR. Every test that touches sqlite or
the network must request these."""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class Store:
    def __init__(self):
        self.tasks = []
        self.next_id = 1
        self.down = False


def _make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _send_json(self, data, status=200):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length))

        def do_GET(self):
            if store.down:
                self.send_response(503)
                self.end_headers()
                return
            if self.path.startswith("/api/tasks"):
                self._send_json(store.tasks)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if store.down:
                self.send_response(503)
                self.end_headers()
                return
            if self.path != "/api/tasks":
                self.send_response(404)
                self.end_headers()
                return
            body = self._read_body()
            task = {
                "id": store.next_id,
                "title": body.get("title", ""),
                "description": body.get("description", ""),
                "project": body.get("project", ""),
                "priority": body.get("priority", "medium"),
                "status": "backlog",
                "category": body.get("category", ""),
            }
            store.next_id += 1
            store.tasks.append(task)
            self._send_json(task, 201)

        def do_PUT(self):
            if store.down:
                self.send_response(503)
                self.end_headers()
                return
            match = re.fullmatch(r"/api/tasks/(\d+)/status", self.path)
            if not match:
                self.send_response(404)
                self.end_headers()
                return
            task_id = int(match.group(1))
            body = self._read_body()
            for t in store.tasks:
                if t["id"] == task_id:
                    t["status"] = body.get("status", t["status"])
                    self._send_json(t)
                    return
            self.send_response(404)
            self.end_headers()

    return Handler


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "nala-data"
    monkeypatch.setenv("NALA_DATA_DIR", str(d))
    return d


@pytest.fixture
def fake_backlog(monkeypatch):
    store = Store()
    handler = _make_handler(store)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("NALA_BACKLOG_URL", f"http://127.0.0.1:{port}")
    yield store
    server.shutdown()
    server.server_close()


class FakeBrain:
    """Swappable brain double: returns a fixed RawIntent, never touches the network."""

    def __init__(self, intent):
        self.intent = intent
        self.calls = 0

    def decide(self, utterance, *, turn_id=None, session_id=None, memory_context=None):
        self.calls += 1
        return self.intent


@pytest.fixture
def make_fake_brain():
    return FakeBrain


class OllamaStore:
    def __init__(self):
        self.responses: list[str] = []  # queued raw `content` strings, popped in order
        self.down = False
        self.calls = 0


def _make_ollama_handler(store: OllamaStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            if not self.path.startswith("/chat/completions"):
                self.send_response(404)
                self.end_headers()
                return
            store.calls += 1
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)  # drain the request body

            if store.down or not store.responses:
                self.send_response(503)
                self.end_headers()
                return

            content = store.responses.pop(0)
            body = json.dumps({
                "id": "chatcmpl-fake",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    return Handler


@pytest.fixture
def fake_ollama(monkeypatch):
    store = OllamaStore()
    handler = _make_ollama_handler(store)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("NALA_OLLAMA_URL", f"http://127.0.0.1:{port}")
    yield store
    server.shutdown()
    server.server_close()
