from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from datahub.emitter.mce_builder import make_tag_urn, make_user_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.graph.client import DatahubClientConfig, DataHubGraph
from datahub.ingestion.run.pipeline import Pipeline, PipelineExecutionError
from datahub.metadata.schema_classes import (
    DatasetPropertiesClass,
    GlobalTagsClass,
    OwnerClass,
    OwnershipClass,
    OwnershipTypeClass,
    SchemaMetadataClass,
    StatusClass,
    TagAssociationClass,
)

from tests.rawtree_api_fixture import RawTreeApiFixture

pytestmark = pytest.mark.datahub_e2e


@pytest.fixture
def gms_url() -> str:
    value = os.getenv("DATAHUB_E2E_GMS_URL")
    if not value:
        pytest.skip("DATAHUB_E2E_GMS_URL is not set")
    return value.rstrip("/")


@pytest.fixture
def api() -> Iterator[RawTreeApiFixture]:
    fixture = RawTreeApiFixture().start()
    try:
        yield fixture
    finally:
        fixture.close()


def _run_pipeline(
    api: RawTreeApiFixture,
    gms_url: str,
    pipeline_name: str,
    platform_instance: str,
) -> Pipeline:
    pipeline = Pipeline.create(
        {
            "source": {
                "type": "rawtree",
                "config": {
                    "base_url": api.base_url,
                    "api_key": api.api_key,
                    "platform_instance": platform_instance,
                    "stateful_ingestion": {
                        "enabled": True,
                        "remove_stale_metadata": True,
                        "fail_safe_threshold": 100,
                    },
                },
            },
            "sink": {
                "type": "datahub-rest",
                "config": {"server": gms_url, "mode": "SYNC"},
            },
            "pipeline_name": pipeline_name,
        },
        report_to=None,
        no_progress=True,
    )
    pipeline.run()
    return pipeline


def test_schema_refresh_governance_preservation_and_safe_deletion(
    api: RawTreeApiFixture, gms_url: str
) -> None:
    suffix = uuid4().hex[:12]
    platform_instance = f"e2e-{suffix}"
    pipeline_name = f"rawtree-datahub-e2e-{suffix}"
    dataset_urn = (
        "urn:li:dataset:(urn:li:dataPlatform:rawtree,"
        f"{platform_instance}.analytics.events,PROD)"
    )
    graph = DataHubGraph(DatahubClientConfig(server=gms_url))

    try:
        initial = _run_pipeline(api, gms_url, pipeline_name, platform_instance)
        initial.raise_from_status()

        schema = graph.get_aspect(dataset_urn, SchemaMetadataClass)
        assert schema is not None
        assert [field.fieldPath for field in schema.fields] == [
            "timestamp",
            "attributes.service.name",
            "payload",
        ]

        graph.emit_mcp(
            MetadataChangeProposalWrapper(
                entityUrn=dataset_urn,
                aspect=DatasetPropertiesClass(
                    name="events",
                    qualifiedName="analytics.events",
                    description="Customer-authored description",
                ),
            )
        )
        graph.emit_mcp(
            MetadataChangeProposalWrapper(
                entityUrn=dataset_urn,
                aspect=OwnershipClass(
                    owners=[
                        OwnerClass(
                            owner=make_user_urn("rawtree-e2e-owner"),
                            type=OwnershipTypeClass.TECHNICAL_OWNER,
                        )
                    ]
                ),
            )
        )
        graph.emit_mcp(
            MetadataChangeProposalWrapper(
                entityUrn=dataset_urn,
                aspect=GlobalTagsClass(
                    tags=[TagAssociationClass(tag=make_tag_urn("rawtree-e2e"))]
                ),
            )
        )

        api.tables["analytics"]["events"].append(
            {"name": "status_code", "type": "UInt16"}
        )
        refresh = _run_pipeline(api, gms_url, pipeline_name, platform_instance)
        refresh.raise_from_status()

        refreshed_schema = graph.get_aspect(dataset_urn, SchemaMetadataClass)
        properties = graph.get_aspect(dataset_urn, DatasetPropertiesClass)
        ownership = graph.get_aspect(dataset_urn, OwnershipClass)
        tags = graph.get_aspect(dataset_urn, GlobalTagsClass)
        assert refreshed_schema is not None
        assert [field.fieldPath for field in refreshed_schema.fields][-1] == "status_code"
        assert properties is not None
        assert properties.description == "Customer-authored description"
        assert ownership is not None
        assert ownership.owners[0].owner == make_user_urn("rawtree-e2e-owner")
        assert tags is not None
        assert tags.tags[0].tag == make_tag_urn("rawtree-e2e")

        api.fail_describe.add(("analytics", "events"))
        failed = _run_pipeline(api, gms_url, pipeline_name, platform_instance)
        with pytest.raises(PipelineExecutionError):
            failed.raise_from_status()
        status_after_failure = graph.get_aspect(dataset_urn, StatusClass)
        assert status_after_failure is None or not status_after_failure.removed

        api.fail_describe.clear()
        api.tables["analytics"].clear()
        removal = _run_pipeline(api, gms_url, pipeline_name, platform_instance)
        removal.raise_from_status()
        removed_status = graph.get_aspect(dataset_urn, StatusClass)
        assert removed_status is not None
        assert removed_status.removed
    finally:
        graph.delete_entity(dataset_urn, hard=True)
        graph.close()
