"""DataHub ingestion source backed by RawTree's public HTTPS API."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import httpx
from datahub.configuration.common import AllowDenyPattern
from datahub.configuration.source_common import EnvConfigMixin, PlatformInstanceConfigMixin
from datahub.emitter.mce_builder import make_data_platform_urn, make_dataplatform_instance_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.mcp_builder import DatabaseKey, add_dataset_to_container, gen_containers
from datahub.ingestion.api.common import PipelineContext
from datahub.ingestion.api.decorators import (
    SourceCapability,
    SupportStatus,
    capability,
    config_class,
    platform_name,
    support_status,
)
from datahub.ingestion.api.workunit import MetadataWorkUnit
from datahub.ingestion.source.common.subtypes import DatasetContainerSubTypes
from datahub.ingestion.source.state.stale_entity_removal_handler import (
    StaleEntityRemovalSourceReport,
    StatefulStaleMetadataRemovalConfig,
)
from datahub.ingestion.source.state.stateful_ingestion_base import (
    StatefulIngestionConfig,
    StatefulIngestionConfigBase,
    StatefulIngestionSourceBase,
)
from datahub.metadata.schema_classes import (
    DataPlatformInfoClass,
    DataPlatformInstanceClass,
    SchemaFieldClass,
    SchemalessClass,
    SchemaMetadataClass,
)
from datahub.metadata.urns import DatasetUrn
from datahub.specific.dataset import DatasetPatchBuilder
from datahub.utilities.lossy_collections import LossyList
from pydantic import Field, SecretStr, field_validator

from rawtree_datahub.client import (
    Column,
    RawTreeClient,
    RawTreeClientConfig,
    TableDetail,
)
from rawtree_datahub.type_mapping import is_nullable, to_datahub_type

PLATFORM = "rawtree"


class RawTreeConfig(
    PlatformInstanceConfigMixin,
    EnvConfigMixin,
    StatefulIngestionConfigBase[StatefulIngestionConfig],
):
    base_url: str = Field(
        default="https://api.rawtree.com",
        description="RawTree API base URL.",
    )
    api_key: SecretStr = Field(
        description="Readable RawTree cluster API key. Use a read_only key when possible."
    )
    platform_instance: str = Field(
        description=(
            "Stable DataHub identity for this RawTree cluster, such as acme-production. "
            "Do not change it after the first successful ingestion."
        ),
        min_length=1,
    )
    database_pattern: AllowDenyPattern = Field(
        default_factory=AllowDenyPattern.allow_all,
        description="Databases to include or exclude.",
    )
    table_pattern: AllowDenyPattern = Field(
        default_factory=AllowDenyPattern.allow_all,
        description="Fully qualified database.table names to include or exclude.",
    )
    include_system_database: bool = Field(
        default=False,
        description="Include RawTree's read-only system database.",
    )
    timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Per-request timeout for RawTree metadata calls.",
    )
    stateful_ingestion: StatefulStaleMetadataRemovalConfig | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        url = httpx.URL(value)
        if url.scheme not in {"http", "https"} or not url.host:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if url.query or url.fragment:
            raise ValueError("base_url must not contain a query string or fragment")
        return value.rstrip("/")


@dataclass
class RawTreeSourceReport(StaleEntityRemovalSourceReport):
    databases_scanned: int = 0
    tables_scanned: int = 0
    filtered: LossyList[str] = field(default_factory=LossyList)

    def report_filtered(self, name: str) -> None:
        self.filtered.append(name)


@platform_name("RawTree", id=PLATFORM)
@config_class(RawTreeConfig)
@support_status(SupportStatus.ALPHA)
@capability(SourceCapability.PLATFORM_INSTANCE, "Required for stable dataset identity")
@capability(SourceCapability.SCHEMA_METADATA, "Enabled by default")
@capability(SourceCapability.CONTAINERS, "Databases are emitted as containers")
@dataclass
class RawTreeSource(StatefulIngestionSourceBase):
    config: RawTreeConfig
    report: RawTreeSourceReport
    client: RawTreeClient
    platform: str = PLATFORM

    def __init__(
        self,
        ctx: PipelineContext,
        config: RawTreeConfig,
        *,
        client: RawTreeClient | None = None,
    ) -> None:
        super().__init__(config, ctx)
        self.config = config
        self.report = RawTreeSourceReport()
        self.client = client or RawTreeClient(
            RawTreeClientConfig(
                base_url=config.base_url,
                api_key=config.api_key.get_secret_value(),
                timeout_seconds=config.timeout_seconds,
            )
        )

    def close(self) -> None:
        self.client.close()
        super().close()

    def get_report(self) -> RawTreeSourceReport:
        return self.report

    def get_workunits_internal(self) -> Iterable[MetadataWorkUnit]:
        yield self._platform_workunit()
        for database in sorted(self.client.list_databases(), key=lambda item: item.name):
            if database.name == "system" and not self.config.include_system_database:
                self.report.report_filtered(database.name)
                continue
            if not self.config.database_pattern.allowed(database.name):
                self.report.report_filtered(database.name)
                continue
            self.report.databases_scanned += 1
            yield from self._database_workunits(database.name)

    def _database_workunits(self, database: str) -> Iterable[MetadataWorkUnit]:
        database_key = DatabaseKey(
            database=database,
            platform=self.platform,
            instance=self.config.platform_instance,
            env=self.config.env,
        )
        yield from gen_containers(
            container_key=database_key,
            name=database,
            sub_types=[DatasetContainerSubTypes.DATABASE],
        )
        for summary in sorted(self.client.list_tables(database), key=lambda item: item.name):
            qualified_name = f"{database}.{summary.name}"
            if not self.config.table_pattern.allowed(qualified_name):
                self.report.report_filtered(qualified_name)
                continue
            detail = self.client.describe_table(database, summary.name)
            self.report.tables_scanned += 1
            yield from self._table_workunits(database_key, database, detail)

    def _table_workunits(
        self,
        database_key: DatabaseKey,
        database: str,
        table: TableDetail,
    ) -> Iterable[MetadataWorkUnit]:
        qualified_name = f"{database}.{table.name}"
        dataset_urn = DatasetUrn.create_from_ids(
            platform_id=self.platform,
            table_name=qualified_name,
            env=self.config.env,
            platform_instance=self.config.platform_instance,
        )
        yield from add_dataset_to_container(database_key, dataset_urn.urn())
        aspects = [
            self._schema_metadata(qualified_name, table.columns),
            DataPlatformInstanceClass(
                platform=make_data_platform_urn(self.platform),
                instance=make_dataplatform_instance_urn(
                    self.platform, self.config.platform_instance
                ),
            ),
        ]
        yield from (
            proposal.as_workunit()
            for proposal in MetadataChangeProposalWrapper.construct_many(
                entityUrn=dataset_urn.urn(), aspects=aspects
            )
        )
        properties = (
            DatasetPatchBuilder(dataset_urn)
            .set_display_name(table.name)
            .set_qualified_name(qualified_name)
        )
        for proposal in properties.build():
            yield MetadataWorkUnit(
                id=MetadataWorkUnit.generate_workunit_id(proposal),
                mcp_raw=proposal,
                is_primary_source=False,
            )

    def _schema_metadata(
        self, name: str, columns: list[Column]
    ) -> SchemaMetadataClass:
        fields = [
            SchemaFieldClass(
                fieldPath=column.name,
                nativeDataType=column.type,
                type=to_datahub_type(column.type),
                nullable=is_nullable(column.type),
                recursive=False,
            )
            for column in columns
        ]
        return SchemaMetadataClass(
            schemaName=name,
            platform=make_data_platform_urn(self.platform),
            version=0,
            hash="",
            platformSchema=SchemalessClass(),  # type: ignore[no-untyped-call]
            fields=fields,
        )

    def _platform_workunit(self) -> MetadataWorkUnit:
        proposal = MetadataChangeProposalWrapper(
            entityUrn=make_data_platform_urn(self.platform),
            aspect=DataPlatformInfoClass(
                name=self.platform,
                displayName="RawTree",
                type="RELATIONAL_DB",
                datasetNameDelimiter=".",
            ),
        )
        return MetadataWorkUnit(
            id=MetadataWorkUnit.generate_workunit_id(proposal),
            mcp=proposal,
            is_primary_source=False,
        )
