"""RawTree metadata source for DataHub."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("rawtree-datahub")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]
