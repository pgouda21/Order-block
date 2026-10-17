"""CLAUDE.md rule 1: no order or position-mutating API may appear anywhere in the code."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from marketboard.data.alpaca_client import ReadOnlyAlpaca

REPO_ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".sh", ".toml", ".yaml", ".yml"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    ".wrangler",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}

FORBIDDEN = re.compile(
    r"submit_order|\w*OrderRequest\b|close_position|close_all_positions|cancel_order\w*"
    r"|replace_order\w*|exercise_options_position"
)
ALPACA_IMPORT = re.compile(r"^\s*(?:from|import)\s+alpaca\b", re.MULTILINE)
ALLOWED_ALPACA_IMPORTER = REPO_ROOT / "scanner" / "marketboard" / "data" / "alpaca_client.py"


def _source_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        if path.suffix not in SCAN_SUFFIXES or not path.is_file():
            continue
        if SKIP_DIRS.intersection(path.relative_to(REPO_ROOT).parts):
            continue
        if path.resolve() != SELF:
            files.append(path)
    return files


def test_scan_covers_the_repo() -> None:
    scanned = {p.relative_to(REPO_ROOT).as_posix() for p in _source_files()}
    assert "scanner/marketboard/data/alpaca_client.py" in scanned
    assert "worker/src/index.ts" in scanned


@pytest.mark.parametrize(
    "sample",
    [
        "client.submit_order(req)",
        "from alpaca.trading.requests import MarketOrderRequest",
        "LimitOrderRequest(symbol='X')",
        "StopLimitOrderRequest",
        "tc.close_position('X')",
        "tc.close_all_positions()",
        "tc.cancel_orders()",
        "tc.cancel_order_by_id(i)",
        "tc.replace_order_by_id(i, r)",
    ],
)
def test_pattern_catches_trading_calls(sample: str) -> None:
    assert FORBIDDEN.search(sample)


def test_no_trading_calls_in_repo() -> None:
    hits = []
    for path in _source_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not hits, "order/position-mutating API found:\n" + "\n".join(hits)


def test_only_alpaca_client_imports_alpaca() -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _source_files()
        if path.suffix == ".py"
        and path.resolve() != ALLOWED_ALPACA_IMPORTER
        and ALPACA_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"import alpaca only via data/alpaca_client.py: {offenders}"


def test_wrapper_exposes_no_trading_client() -> None:
    public = {name for name in dir(ReadOnlyAlpaca) if not name.startswith("_")}
    assert public == {"clock"}
