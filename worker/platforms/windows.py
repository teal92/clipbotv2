"""Preserve the released Windows implementation and its DPAPI-compatible paths."""
from ..windows_integration import SingleInstance, parse_pair_link, user_directory, set_startup, startup_enabled

__all__ = ['SingleInstance', 'parse_pair_link', 'user_directory', 'set_startup', 'startup_enabled']
