# Contributing

Use Python 3.10 or newer and [uv](https://docs.astral.sh/uv/) for local work:

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy src
uv build
```

Connector changes must keep the identity and governance rules in
[`docs/metadata-contract.md`](docs/metadata-contract.md). Add a test when a
change affects API parsing, filtering, identity, schema mapping, or emitted
aspects.

Do not commit API keys, DataHub tokens, or metadata captured from customer
environments.
