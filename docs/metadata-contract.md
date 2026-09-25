# Metadata contract

This document defines the contract shared by the customer-managed DataHub
source and the future RawTree-managed publisher.

## Network direction

The customer-managed source runs in the customer's ingestion environment:

```text
DataHub ingestion runner -> RawTree HTTPS API
DataHub ingestion runner -> DataHub metadata service
```

RawTree does not need network access to a private DataHub deployment.

## RawTree API surface

The source uses these read-only endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /v1/databases` | Discover logical databases available to the API key |
| `GET /v1/tables?database=<name>` | Discover logical tables |
| `GET /v1/tables/<table>?database=<name>` | Read native field names and types |

Authentication uses `Authorization: Bearer <api-key>`. The connector supports
cluster-scoped RawTree API keys and recommends `read_only` permission.

The source uses logical database and table names returned by the API. It never
uses RawTree's physical multi-tenant names.

## Identity

- Data platform: `rawtree`
- Platform instance: required operator-supplied stable identifier
- Dataset name: `<database>.<table>`
- Environment: DataHub's `env`, defaulting to `PROD`
- Database container key: platform, platform instance, environment, database

API URL, API key, and DataHub endpoint are connectivity settings and never form
part of dataset identity.

## Schema

RawTree's table description returns native ClickHouse-compatible type strings.
The connector preserves each string in `nativeDataType` and maps it to the
closest DataHub type:

| RawTree type family | DataHub type |
|---|---|
| Integer, float, decimal, interval | Number |
| String, UUID, IP, enum | String |
| Boolean | Boolean |
| Date | Date |
| DateTime and time | Time |
| Array and Nested | Array |
| Map, Tuple, Object, JSON, Dynamic | Record |
| Unknown future type | String, while preserving the native type |

Fields returned by RawTree can include dotted nested subcolumns. Their field
paths are preserved verbatim.

## Governance ownership

The connector owns technical metadata:

- platform and platform instance
- database containment
- schema fields and native types
- technical display and qualified names
- asset presence or removal within the configured scope

The connector does not write:

- editable descriptions
- owners
- tags
- glossary terms
- domains
- access policies

Display and qualified names are emitted as DataHub patches, rather than a full
replacement of dataset properties, so unrelated DataHub-authored properties
are retained.

## Deletion and incomplete discovery

Deletion detection uses DataHub's stateful-ingestion checkpoints. A run that
cannot list all configured databases, tables, or schemas fails. It does not
commit a successful partial snapshot.

Filtering changes intentionally change the connector-owned scope. Operators
should preview recipe changes and keep DataHub's deletion fail-safe threshold
enabled.

## Compatibility rules

The future managed publisher must use the same platform, platform-instance,
dataset-name, environment, container-key, and schema-path rules. Switching
execution modes with the same values must address the same DataHub entities.
