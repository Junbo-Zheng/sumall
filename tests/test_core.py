# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Junbo Zheng

import pytest

from sumall.core import (
    describe_unit,
    parse_line,
    parse_text,
    parse_token,
    parse_tokens,
)


def test_parse_line_bare_number_uses_default_unit():
    e = parse_line("10", "MB")
    assert e.value == 10
    assert e.unit == "MB"
    assert e.label == ""


def test_parse_line_default_unit_is_mb():
    assert parse_line("10").unit == "MB"


def test_parse_line_suffix_overrides_default_unit():
    assert parse_line("177K", "MB").unit == "KB"
    assert parse_line("13M", "MB").unit == "MB"
    assert parse_line("1.9G", "MB").unit == "GB"


def test_parse_line_suffix_is_case_insensitive():
    assert parse_line("768k").unit == "KB"
    assert parse_line("1.9m").unit == "MB"
    assert parse_line("2g").unit == "GB"


def test_parse_line_decimal_value():
    e = parse_line("1.46")
    assert e.value == pytest.approx(1.46)


def test_parse_line_keeps_trailing_label():
    e = parse_line("177K  ./background_7.png")
    assert e.value == 177
    assert e.unit == "KB"
    assert e.label == "./background_7.png"


def test_parse_line_rejects_lines_without_leading_number():
    assert parse_line("") is None
    assert parse_line("   ") is None
    assert parse_line("hello world") is None
    assert parse_line("total 8.8M") is None
    assert parse_line(".5") is None


def test_parse_line_ls_long_format_takes_size_field_as_bytes():
    e = parse_line("-rw-rw-r-- 1 mi mi 11358  9月  1 09:48 LICENSE")
    assert e is not None
    assert e.value == 11358
    assert e.unit == "B"
    assert e.label == "LICENSE"
    assert e.line == "11358B LICENSE"


def test_parse_line_ls_lh_suffix_in_size_field():
    e = parse_line("-rw-r--r-- 1 mi mi 12K Sep 1 09:48 LICENSE")
    assert e is not None
    assert e.value == 12
    assert e.unit == "KB"


def test_parse_line_ls_directory_line_is_skipped():
    # A directory's "size" is the inode size, not content — summing it
    # would mislead.
    assert parse_line("drwxrwxr-x 3 mi mi 4096  9月  1 09:50 src/") is None


def test_parse_line_ls_total_and_device_lines_are_skipped():
    assert parse_line("total 32") is None  # block count, not bytes
    assert parse_line("brw-rw---- 1 root disk 8, 0 Sep 1 09:48 /dev/sda") is None


def test_parse_line_ls_without_group_falls_back_to_field_4():
    e = parse_line("-rw-r--r-- 1 mi 11358 Sep 1 09:48 LICENSE")  # ls -g / ls -o
    assert e is not None
    assert e.value == 11358
    assert e.unit == "B"
    # The breakdown must echo the size field that matched (field 4 here),
    # not the fixed field-5 token — which would print "SepB LICENSE".
    assert e.line == "11358B LICENSE"


def test_parse_line_ls_without_group_keeps_suffix_field():
    e = parse_line("-rw-r--r-- 1 mi 12K Sep 1 09:48 LICENSE")  # ls -gh / ls -oh
    assert e is not None
    assert e.value == 12
    assert e.unit == "KB"
    assert e.line == "12K LICENSE"


def test_entry_byte_conversion():
    assert parse_line("768K").num_bytes == 768 * 1024
    assert parse_line("2G").num_bytes == 2 * 1024**3
    assert parse_line("768K").mb == pytest.approx(0.75)


def test_parse_token_accepts_number_and_suffix():
    assert parse_token("1.46").value == pytest.approx(1.46)
    assert parse_token("177K").unit == "KB"
    assert parse_token("768", "KB").unit == "KB"


def test_parse_token_rejects_garbage():
    with pytest.raises(ValueError, match="not a number"):
        parse_token("foo")
    with pytest.raises(ValueError):
        parse_token("10x")


def test_parse_tokens_flattened_list():
    entries = parse_tokens(["10", "37", "6"])
    assert [e.value for e in entries] == [10, 37, 6]


def test_parse_text_counts_skipped():
    text = "10\n\n37\n   \n6\n"
    entries, skipped, multi = parse_text(text)
    assert [e.value for e in entries] == [10, 37, 6]
    assert skipped == 2  # the empty line and the whitespace-only line
    assert multi == 0


def test_parse_text_ls_l_paste():
    # A real ls -l paste: total line + two directory lines are skipped,
    # the four file sizes sum as bytes.
    text = (
        "total 32\n"
        "-rw-rw-r-- 1 mi mi 11358  9月  1 09:48 LICENSE\n"
        "-rwxrwxr-x 1 mi mi   499  9月  1 09:50 main.py*\n"
        "-rw-rw-r-- 1 mi mi  1666  9月  1 09:48 pyproject.toml\n"
        "-rw-rw-r-- 1 mi mi  3588  9月  1 09:52 README.md\n"
        "drwxrwxr-x 3 mi mi  4096  9月  1 09:50 src/\n"
        "drwxrwxr-x 3 mi mi  4096  9月  1 09:50 tests/\n"
    )
    entries, skipped, multi = parse_text(text)
    assert len(entries) == 4
    assert skipped == 3
    assert multi == 0
    assert sum(e.num_bytes for e in entries) == 11358 + 499 + 1666 + 3588


def test_parse_line_markdown_table_row():
    e = parse_line("| app.bin | 13M |")
    assert e is not None
    assert e.value == 13
    assert e.unit == "MB"
    assert e.label == "app.bin"
    assert e.line == "13M app.bin"


def test_parse_line_markdown_header_and_separator_skipped():
    assert parse_line("| image | size |") is None
    assert parse_line("|---|---:|") is None


def test_parse_line_tsv_row_with_unit_inside_cell():
    # Spreadsheet clipboard (tab-separated), unit sharing the cell.
    e = parse_line("ap\t13.5 MB")
    assert e is not None
    assert e.value == 13.5
    assert e.unit == "MB"
    assert e.label == "ap"


def test_parse_line_unit_marked_cell_beats_bare_numbers():
    e = parse_line("ap\t13.5MB\t120")
    assert e is not None
    assert e.value == 13.5
    assert e.unit == "MB"


def test_parse_line_multiple_bare_numbers_take_last_and_mark_multi():
    text = "ap 13.5 16\ncp 6 8\n"
    result = parse_text(text)
    assert [e.value for e in result.entries] == [16, 8]
    assert result.multi == 2


def test_parse_column_flag_picks_exact_column():
    result = parse_text("ap 13.5 16\ncp 6 8\n", column=2)
    assert [e.value for e in result.entries] == [13.5, 6]
    assert result.multi == 0
    # A non-numeric column yields nothing for that line.
    result = parse_text("ap 13.5 16\n", column=1)
    assert result.entries == []


def test_parse_line_thousands_separator():
    e = parse_line("1,048,576")
    assert e is not None
    assert e.value == 1048576
    assert e.unit == "MB"  # bare number uses the default unit


def test_parse_line_gibibyte_suffix():
    assert parse_line("15Gi").unit == "GB"  # free -h style
    assert parse_line("78Gi").value == 78


def test_parse_line_excludes_percent_version_date_negative():
    assert parse_line("30%") is None
    assert parse_line("v1.2") is None
    assert parse_line("2025-09-01") is None
    assert parse_line("-5") is None
    assert parse_line(".5") is None  # leading dot is NOT a number start
    # inside a row, the % column is skipped and the number next to it kept
    result = parse_text("ap 13.5 30%\n")
    assert [e.value for e in result.entries] == [13.5]
    assert result.multi == 0


def test_parse_line_summary_footer_rows_skipped():
    assert parse_line("total 32") is None
    assert parse_line("合计\t17111") is None
    assert parse_line("总计: 17111") is None


def test_parse_line_cell_punctuation_and_marks_stripped():
    assert parse_line("13.5MB，").value == 13.5  # full-width comma
    assert parse_line("| **13M** |").value == 13  # markdown bold
    assert parse_line("`768K`").value == 768  # inline code
    assert parse_line("【6MB】").value == 6  # CJK brackets


def test_parse_token_accepts_units_and_thousands():
    assert parse_token("13.5MB").value == 13.5
    assert parse_token("13.5MB").unit == "MB"
    assert parse_token("1,048,576").value == 1048576


def test_parse_text_mixed_suffixes_sum_to_bytes():
    # The ls -lh example from the spec: 13M + 1.9M + 768K + 1.7M = 17.35 MB.
    text = "13M app.bin\n1.9M audio.bin\n768K ota.bin\n1.7M sensor.bin\n"
    entries, skipped, multi = parse_text(text)
    assert skipped == 0
    assert multi == 0
    assert len(entries) == 4
    total = sum(e.num_bytes for e in entries)
    assert total == pytest.approx(17.35 * 1024 * 1024)


def test_describe_unit_default_vs_mixed():
    entries, _, _ = parse_text("10\n37\n")
    assert describe_unit(entries, "MB") == "MB"
    entries, _, _ = parse_text("10\n177K\n")
    assert describe_unit(entries, "MB") == "mixed"
