from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


@dataclass
class RawTreeApiFixture:
    api_key: str = "rt_test_connector"
    tables: dict[str, dict[str, list[dict[str, str]]]] = field(
        default_factory=lambda: {
            "analytics": {
                "events": [
                    {"name": "timestamp", "type": "DateTime64(3)"},
                    {
                        "name": "attributes.service.name",
                        "type": "Nullable(String)",
                    },
                    {"name": "payload", "type": "Dynamic"},
                ]
            }
        }
    )
    fail_describe: set[tuple[str, str]] = field(default_factory=set)
    requests: list[dict[str, Any]] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = field(default=None, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)

    @property
    def base_url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> RawTreeApiFixture:
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                fixture._handle(self)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def _handle(self, request: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(request.path)
        query = parse_qs(parsed.query)
        self.requests.append(
            {
                "path": parsed.path,
                "query": query,
                "authorization": request.headers.get("Authorization"),
                "user_agent": request.headers.get("User-Agent"),
            }
        )

        if request.headers.get("Authorization") != f"Bearer {self.api_key}":
            self._respond(request, 401, {"error": "unauthorized"})
            return
        if parsed.path == "/v1/databases":
            databases = [{"name": name, "s3_storage": None} for name in self.tables]
            databases.append({"name": "system", "s3_storage": None})
            self._respond(request, 200, {"databases": databases})
            return
        if parsed.path == "/v1/tables":
            database = query.get("database", [""])[0]
            tables = [self._table_summary(name) for name in self.tables.get(database, {})]
            self._respond(request, 200, {"tables": tables})
            return
        if parsed.path.startswith("/v1/tables/"):
            database = query.get("database", [""])[0]
            table = unquote(parsed.path.removeprefix("/v1/tables/"))
            if (database, table) in self.fail_describe:
                self._respond(request, 503, {"error": "fixture failure"})
                return
            columns = self.tables.get(database, {}).get(table)
            if columns is None:
                self._respond(request, 404, {"error": "not found"})
                return
            self._respond(
                request,
                200,
                {"table": {**self._table_summary(table), "columns": columns}},
            )
            return
        self._respond(request, 404, {"error": "not found"})

    @staticmethod
    def _table_summary(name: str) -> dict[str, Any]:
        return {
            "name": name,
            "created_at": "2026-01-01T00:00:00Z",
            "total_rows": 12,
            "total_bytes": 1024,
        }

    @staticmethod
    def _respond(
        request: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]
    ) -> None:
        body = json.dumps(payload).encode()
        request.send_response(status)
        request.send_header("Content-Type", "application/json")
        request.send_header("Content-Length", str(len(body)))
        request.end_headers()
        request.wfile.write(body)

