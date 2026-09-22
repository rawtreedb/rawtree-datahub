# RawTree source for DataHub

`rawtree-datahub` is the official metadata source for cataloging
[RawTree](https://rawtree.com) databases, tables, and schemas in
[DataHub](https://datahub.com).

The source runs alongside DataHub, reads metadata from RawTree over HTTPS, and
emits DataHub metadata events. It never reads or copies table rows.

> [!IMPORTANT]
> This connector is under active development and has not yet been published to
> PyPI. Install from a tagged release after the first release is announced.

## What it publishes

- RawTree as a DataHub data platform
- One database container per selected RawTree database
- Tables with their logical `database.table` identity
- Native field types, including nested subcolumns returned by RawTree
- A stable DataHub platform instance chosen by the operator

The connector does not publish ownership, tags, glossary terms, editable
descriptions, profiling results, sample values, or lineage. Existing governance
annotations in DataHub remain owned by DataHub users and workflows.

## Configuration

Create a read-only RawTree API key and store credentials in environment
variables:

```bash
export RAWTREE_API_KEY=rt_...
export DATAHUB_TOKEN=...
```

Create `rawtree.dhub.yml`:

```yaml
source:
  type: rawtree
  config:
    base_url: https://api.rawtree.com
    api_key: ${RAWTREE_API_KEY}
    # Stable identity for this RawTree cluster. Never rename it after ingestion.
    platform_instance: acme-production
    database_pattern:
      allow:
        - ^analytics$
    stateful_ingestion:
      enabled: true
      remove_stale_metadata: true

sink:
  type: datahub-rest
  config:
    server: https://datahub.example.com
    token: ${DATAHUB_TOKEN}

pipeline_name: rawtree-acme-production
```

After the package is released:

```bash
python -m pip install rawtree-datahub
datahub ingest -c rawtree.dhub.yml
```

The machine executing this command must be able to reach both the RawTree API
and the destination DataHub instance. DataHub or the customer's scheduler owns
the cadence for this connector.

## Dataset identity

Dataset identity is deliberately independent of API hostname and credentials:

```text
urn:li:dataset:(
  urn:li:dataPlatform:rawtree,
  <platform_instance>.<database>.<table>,
  <env>
)
```

For example, `platform_instance: acme-production`, database `analytics`, and
table `events` produce the name component
`acme-production.analytics.events`. The exact URN serialization is performed
by DataHub's `DatasetUrn.create_from_ids`; the logical dataset name passed to it
is `analytics.events`.

Changing `platform_instance`, `env`, a database name, or a table name creates a
new DataHub identity. See [the metadata contract](docs/metadata-contract.md)
before changing production recipes.

## Stateful deletion

When stateful ingestion is enabled, DataHub checkpoints successful runs and can
soft-delete assets that disappear from a later complete run. DataHub's
fail-safe threshold is retained. A failed RawTree request raises the ingestion
run as failed instead of turning a partial discovery into a successful empty
snapshot.

## Development

This project requires Python 3.10 or newer and uses
[uv](https://docs.astral.sh/uv/):

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy
```

The source is registered through the
`datahub.ingestion.source.plugins` entry-point group under the alias `rawtree`.

## License

Apache License 2.0.
