from __future__ import annotations

import httpx
import pytest

from rawtree_datahub.client import RawTreeApiError, RawTreeClient, RawTreeClientConfig


def test_client_uses_bearer_auth_and_routes_metadata_requests() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/databases":
            return httpx.Response(200, json={"databases": [{"name": "analytics"}]})
        if request.url.path == "/v1/tables":
            return httpx.Response(
                200,
                json={
                    "tables": [
                        {
                            "name": "events",
                            "created_at": "2026-01-01T00:00:00Z",
                            "total_rows": 12,
                            "total_bytes": 1024,
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "table": {
                    "name": "events/current",
                    "created_at": "2026-01-01T00:00:00Z",
                    "total_rows": 12,
                    "total_bytes": 1024,
                    "columns": [{"name": "timestamp", "type": "DateTime64(3)"}],
                }
            },
        )

    client = RawTreeClient(
        RawTreeClientConfig("https://api.example.test", "secret"),
        transport=httpx.MockTransport(handler),
    )

    assert [database.name for database in client.list_databases()] == ["analytics"]
    assert [table.name for table in client.list_tables("analytics")] == ["events"]
    assert client.describe_table("analytics", "events/current").columns[0].name == "timestamp"
    client.close()

    assert [request.url.path for request in requests] == [
        "/v1/databases",
        "/v1/tables",
        "/v1/tables/events/current",
    ]
    assert dict(requests[1].url.params) == {"database": "analytics"}
    assert dict(requests[2].url.params) == {"database": "analytics"}
    assert all(request.headers["Authorization"] == "Bearer secret" for request in requests)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(401, text="token secret-token is invalid"), "HTTP 401"),
        (httpx.Response(200, content=b"not-json"), "request to v1/databases failed"),
        (httpx.Response(200, json={"databases": [{}]}), "invalid response"),
    ],
)
def test_client_errors_are_sanitized(
    response: httpx.Response, expected: str
) -> None:
    client = RawTreeClient(
        RawTreeClientConfig("https://api.example.test", "secret-token"),
        transport=httpx.MockTransport(lambda _: response),
    )

    with pytest.raises(RawTreeApiError, match=expected) as raised:
        client.list_databases()

    assert "secret-token" not in str(raised.value)
    client.close()
