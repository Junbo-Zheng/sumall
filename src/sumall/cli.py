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
    # Prefer the session's native tool: on Wayland, xclip/xsel go through
    # XWayland and can hang for seconds, while wl-paste answers in ~5ms.
    if os.environ.get("WAYLAND_DISPLAY") or (
        os.environ.get("XDG_SESSION_TYPE") == "wayland"
    ):
        candidates.sort(key=lambda cmd: cmd[0] != "wl-paste")
    for cmd in candidates:
        if shutil.which(cmd[0]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if out.returncode == 0:
                    return out.stdout
            except (subprocess.SubprocessError, OSError):
                continue
    raise SumallError(
        "no clipboard tool found; install xclip/xsel (X11) or wl-clipboard "
        "(Wayland), or pass numbers as arguments / via stdin"
    )


_SOURCE = {"arguments": "arguments", "stdin": "stdin", "clipboard": "clipboard"}


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


def _breakdown_lines(entries: list[Entry], plain: bool = False) -> list[str]:
    """Per-line breakdown: a compact 7-per-row grid when no entry carries a
    label (the common number-column paste), one line per entry otherwise so
    labeled du/ls -lh output stays recognizable."""
    if not any(e.label for e in entries):
        cells = [f"{i:>2}) {e.line.strip()}" for i, e in enumerate(entries, 1)]
        width = max(len(c) for c in cells) + 2
        return [
            "  " + "".join(c.ljust(width) for c in cells[i : i + 8]).rstrip()
            for i in range(0, len(cells), 8)
        ]
    width = max(len(e.line.strip()) for e in entries)
    lines = []
    for e in entries:
        if plain:
            shown = f"{e.value:g}"
        elif e.unit == "%":
            shown = f"{e.value:g} %"
        else:
            shown = f"{e.mb:.4f} MB"
        lines.append(f"  {e.line.strip().ljust(width)}  =  {shown}")
    return lines


def _print_report(
    entries: list[Entry],
    skipped: int,
    default_unit: str,
    source: str,
    color: dict[str, str],
    multi: int = 0,
    unitless: bool = False,
) -> None:
    dim, bold, reset = color["dim"], color["bold"], color["reset"]

    # Every value was a bare number and no --unit was given: these are not
    # sizes, so the total is the raw sum with no unit and no conversion.
    plain = unitless and all(e.bare for e in entries)
    n = len(entries)
    if plain:
        header = f"input: {n} value{'s' if n != 1 else ''}"
    else:
        unit = describe_unit(entries, default_unit)
        header = f"input: {n} value{'s' if n != 1 else ''}, unit {unit}"
    if skipped:
        header += f" ({skipped} line{'s' if skipped != 1 else ''} skipped)"
    print(f"{dim}source: {_SOURCE[source]}{reset}")
    print(header)
    if multi:
        print(
            f"{color['yellow']}multiple numeric columns: "
            f"last one taken by default (-c N picks column N){reset}"
        )
    print()
    print("breakdown:")
    for line in _breakdown_lines(entries, plain):
        print(line)
    print()
    total_bytes = sum(e.num_bytes for e in entries)
    print("total:")
    if plain:
        print(f"  {bold}{sum(e.value for e in entries):.2f}{reset}")
        return
    if {e.unit for e in entries} == {"%"}:
        # Percent values are not sizes; sum them as-is, no MB/KB/bytes.
        print(f"  {bold}{total_bytes:.2f} %{reset}")
        return
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
            "values may carry a du-style K/M/G suffix or %; bare numbers sum\n"
            "unitless unless --unit anchors them (or a suffix-marked value\n"
            "sets the context)"
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
        default=None,
        help="unit for bare numbers without a K/M/G suffix; omit to sum "
        "bare numbers unitless (a unit-marked value anchors them to MB)",
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
    # Bare numbers are unitless unless the user says otherwise; a size unit
    # is only needed when parsing mixes them with unit-marked values.
    default_unit = args.unit or "MB"
    unitless = args.unit is None

    try:
        if args.values:
            source = "arguments"
            tokens = [t for v in args.values for t in v.split()]
            entries = parse_tokens(tokens, default_unit)
            skipped = multi = 0
        elif not sys.stdin.isatty():
            source = "stdin"
            entries, skipped, multi = parse_text(
                sys.stdin.read(), default_unit, args.column
            )
        else:
            source = "clipboard"
            entries, skipped, multi = parse_text(
                _read_clipboard(), default_unit, args.column
            )
    except (SumallError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not entries:
        print(f"error: no numbers found in {source}", file=sys.stderr)
        return 1

    _print_report(
        entries, skipped, default_unit, source, _color_codes(), multi, unitless
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
