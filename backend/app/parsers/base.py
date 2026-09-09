from pathlib import Path
from typing import Protocol

from app.schemas.transaction import ParseReport


class BillParser(Protocol):
    source: str
    format: str

    def parse(self, path: Path) -> ParseReport:
        """Parse a bill file without calling a model."""

