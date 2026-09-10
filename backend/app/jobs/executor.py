"""Task executor adapters.

The interface is intentionally tiny so a queue-backed implementation can be
introduced later without changing the import API.
"""

from app.services.import_service import InProcessImportExecutor

__all__ = ["InProcessImportExecutor"]
