"""Immich Frames application."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("immich-frames")
except PackageNotFoundError:
    __version__ = "development"
