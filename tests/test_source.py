from __future__ import annotations

import json
from typing import cast

import pytest
from datahub.ingestion.api.common import PipelineContext
from datahub.metadata.schema_classes import (
    GlobalTagsClass,
    OwnershipClass,
    SchemaMetadataClass,
)
from pydantic import ValidationError

from rawtree_datahub.client import Column, Database, RawTreeClient, TableDetail, TableSummary
from rawtree_datahub.source import RawTreeConfig, RawTreeSource


class FakeRawTreeClient:
    def __init__(self) -> None:
        self.closed = False

    def list_databases(self) -> list[Database]:
        return [Database(name="system"), Database(name="analytics")]

    def list_tables(self, database: str) -> list[TableSummary]:
        assert database == "analytics"
        return [
            TableSummary(
                name="ignored",
                created_at="2026-01-01T00:00:00Z",
                total_rows=0,
                total_bytes=0,
            ),
            TableSummary(
                name="events",
                created_at="2026-01-01T00:00:00Z",
                total_rows=12,
                total_bytes=1024,
            ),
        ]

    def describe_table(self, database: str, table: str) -> TableDetail:
        assert (database, table) == ("analytics", "events")
        return TableDetail(
            name="events",
            created_at="2026-01-01T00:00:00Z",
            total_rows=12,
            total_bytes=1024,
            columns=[
                Column(name="timestamp", type="DateTime64(3)"),
                Column(name="attributes.service.name", type="Nullable(String)"),
            ],
        )

    def close(self) -> None:
        self.closed = True


def test_source_emits_stable_dataset_identity_and_schema() -> None:
    config = RawTreeConfig.model_validate(
        {
            "api_key": "secret",
            "platform_instance": "acme-production",
            "table_pattern": {"allow": ["analytics.events"]},
        }
    )
    fake_client = FakeRawTreeClient()
    source = RawTreeSource(
        PipelineContext(run_id="test"),
        config,
        client=cast(RawTreeClient, fake_client),
    )

    workunits = list(source.get_workunits_internal())
    dataset_urn = (
        "urn:li:dataset:(urn:li:dataPlatform:rawtree,"
        "acme-production.analytics.events,PROD)"
    )
    dataset_workunits = [workunit for workunit in workunits if workunit.get_urn() == dataset_urn]

    schema = next(
        aspect
        for workunit in dataset_workunits
        if (aspect := workunit.get_aspect_of_type(SchemaMetadataClass)) is not None
    )
    assert [(field.fieldPath, field.nativeDataType, field.nullable) for field in schema.fields] == [
        ("timestamp", "DateTime64(3)", False),
        ("attributes.service.name", "Nullable(String)", True),
    ]
    assert source.report.databases_scanned == 1
    assert source.report.tables_scanned == 1
    assert list(source.report.filtered) == ["analytics.ignored", "system"]

    # The connector only patches its display/qualified names. Governance authored in
    # DataHub remains untouched because no ownership, tags, or description are emitted.
    assert not any(
        workunit.get_aspect_of_type(aspect_type)
        for workunit in dataset_workunits
        for aspect_type in (OwnershipClass, GlobalTagsClass)
    )
    properties_patches = [
        workunit.metadata.aspect.value
        for workunit in dataset_workunits
        if getattr(workunit.metadata, "aspectName", None) == "datasetProperties"
    ]
    assert len(properties_patches) == 1
    assert json.loads(properties_patches[0]) == [
        {"op": "add", "path": "/name", "value": "events"},
        {
            "op": "add",
            "path": "/qualifiedName",
            "value": "analytics.events",
        },
    ]

    source.close()
    assert fake_client.closed


def test_config_requires_stable_platform_instance_and_valid_base_url() -> None:
    with pytest.raises(ValidationError, match="platform_instance"):
        RawTreeConfig.model_validate({"api_key": "secret"})

    with pytest.raises(ValidationError, match="absolute HTTP"):
        RawTreeConfig.model_validate(
            {
                "api_key": "secret",
                "platform_instance": "acme-production",
                "base_url": "api.example.test",
            }
        )
