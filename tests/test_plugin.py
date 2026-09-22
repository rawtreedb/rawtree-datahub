from __future__ import annotations

from importlib.metadata import entry_points

from rawtree_datahub.source import RawTreeSource


def test_datahub_source_entry_point_is_registered() -> None:
    plugins = {
        entry.name: entry
        for entry in entry_points(group="datahub.ingestion.source.plugins")
    }

    assert plugins["rawtree"].load() is RawTreeSource
