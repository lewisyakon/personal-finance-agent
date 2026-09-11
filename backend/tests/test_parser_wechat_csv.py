from datetime import datetime
from io import BytesIO

from openpyxl import Workbook

from app.parsers.registry import parser_registry
from app.parsers.wechat_csv import parse_wechat_rows


def test_wechat_csv_golden_sample(sample_dir):
    report = parser_registry.parse(sample_dir / "wechat_sample_utf8.csv")

    assert report.encoding == "utf-8-sig"
    assert report.header_row == 4
    assert report.total_rows == 3
    assert report.success_rows == 3
    assert not report.error_rows
    assert report.records[0].amount_minor == 1250
    assert report.records[0].direction == "expense"
    assert report.records[0].occurred_at.tzinfo is not None
    assert report.records[2].direction == "income"


def test_parser_reports_bad_rows(sample_dir):
    report = parser_registry.parse(sample_dir / "wechat_sample_with_error.csv")

    assert report.total_rows == 3
    assert report.success_rows == 2
    assert [error.row_number for error in report.error_rows] == [6]
    assert "金额" in report.error_rows[0].message


def test_parser_rejects_missing_required_header(sample_dir):
    report = parser_registry.parse(sample_dir / "wechat_sample_missing_column.csv")

    assert report.success_rows == 0
    assert report.error_rows
    assert "缺少关键列" in report.error_rows[0].message


def test_wechat_xlsx_parser_reads_excel_cells(tmp_path):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["微信支付账单明细"])
    worksheet.append(["统计时间", "2026-01-01 至 2026-01-31"])
    worksheet.append([])
    worksheet.append(
        [
            "交易时间",
            "交易类型",
            "交易对方",
            "商品",
            "收/支",
            "金额(元)",
            "支付方式",
            "当前状态",
            "交易单号",
        ]
    )
    worksheet.append(
        [
            datetime(2026, 1, 3, 8, 12, 30),
            "商户消费",
            "早餐店",
            "早餐",
            "支出",
            12.5,
            "零钱",
            "支付成功",
            "WX-XLSX-001",
        ]
    )
    worksheet.append(
        [
            datetime(2026, 1, 10, 9, 30),
            "转账",
            "朋友",
            "AA",
            "收入",
            50,
            "零钱",
            "交易成功",
            "WX-XLSX-002",
        ]
    )
    content = BytesIO()
    workbook.save(content)
    path = tmp_path / "wechat-export.xlsx"
    path.write_bytes(content.getvalue())

    report = parser_registry.parse(path)

    assert report.format == "xlsx"
    assert report.encoding == "xlsx"
    assert report.header_row == 4
    assert report.total_rows == 2
    assert report.success_rows == 2
    assert not report.error_rows
    assert report.records[0].amount_minor == 1250
    assert report.records[0].direction == "expense"
    assert report.records[0].status == "success"
    assert report.records[1].amount_minor == 5000
    assert report.records[1].direction == "income"


def test_wechat_status_variants_are_normalized_deterministically():
    rows = [
        [
            "交易时间",
            "交易类型",
            "交易对方",
            "商品",
            "收/支",
            "金额(元)",
            "支付方式",
            "交易状态",
            "交易单号",
        ],
        [
            "2026-01-01 08:00:00",
            "商户消费",
            "早餐店",
            "早餐",
            "支出",
            "1",
            "零钱",
            "已全额退款",
            "STATUS-001",
        ],
        [
            "2026-01-01 09:00:00",
            "商户消费",
            "午餐店",
            "午餐",
            "支出",
            "2",
            "零钱",
            "已退款¥0.56",
            "STATUS-002",
        ],
        [
            "2026-01-01 10:00:00",
            "转账",
            "朋友",
            "AA",
            "收入",
            "3",
            "零钱",
            "已存入零钱",
            "STATUS-003",
        ],
        [
            "2026-01-01 11:00:00",
            "转账",
            "朋友",
            "AA",
            "收入",
            "4",
            "零钱",
            "对方已收钱",
            "STATUS-004",
        ],
        [
            "2026-01-01 12:00:00",
            "转账",
            "朋友",
            "AA",
            "收入",
            "5",
            "零钱",
            "已转账",
            "STATUS-005",
        ],
        [
            "2026-01-01 13:00:00",
            "转账",
            "朋友",
            "AA",
            "收入",
            "6",
            "零钱",
            "已收钱",
            "STATUS-006",
        ],
    ]

    report = parse_wechat_rows(rows, encoding="synthetic", format="csv")

    assert report.success_rows == 6
    assert not report.error_rows
    assert [record.status for record in report.records] == [
        "refunded",
        "refunded",
        "success",
        "success",
        "success",
        "success",
    ]
