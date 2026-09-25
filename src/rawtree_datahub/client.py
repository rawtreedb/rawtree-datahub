"""Small, typed client for RawTree's metadata APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError


class RawTreeApiError(RuntimeError):
    """A sanitized RawTree API failure safe to surface in ingestion reports."""


class _ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Database(_ApiModel):
    name: str


class DatabaseList(_ApiModel):
    databases: list[Database]


class TableSummary(_ApiModel):
    name: str
    created_at: str
    total_rows: int
    total_bytes: int


class TableList(_ApiModel):
    tables: list[TableSummary]


class Column(_ApiModel):
    name: str
    type: str


class TableDetail(TableSummary):
    columns: list[Column]


class TableDescription(_ApiModel):
    table: TableDetail


ApiModelT = TypeVar("ApiModelT", bound=_ApiModel)


@dataclass(frozen=True)
class RawTreeClientConfig:
    base_url: str
    api_key: str
    timeout_seconds: float = 30.0


class RawTreeClient:
    """Read-only access to databases, table summaries, and table schemas."""

    def __init__(
        self,
        config: RawTreeClientConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=f"{config.base_url.rstrip('/')}/",
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Accept": "application/json",
                "User-Agent": "rawtree-datahub",
            },
            follow_redirects=True,
            timeout=config.timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def list_databases(self) -> list[Database]:
        return self._get_model("v1/databases", DatabaseList).databases

    def list_tables(self, database: str) -> list[TableSummary]:
        return self._get_model(
            "v1/tables", TableList, params={"database": database}
        ).tables

    def describe_table(self, database: str, table: str) -> TableDetail:
        encoded_table = quote(table, safe="")
        path = f"v1/tables/{encoded_table}"
        return self._get_model(
            path, TableDescription, params={"database": database}
        ).table

    def _get_model(
        self,
        path: str,
        model: type[ApiModelT],
        *,
        params: dict[str, str] | None = None,
    ) -> ApiModelT:
        try:
            return model.model_validate(self._get_json(path, params=params))
        except ValidationError as error:
            raise RawTreeApiError(
                f"RawTree returned an invalid response for {path}."
            ) from error

    def _get_json(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            raise RawTreeApiError(
                f"RawTree request to {path} failed with HTTP {status}."
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            raise RawTreeApiError(f"RawTree request to {path} failed: {error}") from error
