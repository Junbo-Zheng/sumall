# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Junbo Zheng

"""Value parsing and summation.

Each input line is split into cells and the size value is located inside
them, so tables paste as naturally as terminal output:

    10                        -> 10 <default unit>        (number column)
    177K  file.png            -> 177 KB                   (du / ls -lh)
    -rw-r--r-- 1 mi mi 11358 ...  -> 11358 bytes          (ls -l)
    | app.bin | 13M |     -> 13 MB, label app.bin (markdown table)
    ap\t13.5 MB               -> 13.5 MB, label ap        (spreadsheet TSV)

All values are normalized to bytes (binary MiB convention: 1 MB = 1024 KB)
before summing, so mixed-unit input adds up correctly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple

# Binary (MiB-style) units, matching du/df -h output.
UNIT_BYTES = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 * 1024,
    "GB": 1024 * 1024 * 1024,
}

# A number cell: optional thousands separators, optional size unit (K/M/G
# with optional i/B as in KiB/GB, or a bare B). Percentages, versions,
# dates, and negative numbers all fail this pattern.
_NUM_RE = re.compile(
    r"^(?P<value>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<unit>[KMGkmg]i?[Bb]?|[Bb])?$"
)

# ls -l long format: mode, nlink, owner[, group], size, date..., name.
_MODE_RE = re.compile(r"^[dlbcps\-][rwxstST\-]{9}[.+]?$")

# Summary rows must never join the sum (block counts / footer totals).
_SUMMARY_RE = re.compile(r"^(total|subtotal|sum|总计|总用量|合计)$", re.IGNORECASE)

# Formatting marks wrapped around table cells (markdown emphasis, quotes,
# CJK brackets); stripped before number matching.
_CELL_STRIP = "*_`【】「」()[]"

# Punctuation left clinging to cells by prose. Trailing side may include
# dots and commas (sentence end); the leading side must not — stripping a
# leading dot would silently turn ".5" into "5".
_PUNCT_R = "，。、；：:;,."
_PUNCT_L = "，、；：:;"


def _norm_unit(suffix: str) -> str:
    """Map a raw suffix (K, Ki, MB, GiB, B, ...) to a UNIT_BYTES key."""
    u = suffix.upper().replace("I", "")
    return {"K": "KB", "M": "MB", "G": "GB", "B": "B"}[u[0]]


def _clean_cell(cell: str) -> str:
    c = cell.strip().strip(_CELL_STRIP).strip()
    return c.rstrip(_PUNCT_R).lstrip(_PUNCT_L).strip()


def _split_cells(line: str) -> list[str]:
    """Split a line into cells: TSV first (spreadsheet clipboard), then
    markdown pipes (outer empty cells dropped), then whitespace runs."""
    if "\t" in line:
        parts = line.split("\t")
    elif "|" in line:
        parts = line.split("|")
        if parts and parts[0].strip() == "":
            parts = parts[1:]
        if parts and parts[-1].strip() == "":
            parts = parts[:-1]
    else:
        parts = line.split()
    return [_clean_cell(p) for p in parts]


@dataclass
class Entry:
    """One parsed input value."""

    value: float
    unit: str  # one of UNIT_BYTES keys
    label: str  # row/file name for the breakdown display; "" when absent
    line: str  # compact "value label" text shown in the breakdown

    @property
    def num_bytes(self) -> float:
        return self.value * UNIT_BYTES[self.unit]

    @property
    def mb(self) -> float:
        return self.num_bytes / UNIT_BYTES["MB"]


class ParseResult(NamedTuple):
    entries: list[Entry]
    skipped: int  # lines with no extractable value
    multi: int  # lines where several numbers vied and a heuristic picked one


def _entry(m: re.Match, unit: str, label: str, shown: str) -> Entry:
    value = float(m.group("value").replace(",", ""))
    line = f"{shown} {label}" if label else shown
    return Entry(value=value, unit=unit, label=label, line=line)


def _parse_ls_line(line: str) -> Entry | None:
    """Parse an ls -l long-format line; None when it is not one.

    The size field becomes the value: plain digits are bytes (ls -l), a
    K/M/G suffix is honored (ls -lh). Directory lines are skipped — their
    "size" is the directory inode size, not content — and device lines
    (major, minor instead of a size) don't match the size shape either.
    """
    tokens = line.split()
    if len(tokens) < 6 or _MODE_RE.match(tokens[0]) is None:
        return None
    if tokens[0].startswith("d"):
        return None
    # Field 5 is the size in the standard layout (mode nlink owner group
    # size); ls -g / ls -o drop one name field, so fall back to field 4.
    # Keep the matched index — the breakdown must show the size token that
    # was actually parsed, not a hardcoded field.
    idx = 4
    m = _NUM_RE.match(tokens[idx])
    if m is None:
        idx = 3
        m = _NUM_RE.match(tokens[idx])
    if m is None:
        return None
    raw_unit = m.group("unit")
    unit = _norm_unit(raw_unit) if raw_unit else "B"
    shown = tokens[idx] if raw_unit else f"{tokens[idx]}B"
    return _entry(m, unit, tokens[-1], shown)


def _parse_cells(
    line: str, default_unit: str, column: int | None
) -> tuple[Entry | None, bool]:
    """Locate the value among the line's cells.

    Returns (entry, multi) where multi means several numeric cells were
    present and one was picked by the heuristic below (the caller surfaces
    a hint so the user can verify or switch to --column).

    Selection order with several numeric cells: prefer unit-marked ones
    (13.5MB beats 120), then the last — size columns usually sit at the
    end of a row. With --column N, take exactly that column instead.
    """
    cells = _split_cells(line)
    if not cells or _SUMMARY_RE.match(cells[0]):
        return None, False
    matches = [(i, m) for i, c in enumerate(cells) if (m := _NUM_RE.match(c))]
    if not matches:
        return None, False
    if column is not None:
        picked = next((p for p in matches if p[0] == column - 1), None)
        if picked is None:
            return None, False
        idx, m = picked
        multi = False
    elif len(matches) == 1:
        idx, m = matches[0]
        multi = False
    else:
        marked = [p for p in matches if p[1].group("unit")]
        idx, m = (marked or matches)[-1]
        multi = True
    raw_unit = m.group("unit")
    unit = _norm_unit(raw_unit) if raw_unit else default_unit
    label = next(
        (c for i, c in enumerate(cells) if i != idx and not _NUM_RE.match(c)), ""
    )
    return _entry(m, unit, label, cells[idx]), multi


def _parse_line(
    line: str, default_unit: str, column: int | None
) -> tuple[Entry | None, bool]:
    # A line shaped like ls -l (mode token first) is decided by the ls
    # parser alone — its "directory/device -> skip" verdict must not fall
    # through to the generic cell parser, which would sum nlink/day
    # numbers by mistake.
    tokens = line.split()
    if len(tokens) >= 6 and _MODE_RE.match(tokens[0]):
        return _parse_ls_line(line), False
    return _parse_cells(line, default_unit, column)


def parse_line(
    line: str, default_unit: str = "MB", column: int | None = None
) -> Entry | None:
    """Parse one clipboard/stdin line; None when it holds no value.

    Recognized shapes: a number cell (anywhere in the line, with optional
    unit suffix and row label), or an ls -l long-format line. Lines with
    neither (blanks, headers, prose, directories, summary rows) are
    tolerated and counted by the caller as skipped.
    """
    entry, _multi = _parse_line(line, default_unit, column)
    return entry


def parse_token(token: str, default_unit: str = "MB") -> Entry:
    """Parse one command-line token; raises ValueError on a non-number.

    Unlike the line parsers this is strict: a typo'd argument should fail
    loudly instead of being silently skipped.
    """
    m = _NUM_RE.match(token)
    if m is None:
        raise ValueError(f"not a number: {token!r}")
    raw_unit = m.group("unit")
    unit = _norm_unit(raw_unit) if raw_unit else default_unit
    return _entry(m, unit, "", token)


def parse_text(
    text: str, default_unit: str = "MB", column: int | None = None
) -> ParseResult:
    """Parse clipboard/stdin text line by line."""
    entries: list[Entry] = []
    skipped = 0
    multi = 0
    for line in text.splitlines():
        entry, was_multi = _parse_line(line, default_unit, column)
        if entry is None:
            skipped += 1
        else:
            entries.append(entry)
            multi += was_multi
    return ParseResult(entries, skipped, multi)


def parse_tokens(tokens: list[str], default_unit: str = "MB") -> list[Entry]:
    """Parse whitespace-split argument tokens (strict: raises ValueError)."""
    return [parse_token(t, default_unit) for t in tokens]


def describe_unit(entries: list[Entry], default_unit: str) -> str:
    """The default unit name when every entry uses it, else 'mixed'."""
    return default_unit if {e.unit for e in entries} == {default_unit} else "mixed"
