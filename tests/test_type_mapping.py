from __future__ import annotations

import pytest
from datahub.metadata.schema_classes import (
    ArrayTypeClass,
    DateTypeClass,
    NumberTypeClass,
    RecordTypeClass,
    StringTypeClass,
    TimeTypeClass,
)

from rawtree_datahub.type_mapping import is_nullable, to_datahub_type


@pytest.mark.parametrize(
    ("native_type", "expected"),
    [
        ("UInt64", NumberTypeClass),
        ("Nullable(LowCardinality(String))", StringTypeClass),
        ("Date32", DateTypeClass),
        ("DateTime64(3, 'UTC')", TimeTypeClass),
        ("Array(String)", ArrayTypeClass),
        ("Map(String, UInt64)", RecordTypeClass),
        ("Dynamic", RecordTypeClass),
        ("UnknownFutureType", StringTypeClass),
    ],
)
def test_type_mapping(native_type: str, expected: type[object]) -> None:
    assert isinstance(to_datahub_type(native_type).type, expected)


@pytest.mark.parametrize(
    ("native_type", "expected"),
    [
        ("Nullable(String)", True),
        ("LowCardinality(Nullable(String))", True),
        ("LowCardinality(String)", False),
        ("Array(Nullable(String))", False),
    ],
)
def test_nullability(native_type: str, expected: bool) -> None:
    assert is_nullable(native_type) is expected
