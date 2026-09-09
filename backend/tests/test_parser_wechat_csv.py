from app.parsers.registry import parser_registry


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
