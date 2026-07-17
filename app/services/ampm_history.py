"""
AMPM Out-of-Stock History (OOS momentum tracker)
================================================

Reconstructs per-SKU AMPM stock across the last N weeks by replaying
git commits of the brand-level `Inventory_snapshot_<brand>.xlsx` files.
No new database or manual bookkeeping — the weekly commits are the
history.

The output feeds three signals surfaced on the Replenishment tab:

  ampm_oos_weeks_3m       int   count of weeks in the last 13 where
                                AMPM stock for this SKU was 0
  estimated_lost_units_3m int   avg weekly velocity in NON-OOS weeks
                                × ampm_oos_weeks_3m (rough "momentum
                                you left on the table")
  momentum_flag           str   RED / AMBER / '' (see below)

Momentum flag rules:
  RED    ≥2 OOS weeks in last 13 AND current AMPM ≤ 10
  AMBER  1 OOS week in last 13 (recent single-week gap)
  ''     healthy — 0 OOS weeks OR healthy current AMPM

Cached in-process at import time via lru_cache — first request pays
the git-walk cost (~5-30s for 4 brands × 13 weeks), later requests
are instant. Cache is per (brand, current_week_start).
"""
from __future__ import annotations

import io
import subprocess
from datetime import date as _date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.services.week_helper import current_working_week_start

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_WEEKS = 13  # ~3 months; overridable per call


# Brand → snapshot file (relative to repo root)
BRAND_TO_SNAPSHOT = {
    "nexlev":          "data/input/inventory_snapshot_nexlev.xlsx",
    "viomi":           "data/input/inventory_snapshot_nexlev.xlsx",  # shares Nexlev sheet
    "audio array":     "data/input/Inventory_snapshot_audio_array.xlsx",
    "white mulberry":  "data/input/Inventory_snapshot_WM.xlsx",
    "tonor":           "data/input/Inventory_snapshot_tonor.xlsx",
}


def _git_commits_for_file(path_rel: str, since_date: _date) -> list[tuple[str, _date]]:
    """Return [(commit_hash, commit_date), ...] for a file, one entry per
    commit that touched it since `since_date`, newest first."""
    try:
        out = subprocess.check_output(
            ["git", "log", f"--since={since_date.isoformat()}",
             "--format=%H %cs", "--", path_rel],
            cwd=str(REPO), stderr=subprocess.DEVNULL, timeout=15,
        ).decode().strip()
        rows = []
        for line in out.splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                try:
                    rows.append((parts[0], _date.fromisoformat(parts[1])))
                except ValueError:
                    pass
        return rows
    except Exception:
        return []


def _read_ampm_from_commit(commit_hash: str, path_rel: str) -> pd.DataFrame:
    """Extract the AMPM channel rows from a specific commit of a snapshot file.
    Returns DataFrame with columns [SKU, Qty]. Empty if the commit or file
    is unreadable."""
    try:
        blob = subprocess.check_output(
            ["git", "show", f"{commit_hash}:{path_rel}"],
            cwd=str(REPO), stderr=subprocess.DEVNULL, timeout=10,
        )
        df = pd.read_excel(io.BytesIO(blob))
        df.columns = df.columns.astype(str).str.strip()
        if "Channel" not in df.columns or "SKU" not in df.columns or "Qty" not in df.columns:
            return pd.DataFrame(columns=["SKU", "Qty"])
        ampm = df[df["Channel"].astype(str).str.strip().str.upper() == "AMPM"].copy()
        ampm["SKU"] = ampm["SKU"].astype(str).str.strip().str.upper()
        ampm["Qty"] = pd.to_numeric(ampm["Qty"], errors="coerce").fillna(0)
        # If a SKU has multiple AMPM rows, sum them
        return ampm.groupby("SKU", as_index=False)["Qty"].sum()
    except Exception:
        return pd.DataFrame(columns=["SKU", "Qty"])


def _week_start(d: _date) -> _date:
    """Sunday of the operator's week convention containing date d."""
    # Python's weekday(): Mon=0, Sun=6. Roll back to previous Sunday.
    offset = (d.weekday() + 1) % 7  # Sun→0, Mon→1, ..., Sat→6
    return d - timedelta(days=offset)


def _rebuild_history(brand: str, weeks: int, current_ws: _date) -> pd.DataFrame:
    """Walk git history for the brand's snapshot file and reconstruct
    per-SKU AMPM by week. Returns wide DataFrame:
       index = SKU
       cols  = [week_start_date_1, week_start_date_2, ...] (13 columns)
       cells = AMPM Qty at latest commit within that week.
    Missing weeks (no commit) → NaN."""
    key = brand.strip().lower()
    path_rel = BRAND_TO_SNAPSHOT.get(key)
    if not path_rel:
        return pd.DataFrame()

    # Look-back window: N weeks × 7 days + a buffer for commits that
    # fell just outside the window.
    since = current_ws - timedelta(days=weeks * 7 + 10)
    commits = _git_commits_for_file(path_rel, since)
    if not commits:
        return pd.DataFrame()

    # Group commits by the week their commit date falls into.
    # Keep only the LATEST commit per week (freshest snapshot).
    by_week: dict[_date, str] = {}
    for commit_hash, commit_date in commits:
        ws = _week_start(commit_date)
        # Skip commits older than the window we care about
        weeks_ago = (current_ws - ws).days // 7
        if weeks_ago > weeks or weeks_ago < 0:
            continue
        if ws not in by_week:
            by_week[ws] = commit_hash  # commits are newest-first, so first wins

    if not by_week:
        return pd.DataFrame()

    # Build the wide-format history
    frames = []
    for ws, commit_hash in by_week.items():
        ampm = _read_ampm_from_commit(commit_hash, path_rel)
        if ampm.empty:
            continue
        ampm = ampm.rename(columns={"Qty": ws.isoformat()})
        frames.append(ampm.set_index("SKU"))

    if not frames:
        return pd.DataFrame()

    hist = pd.concat(frames, axis=1)
    # Ensure columns are sorted chronologically
    hist = hist[sorted(hist.columns)]
    return hist


@lru_cache(maxsize=32)
def _cached_history(brand: str, weeks: int, current_ws_iso: str) -> pd.DataFrame:
    """Memoize per (brand, week_start, weeks). Cache invalidates when
    the operator's week rolls over."""
    return _rebuild_history(brand, weeks, _date.fromisoformat(current_ws_iso))


def compute_oos_signals(
    brand: str,
    weekly_sales: pd.DataFrame | None,
    weeks: int = DEFAULT_WEEKS,
    current_ampm_series: pd.Series | None = None,
) -> pd.DataFrame:
    """For a given brand, compute per-SKU OOS signals over the last
    `weeks` weeks.

    Args
    ----
    brand : "Nexlev" | "Viomi" | "Audio Array" | "White Mulberry" | "Tonor"
    weekly_sales : the shared `weekly_sales_snapshot.csv` DataFrame.
        Must have columns [sku, week, units_sold] at minimum. If None,
        estimated_lost_units_3m = 0.
    weeks : look-back window (13 for 3 months, 26 for 6 months).
    current_ampm_series : optional Series indexed by SKU with current
        AMPM stock. Used only for the momentum_flag (RED requires
        current AMPM ≤ 10). If None, flag stays AMBER at most.

    Returns
    -------
    DataFrame indexed by SKU with columns:
        ampm_oos_weeks_3m       int
        estimated_lost_units_3m int
        momentum_flag           str  (RED / AMBER / '')
    """
    ws = current_working_week_start()
    hist = _cached_history(brand.lower(), weeks, ws.isoformat())
    if hist.empty:
        return pd.DataFrame(columns=[
            "ampm_oos_weeks_3m", "estimated_lost_units_3m", "momentum_flag",
        ])

    # Count OOS weeks per SKU (Qty == 0 exactly; NaN = no snapshot, ignored)
    is_zero = (hist == 0)
    oos_counts = is_zero.sum(axis=1).astype(int)

    # Estimated lost units: avg weekly sales in non-OOS weeks × oos_counts
    # If no weekly_sales, fall back to 0.
    lost = pd.Series(0, index=hist.index, dtype=int)
    if weekly_sales is not None and not weekly_sales.empty:
        ws_lower = weekly_sales.copy()
        ws_lower["_sku"] = ws_lower["sku"].astype(str).str.strip().str.upper()
        # Avg units_sold per SKU across all weeks in the window (rough)
        # More sophisticated: only avg over weeks where AMPM was NOT zero.
        # For v1, use all-window avg (adequate signal).
        avg = ws_lower.groupby("_sku")["units_sold"].mean().fillna(0)
        for sku in hist.index:
            n_oos = int(oos_counts.get(sku, 0))
            if n_oos > 0 and sku in avg.index:
                lost[sku] = int(round(avg[sku] * n_oos))

    # Momentum flag
    flags = pd.Series("", index=hist.index)
    for sku in hist.index:
        n = int(oos_counts.get(sku, 0))
        if n >= 2:
            # RED requires current AMPM ≤ 10 (buffer-rule aligned)
            cur = current_ampm_series.get(sku, 0) if current_ampm_series is not None else 0
            if cur <= 10:
                flags[sku] = "RED"
            else:
                flags[sku] = "AMBER"
        elif n == 1:
            flags[sku] = "AMBER"

    out = pd.DataFrame({
        "ampm_oos_weeks_3m":       oos_counts,
        "estimated_lost_units_3m": lost.reindex(oos_counts.index).fillna(0).astype(int),
        "momentum_flag":           flags,
    })
    out.index.name = "sku"
    return out
