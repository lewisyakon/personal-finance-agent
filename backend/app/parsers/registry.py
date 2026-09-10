from pathlib import Path

from app.parsers.base import BillParser
from app.parsers.wechat_csv import WechatCsvParser
from app.parsers.wechat_xlsx import WechatXlsxParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[tuple[str, str], type[BillParser]] = {}

    def register(self, source: str, format: str, parser: type[BillParser]) -> None:
        self._parsers[(source, format)] = parser

    def create(self, source: str, format: str) -> BillParser:
        try:
            return self._parsers[(source, format)]()
        except KeyError as exc:
            raise ValueError(f"不支持的账单来源或格式: {source}/{format}") from exc

    def parse(self, path: Path, source: str = "wechat", format: str | None = None):
        # Preserve the stage-1 default for extensionless CSV fixtures while
        # allowing normal uploads to select XLSX from their file suffix.
        resolved_format = format or path.suffix.lower().lstrip(".") or "csv"
        return self.create(source, resolved_format).parse(path)


parser_registry = ParserRegistry()
parser_registry.register("wechat", "csv", WechatCsvParser)
parser_registry.register("wechat", "xlsx", WechatXlsxParser)
