"""
Structured Logging Configuration (re-export)
=============================================

This module re-exports ``configure_logging`` from ``graphs.common.logging``
for backwards compatibility.  All new code should import directly from
``common.logging`` instead.
"""

from common.logging import configure_logging

__all__ = ["configure_logging"]
