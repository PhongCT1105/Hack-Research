"""Compatibility re-exports for collection progress helpers."""

try:
    from lib.progress import *  # noqa: F403
    from lib.progress import __all__  # noqa: F401
except ModuleNotFoundError:
    from .lib.progress import *  # type: ignore[no-redef]  # noqa: F403
    from .lib.progress import __all__  # type: ignore[no-redef]  # noqa: F401
