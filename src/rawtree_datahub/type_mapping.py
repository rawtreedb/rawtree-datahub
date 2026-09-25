"""Map RawTree/ClickHouse native types to DataHub schema types."""

from __future__ import annotations

from datahub.metadata.schema_classes import (
    ArrayTypeClass,
    BooleanTypeClass,
    BytesTypeClass,
    DateTypeClass,
    NumberTypeClass,
    RecordTypeClass,
    SchemaFieldDataTypeClass,
    StringTypeClass,
    TimeTypeClass,
)

DataHubPrimitiveType = (
    ArrayTypeClass
    | BooleanTypeClass
    | BytesTypeClass
    | DateTypeClass
    | NumberTypeClass
    | RecordTypeClass
    | StringTypeClass
    | TimeTypeClass
)


def _base_type(native_type: str) -> str:
    current = native_type.strip()
    while True:
        opening = current.find("(")
        if opening == -1 or not current.endswith(")"):
            return current
        wrapper = current[:opening].strip().lower()
        if wrapper not in {"nullable", "lowcardinality"}:
            return current
        current = current[opening + 1 : -1].strip()


def is_nullable(native_type: str) -> bool:
    current = native_type.strip()
    while True:
        opening = current.find("(")
        if opening == -1 or not current.endswith(")"):
            return False
        wrapper = current[:opening].strip().lower()
        if wrapper == "nullable":
            return True
        if wrapper != "lowcardinality":
            return False
        current = current[opening + 1 : -1].strip()


def to_datahub_type(native_type: str) -> SchemaFieldDataTypeClass:
    normalized = _base_type(native_type).lower()
    if normalized.startswith(("array(", "nested(")):
        mapped: DataHubPrimitiveType = ArrayTypeClass()
    elif normalized.startswith(("map(", "tuple(", "object(", "json", "dynamic")):
        mapped = RecordTypeClass()  # type: ignore[no-untyped-call]
    elif normalized.startswith("date") and not normalized.startswith("datetime"):
        mapped = DateTypeClass()  # type: ignore[no-untyped-call]
    elif normalized.startswith(("datetime", "time")):
        mapped = TimeTypeClass()  # type: ignore[no-untyped-call]
    elif normalized.startswith("bool"):
        mapped = BooleanTypeClass()  # type: ignore[no-untyped-call]
    elif normalized.startswith(("fixedstring", "string", "uuid", "ipv", "enum")):
        mapped = StringTypeClass()  # type: ignore[no-untyped-call]
    elif normalized.startswith("bytes"):
        mapped = BytesTypeClass()  # type: ignore[no-untyped-call]
    elif normalized.startswith(
        ("int", "uint", "float", "decimal", "bfloat", "interval")
    ):
        mapped = NumberTypeClass()  # type: ignore[no-untyped-call]
    else:
        mapped = StringTypeClass()  # type: ignore[no-untyped-call]
    return SchemaFieldDataTypeClass(type=mapped)
