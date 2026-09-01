# sumall

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

A fast, zero-dependency CLI that sums a column of numbers and reports the total in MB / KB / bytes.

Built for the everyday "add up these sizes" moment: paste from a spreadsheet, pipe `du -sh` output, or pass numbers as arguments. The per-line breakdown shows exactly which values were included, so the total is verifiable at a glance.

## Features

- **Three input sources**, first match wins: command-line arguments, piped stdin, the system clipboard (bare invocation)
- **du / ls -lh style suffixes**: `768K`, `1.9M`, `2G`, `15Gi` — mixed units are normalized to bytes before summing
- **`ls -l` long-format lines**: the size field is parsed as bytes (`ls -lh` suffixes honored); directory lines are skipped since their "size" is just the inode
- **Table pastes**: markdown tables and spreadsheet TSV (Excel / Feishu clipboard) — the number can sit in any column; when a row holds several numbers, unit-marked cells win, then the last column (`--column N` pins one)
- **Trailing labels tolerated**: `177K background.png` parses as 177 KB; the label rides along in the breakdown
- **Configurable default unit** for bare numbers (`MB` by default, override with `--unit`)
- **Per-line breakdown** plus totals in MB / KB / bytes
- Pure Python 3.10+ stdlib — no runtime dependencies, starts in ~60 ms

> [!NOTE]
> Units follow the binary (MiB) convention — 1 MB = 1024 KB = 1,048,576 bytes — matching `du -h` / `df -h` output.

## Usage

### From arguments

Arguments are strict: every token must be a number (optionally with a suffix). A typo fails loudly instead of being silently skipped. Tokens may contain spaces or newlines, so pasting a whole column as one quoted argument works too.

```console
$ ./main.py 10 37 6 1.46
来源：参数
输入：4 个数值，单位 MB

逐行明细：
   1) 10     2) 37     3) 6      4) 1.46

合计：
  54.46 MB
  55767.04 KB
  57105449 bytes
```

### From the clipboard

Copy the numbers, then run bare — no arguments needed. Linux (X11 via `xclip`/`xsel`, Wayland via `wl-paste`) and macOS (`pbpaste`) are supported; the first tool found wins.

Clipboard (and stdin) parsing is line-based and lenient: each line is split into cells (tabs, then markdown pipes, then whitespace) and the value is located among them; lines with no number — headers, separators, prose, directories, summary rows — are skipped and counted in the header.

### From stdin

```console
$ du -sh img/* | ./main.py
来源：stdin
输入：4 个数值，单位 mixed

逐行明细：
  13M app.bin       =  13.0000 MB
  1.9M audio.bin    =  1.9000 MB
  768K ota.bin      =  0.7500 MB
  1.7M sensor.bin   =  1.7000 MB

合计：
  17.35 MB
  17766.40 KB
  18192794 bytes
```

### From an `ls -l` paste

`ls -l` puts the size in field 5, not at the start of the line — a paste is recognized as long-format lines and the size field is taken as **bytes** (`ls -lh` suffixes like `12K` are honored). Directory lines and the `total` summary are skipped:

```console
$ ls -l | ./main.py
来源：stdin
输入：4 个数值，单位 mixed（3 行已跳过）

逐行明细：
  11358B LICENSE        =  0.0108 MB
  499B main.py*         =  0.0005 MB
  1666B pyproject.toml  =  0.0016 MB
  3588B README.md       =  0.0034 MB

合计：
  0.02 MB
  16.71 KB
  17111 bytes
```

### From a table paste

Markdown tables and spreadsheet clipboard (Excel / Feishu copy = TSV) put the number after the name, in any column — both work. When a row holds several numbers (`size` and `used`, or a `df -h` row), cells carrying a unit marker win over bare ones, and otherwise the last column is taken; a yellow note is printed whenever that heuristic fired, so a wrong pick is visible:

```console
$ ./main.py -c 2 < partitions.md
来源：stdin
输入：3 个数值，单位 mixed（2 行已跳过）

逐行明细：
  13M app.bin      =  13.0000 MB
  1.9M audio.bin   =  1.9000 MB
  768K ota.bin     =  0.7500 MB

合计：
  15.65 MB
  16025.60 KB
  16410214 bytes
```

`-c N` takes the Nth table column (counting all columns, not just numeric ones) instead of the heuristic; footer rows starting with `total` / `总计` / `合计` are always skipped so totals never count twice.

### Units

| Input line | Parsed as |
|---|---|
| `10` | 10 of the default unit (`--unit`, default `MB`) |
| `768K` / `768k` | 768 KB — suffix always wins over the default unit |
| `1.9M` / `15Gi` / `1,048,576` | 1.9 MB / 15 GB / 1048576 of the default unit |
| `2G` | 2 GB |
| `177K file.png` | 177 KB, label `file.png` |
| `\| app.bin \| 13M \|` | 13 MB, label `app.bin` (markdown row) |
| `ap<TAB>13.5 MB` | 13.5 MB, label `ap` (spreadsheet cell) |
| `ap 13.5 16` | several numbers: unit-marked wins, else last; `-c N` pins one |
| `-rw-r--r-- 1 mi mi 11358 Sep 1 09:48 LICENSE` | 11358 bytes, label `LICENSE` |
| `drwxr-xr-x 3 mi mi 4096 Sep 1 09:50 src/` | skipped — directory inode size, not content |
| `total 32` / `合计 17111` | skipped — block counts and footer totals |
| `30%` / `v1.2` / `2025-09-01` | skipped — not sizes |
| `hello` | skipped (stdin/clipboard) or an error (argument) |

Use `--unit B|KB|MB|GB` to change what a bare number means, e.g. `./main.py --unit KB 768 128` sums to 896 KB.

## Installation

No install is needed — run straight from a checkout:

```console
$ ./main.py 10 37 1.46
```

Or install it as a `sumall` command on your `PATH`:

```console
$ pip install -e .
$ sumall 10 37 1.46
```

## Development

```console
$ pip install -e ".[dev]"   # pytest + ruff
$ pytest                    # runs against src/ via pythonpath — no build step
$ ruff check src tests main.py
$ ruff format --check src tests main.py
```

CI (`.github/workflows/ci.yml`) lints and tests across Python 3.10–3.12 and additionally builds the wheel, installs it clean, and reruns the suite against the installed package.

## License

This project is licensed under the Apache License, Version 2.0. See
[LICENSE](LICENSE) or <https://www.apache.org/licenses/LICENSE-2.0> for the
full text.
