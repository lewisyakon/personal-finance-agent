from pathlib import Path

from app.parsers.base import BillParser
from app.parsers.wechat_csv import WechatCsvParser


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

    def parse(self, path: Path, source: str = "wechat", format: str = "csv"):
        return self.create(source, format).parse(path)


parser_registry = ParserRegistry()
parser_registry.register("wechat", "csv", WechatCsvParser)

