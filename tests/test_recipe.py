from __future__ import annotations

import json
from pathlib import Path

from datahub.ingestion.run.pipeline import Pipeline

from tests.rawtree_api_fixture import RawTreeApiFixture


def test_installed_plugin_runs_through_a_datahub_recipe(tmp_path: Path) -> None:
    api = RawTreeApiFixture().start()
    output = tmp_path / "metadata.json"
    try:
        pipeline = Pipeline.create(
            {
                "source": {
                    "type": "rawtree",
                    "config": {
                        "base_url": api.base_url,
                        "api_key": api.api_key,
                        "platform_instance": "recipe-test",
                    },
                },
                "sink": {"type": "file", "config": {"filename": str(output)}},
                "pipeline_name": "rawtree-recipe-test",
            },
            report_to=None,
            no_progress=True,
        )
        pipeline.run()
        pipeline.raise_from_status()
    finally:
        api.close()

    proposals = json.loads(output.read_text())
    dataset_urn = (
        "urn:li:dataset:(urn:li:dataPlatform:rawtree,"
        "recipe-test.analytics.events,PROD)"
    )
    dataset_proposals = [
        proposal for proposal in proposals if proposal.get("entityUrn") == dataset_urn
    ]

    aspect_names = {proposal["aspectName"] for proposal in dataset_proposals}
    assert {
        "container",
        "dataPlatformInstance",
        "datasetProperties",
        "schemaMetadata",
    } <= aspect_names
    assert {"ownership", "globalTags", "glossaryTerms"}.isdisjoint(aspect_names)
    schema = next(
        proposal["aspect"]["json"]
        for proposal in dataset_proposals
        if proposal["aspectName"] == "schemaMetadata"
    )
    assert [field["fieldPath"] for field in schema["fields"]] == [
        "timestamp",
        "attributes.service.name",
        "payload",
    ]
    assert all(request["authorization"] == "Bearer rt_test_connector" for request in api.requests)
    assert all(request["user_agent"] == "rawtree-datahub" for request in api.requests)
    assert not any(
        request["query"].get("database") == ["system"] for request in api.requests
    )
