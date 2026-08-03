"""DhakaGraph: practical spatial graph exploration for Dhaka."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dhakagraph")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__"]
