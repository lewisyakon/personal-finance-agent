import csv
import io
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.parsers.encoding import decode_bill
from app.schemas.transaction import ParseReport, ParseRowError, TransactionRecord

HEADER_ALIASES = {
    "occurred_at": ("交易时间", "时间", "交易日期"),
    "type": ("交易类型", "类型"),
    "merchant": ("交易对方", "商户", "商户名称"),
    "description": ("商品", "商品说明", "备注"),
    "direction": ("收/支", "收支", "交易方向"),
    "amount": ("金额(元)", "金额（元）", "金额", "交易金额"),
    "payment_method": ("支付方式", "付款方式"),
    "status": ("交易状态", "当前状态", "状态"),
    "source_transaction_id": ("交易单号", "流水号", "订单号"),
    "platform_category": ("平台分类", "类别"),
}


def _clean(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).replace("\ufeff", "").strip()


def _find_column(header: list[str], names: tuple[str, ...]) -> int | None:
    normalized = [_clean(item).replace(" ", "") for item in header]
    for alias in names:
        alias = alias.replace(" ", "")
        for index, item in enumerate(normalized):
            if item == alias:
                return index
    return None


def _parse_amount(value: object | None) -> int:
    cleaned = _clean(value).replace(",", "").replace("¥", "").replace("￥", "")
    if not cleaned:
        raise ValueError("金额为空")
    try:
        amount = Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"金额格式无效: {value!r}") from exc
    if amount < 0:
        raise ValueError("金额不能为负数；方向应由收/支字段表示")
    return int(amount * 100)


def _parse_datetime(value: object | None) -> datetime:
    value = _clean(value)
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y.%m.%d",
    )
    for fmt in formats:
        try:
            timezone = ZoneInfo(get_settings().app_timezone)
            return datetime.strptime(value, fmt).replace(tzinfo=timezone)
        except ValueError:
            continue
    raise ValueError(f"交易时间格式无效: {value!r}")


def _direction(value: str) -> str:
    normalized = _clean(value)
    if normalized in {"支出", "付款", "消费"}:
        return "expense"
    if normalized in {"收入", "收款", "退款"}:
        return "income"
    if normalized in {"不计收支", "转账", "其他"}:
        return "transfer"
    if not normalized:
        return "unknown"
    return "unknown"


def _status(value: str) -> str:
    normalized = _clean(value)
    if normalized in {"支付成功", "交易成功", "成功"}:
        return "success"
    if normalized in {"已退款", "退款成功", "退款"}:
        return "refunded"
    if normalized in {"支付失败", "交易失败", "失败"}:
        return "failed"
    if normalized in {"待支付", "处理中", "进行中"}:
        return "pending"
    return "unknown"


class WechatCsvParser:
    source = "wechat"
    format = "csv"

    def parse(self, path: Path) -> ParseReport:
        text, encoding = decode_bill(path)
        rows = list(csv.reader(io.StringIO(text)))
        return parse_wechat_rows(rows, encoding, self.format)


def parse_wechat_rows(rows: list[list[object]], encoding: str, format: str = "csv") -> ParseReport:
    header_index = _header_index(rows)
    if header_index is None:
        return ParseReport(
            source="wechat",
            format=format,
            encoding=encoding,
            total_rows=0,
            error_rows=[ParseRowError(row_number=1, message="未找到包含关键列的表头")],
        )

    header = [_clean(item) for item in rows[header_index]]
    columns = {key: _find_column(header, aliases) for key, aliases in HEADER_ALIASES.items()}
    missing = [key for key in ("occurred_at", "amount", "direction") if columns[key] is None]
    if missing:
        return ParseReport(
            source="wechat",
            format=format,
            encoding=encoding,
            total_rows=max(0, len(rows) - header_index - 1),
            header_row=header_index + 1,
            error_rows=[
                ParseRowError(
                    row_number=header_index + 1,
                    message=f"缺少关键列: {', '.join(missing)}",
                )
            ],
        )

    records: list[TransactionRecord] = []
    errors: list[ParseRowError] = []
    data_rows = rows[header_index + 1 :]
    non_empty_rows = [row for row in data_rows if any(_clean(cell) for cell in row)]
    for offset, row in enumerate(data_rows, start=header_index + 2):
        if not any(_clean(cell) for cell in row):
            continue
        try:
            records.append(_record(row, columns, offset))
        except (ValueError, TypeError, IndexError) as exc:
            errors.append(ParseRowError(row_number=offset, message=str(exc)))

    return ParseReport(
        source="wechat",
        format=format,
        encoding=encoding,
        total_rows=len(non_empty_rows),
        success_rows=len(records),
        error_rows=errors,
        records=records,
        header_row=header_index + 1,
    )


def _header_index(rows: list[list[object]]) -> int | None:
    for index, row in enumerate(rows):
        normalized = {_clean(cell).replace(" ", "") for cell in row}
        has_time = bool(normalized & {"交易时间", "时间", "交易日期"})
        has_amount = bool(normalized & {"金额(元)", "金额（元）", "金额", "交易金额"})
        has_direction = bool(normalized & {"收/支", "收支", "交易方向"})
        # Identify a likely transaction header even when one required
        # column is missing, so the report can name the missing column.
        if has_time and (has_amount or has_direction):
            return index
    return None


def _cell(row: list[object], index: int | None) -> str:
    return _clean(row[index]) if index is not None and index < len(row) else ""


def _record(
    row: list[object],
    columns: dict[str, int | None],
    row_number: int,
) -> TransactionRecord:
    type_value = _cell(row, columns["type"])
    description = _cell(row, columns["description"])
    return TransactionRecord(
        platform="wechat",
        occurred_at=_parse_datetime(_cell(row, columns["occurred_at"])),
        direction=_direction(_cell(row, columns["direction"])),
        amount_minor=_parse_amount(_cell(row, columns["amount"])),
        status=_status(_cell(row, columns["status"])),
        merchant=_cell(row, columns["merchant"]),
        description=description or type_value,
        payment_method=_cell(row, columns["payment_method"]),
        platform_category=_cell(row, columns["platform_category"]),
        source_transaction_id=_cell(row, columns["source_transaction_id"]) or None,
        source_row=row_number,
    )
