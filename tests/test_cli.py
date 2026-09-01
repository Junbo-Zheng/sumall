# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Junbo Zheng

import io
import sys

import pytest

from sumall import __version__
from sumall.cli import main


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_version_flag_prints_and_exits(flag, capsys):
    with pytest.raises(SystemExit) as exc:
        main([flag])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_args_sum_with_breakdown_and_totals(capsys):
    assert main(["10", "37", "6", "1.46"]) == 0
    out = capsys.readouterr().out
    assert "输入：4 个数值，单位 MB" in out
    assert "逐行明细：" in out
    assert "54.46 MB" in out
    assert "55767.04 KB" in out
    assert "57105449 bytes" in out


def test_args_multiline_and_spaced_blob(capsys):
    assert main(["10 37\n6"]) == 0
    out = capsys.readouterr().out
    assert "53.00 MB" in out


def test_args_du_style_suffixes(capsys):
    assert main(["13M", "1.9M", "768K", "1.7M"]) == 0
    out = capsys.readouterr().out
    assert "17.35 MB" in out
    assert "单位 mixed" in out


def test_unit_flag_sets_default_unit(capsys):
    assert main(["-u", "KB", "768", "128"]) == 0
    out = capsys.readouterr().out
    assert "896.00 KB" in out
    assert "0.88 MB" in out


def test_invalid_token_fails_loudly(capsys):
    assert main(["10", "foo"]) == 1
    err = capsys.readouterr().err
    assert "not a number" in err


def test_stdin_source_with_labels(capsys, monkeypatch):
    import sys as _sys

    monkeypatch.setattr(_sys, "stdin", io.StringIO("177K a.png\n157K b.png\n"))
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "来源：stdin" in out
    assert "0.33 MB" in out
    assert "334.00 KB" in out
    assert "342016 bytes" in out


def test_stdin_empty_is_an_error(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert main([]) == 1
    assert "no numbers found in stdin" in capsys.readouterr().err


def test_grid_layout_when_no_labels(capsys):
    assert main(["10", "37", "6"]) == 0
    out = capsys.readouterr().out
    assert "1) 10" in out
    assert "3) 6" in out


def test_breakdown_one_line_per_entry_when_labeled(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("177K a.png\n157K b.png\n"))
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "177K a.png" in out
    assert "=  0.1729 MB" in out


def test_ls_l_paste_end_to_end(capsys, monkeypatch):
    paste = (
        "total 32\n"
        "-rw-rw-r-- 1 mi mi 11358  9月  1 09:48 LICENSE\n"
        "-rwxrwxr-x 1 mi mi   499  9月  1 09:50 main.py*\n"
        "-rw-rw-r-- 1 mi mi  1666  9月  1 09:48 pyproject.toml\n"
        "-rw-rw-r-- 1 mi mi  3588  9月  1 09:52 README.md\n"
        "drwxrwxr-x 3 mi mi  4096  9月  1 09:50 src/\n"
        "drwxrwxr-x 3 mi mi  4096  9月  1 09:50 tests/\n"
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(paste))
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "输入：4 个数值，单位 mixed（3 行已跳过）" in out
    assert "11358B LICENSE" in out
    assert "0.02 MB" in out
    assert "16.71 KB" in out
    assert "17111 bytes" in out


def test_markdown_table_paste(capsys, monkeypatch):
    paste = (
        "| image | size |\n"
        "|---|---|\n"
        "| app.bin | 13M |\n"
        "| audio.bin | 1.9M |\n"
        "| ota.bin | 768K |\n"
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(paste))
    assert main([]) == 0
    out = capsys.readouterr().out
    # header + separator rows skipped, no multi-column warning
    assert "输入：3 个数值，单位 mixed（2 行已跳过）" in out
    assert "多列数值" not in out
    assert "13M app.bin" in out
    assert "15.65 MB" in out
    assert "16025.60 KB" in out
    assert "16410214 bytes" in out


def test_df_h_paste_multi_column_heuristic(capsys, monkeypatch):
    paste = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/sda1       916G  113G  757G  13% /\n"
        "tmpfs            78G   17M   78G   0% /dev/shm\n"
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(paste))
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "多列数值" in out  # heuristic fired; the note teaches -c
    assert "757G /dev/sda1" in out
    assert "78G tmpfs" in out
    total = 835 * 1024**3
    assert f"{total / 1024:.2f} KB" in out
    assert f"{round(total)} bytes" in out


def test_column_flag_overrides_heuristic(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("ap 13.5 16\ncp 6 8\n"))
    assert main(["-c", "2"]) == 0
    out = capsys.readouterr().out
    assert "19.50 MB" in out  # 13.5 + 6, the second column
    assert "多列数值" not in out


def test_column_flag_must_be_positive(capsys):
    with pytest.raises(SystemExit):
        main(["-c", "0"])
