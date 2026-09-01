# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Junbo Zheng

"""CLI entry point: pick the input source (arguments > piped stdin >
clipboard), parse the numbers, and print the breakdown + totals."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version

from .core import UNIT_BYTES, Entry, describe_unit, parse_text, parse_tokens


class SumallError(Exception):
    """Fatal input problem; the message is shown to the user as-is."""


def _version() -> str:
    # Installed metadata is the source of truth; fall back to the in-tree
    # __init__ string for zero-install runs (main.py shim, editable checkouts).
    try:
        return version("sumall")
    except PackageNotFoundError:
        from . import __version__

        return __version__


def _read_clipboard() -> str:
    """Return the system clipboard text, trying common tools in order.

    Supports Linux X11 (xclip/xsel), Wayland (wl-paste), and macOS (pbpaste).
    Raises SumallError with an install hint when no usable tool is found.
    """
    candidates = [
        ["xclip", "-o", "-selection", "clipboard"],
        ["xsel", "-b", "-o"],
        ["wl-paste", "--no-newline"],
        ["pbpaste"],
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if out.returncode == 0:
                    return out.stdout
            except (subprocess.SubprocessError, OSError):
                continue
    raise SumallError(
        "no clipboard tool found; install xclip/xsel (X11) or wl-clipboard "
        "(Wayland), or pass numbers as arguments / via stdin"
    )


_SOURCE_ZH = {"arguments": "参数", "stdin": "stdin", "clipboard": "剪贴板"}


def _color_codes() -> dict[str, str]:
    """ANSI prefix map, empty when output is piped or NO_COLOR is set."""
    if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
        return {
            "dim": "\033[2m",
            "bold": "\033[1m",
            "yellow": "\033[33m",
            "reset": "\033[0m",
        }
    return {"dim": "", "bold": "", "yellow": "", "reset": ""}


def _breakdown_lines(entries: list[Entry]) -> list[str]:
    """Per-line breakdown: a compact 7-per-row grid when no entry carries a
    label (the common number-column paste), one line per entry otherwise so
    labeled du/ls -lh output stays recognizable."""
    if not any(e.label for e in entries):
        cells = [f"{i:>2}) {e.line.strip()}" for i, e in enumerate(entries, 1)]
        width = max(len(c) for c in cells) + 2
        return [
            "  " + "".join(c.ljust(width) for c in cells[i : i + 7]).rstrip()
            for i in range(0, len(cells), 7)
        ]
    width = max(len(e.line.strip()) for e in entries)
    return [f"  {e.line.strip().ljust(width)}  =  {e.mb:.4f} MB" for e in entries]


def _print_report(
    entries: list[Entry],
    skipped: int,
    default_unit: str,
    source: str,
    color: dict[str, str],
    multi: int = 0,
) -> None:
    dim, bold, reset = color["dim"], color["bold"], color["reset"]

    header = f"输入：{len(entries)} 个数值，单位 {describe_unit(entries, default_unit)}"
    if skipped:
        header += f"（{skipped} 行已跳过）"
    print(f"{dim}来源：{_SOURCE_ZH[source]}{reset}")
    print(header)
    if multi:
        print(f"{color['yellow']}多列数值：默认取最后一列（-c N 指定第 N 列）{reset}")
    print()
    print("逐行明细：")
    for line in _breakdown_lines(entries):
        print(line)
    print()
    total_bytes = sum(e.num_bytes for e in entries)
    print("合计：")
    print(f"  {bold}{total_bytes / UNIT_BYTES['MB']:.2f} MB{reset}")
    print(f"  {total_bytes / UNIT_BYTES['KB']:.2f} KB")
    print(f"  {round(total_bytes)} bytes")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="sumall",
        description=f"sumall {_version()} — sum numbers and report the total "
        "in MB / KB / bytes.",
        epilog=(
            "input sources, first match wins:\n"
            "  sumall 10 37 1.46   numbers as arguments (spaces/newlines ok)\n"
            "  du -sh * | sumall   piped stdin\n"
            "  sumall              the system clipboard\n"
            "\n"
            "values may carry a du-style K/M/G suffix; bare numbers use the\n"
            "unit set by --unit (default MB)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"sumall {_version()}",
        help="show the version and exit",
    )
    p.add_argument(
        "-u",
        "--unit",
        choices=["B", "KB", "MB", "GB"],
        default="MB",
        help="unit for bare numbers without a K/M/G suffix (default: MB)",
    )
    p.add_argument(
        "-c",
        "--column",
        type=int,
        metavar="N",
        help="1-based column to take when a line holds several numbers "
        "(table pastes); counts table columns, not just numeric ones",
    )
    p.add_argument(
        "values",
        nargs="*",
        metavar="NUM",
        help="numbers to sum; omit to read the clipboard (or pipe stdin)",
    )
    args = p.parse_args(argv)
    if args.column is not None and args.column < 1:
        p.error("--column must be >= 1")

    try:
        if args.values:
            source = "arguments"
            tokens = [t for v in args.values for t in v.split()]
            entries = parse_tokens(tokens, args.unit)
            skipped = multi = 0
        elif not sys.stdin.isatty():
            source = "stdin"
            entries, skipped, multi = parse_text(
                sys.stdin.read(), args.unit, args.column
            )
        else:
            source = "clipboard"
            entries, skipped, multi = parse_text(
                _read_clipboard(), args.unit, args.column
            )
    except (SumallError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not entries:
        print(f"error: no numbers found in {source}", file=sys.stderr)
        return 1

    _print_report(entries, skipped, args.unit, source, _color_codes(), multi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
