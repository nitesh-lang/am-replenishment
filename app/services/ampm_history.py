"""
AMPM Momentum Tracker — two-layer signal (OOS + Thinning)
=========================================================

Reconstructs per-SKU AMPM stock across the last N weeks by replaying
git commits of the brand-level `Inventory_snapshot_<brand>.xlsx` files.
Combines with per-week sales to catch two distinct failure modes:

  LAYER 1 — ZEROED (hard OOS): weeks where AMPM was literally 0.
            The SKU couldn't ship anything.
  LAYER 2 — THINNING (slow bleed): weeks where AMPM > 0 but so
            low that Amazon likely throttled the listing.
            Concretely: 0 < AMPM ≤ 2 × avg-weekly-velocity AND
            that week's actual sales < 70% of peak week.

Output columns (surfaced on the Replenishment tab):

  oos_weeks_3m       int   Layer-1 count (AMPM=0 weeks)
  thin_weeks_3m      int   Layer-2 count (thinning without hitting 0)
  lost_units_3m      int   COMBINED: for each flagged week, sum of
                           max(0, benchmark − actual_sales_that_week)
  momentum_flag      str   RED / AMBER / '' (see rules below)

lost_basis — what "benchmark" means (operator 2026-08-27: "dont take peak
numbers, just sales vs cover selected basis as simple math, also give option
if last 2 week or considering peak days" — scoped to the WATCHLIST only:
"hope we are doing changes in watchlist not other modules"):
  "peak" (DEFAULT here) — the historical behaviour. Default stays peak so
         the Replenishment tab and every other existing caller render
         byte-identical numbers; ONLY replen_watchlist passes a different
         basis. Do not change this default without the operator.
  "avg"  — the SKU's average weekly sales over the momentum window. The
         watchlist's default: peak-based counterfactuals booked absurd
         losses (AM-W45: 387 "lost" units, of which 122 assumed a 40-unit
         week would have been a 162-unit week).
  "2wk"  — trailing-2-week average, for "what is it doing right now".
NOTE: lost_basis changes only the SIZE of the loss. Which weeks get flagged
(OOS / THIN, and thus momentum_flag) is unchanged — THIN detection still
compares against 70% of peak, which is a detector, not a valuation.

Momentum flag:
  RED    "Bleeding"  — oos_weeks ≥ 2
         "Starving"  — thin_weeks ≥ 3
  AMBER  "At risk"   — oos_weeks == 1 OR 1 ≤ thin_weeks ≤ 2
  ''     healthy

Cached per (brand, current_week_start).
"""
from __future__ import annotations

import io
import re
import subprocess
from datetime import date as _date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.services.week_helper import current_working_week_start

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_WEEKS = 13  # ~3 months; extendable to 26 later

BRAND_TO_SNAPSHOT = {
    "nexlev":          "data/input/inventory_snapshot_nexlev.xlsx",
    "viomi":           "data/input/inventory_snapshot_nexlev.xlsx",
    "audio array":     "data/input/Inventory_snapshot_audio_array.xlsx",
    "white mulberry":  "data/input/Inventory_snapshot_WM.xlsx",
    "tonor":           "data/input/Inventory_snapshot_tonor.xlsx",
}

BRAND_TO_SALES_TAG = {
    # weekly_sales_snapshot['brand'] value → account we use here
    "nexlev":          "Nexlev",
    "viomi":           "Nexlev",           # snapshot merges Viomi under Nexlev; Viomi bypasses this via raw FBA Sales files
    "audio array":     "Audio Array",
    "white mulberry":  "White Mulberry",
    "tonor":           "Tonor",
}

# Accounts that must read raw per-week FBA Sales CSVs instead of the
# merged weekly_sales_snapshot.csv (which brand-tags Viomi rows as
# "Nexlev" because both Seller Central accounts share the catalog).
# Filename stems match fc_planning.ACCOUNT_FILES aliases.
RAW_SHIPMENTS_ACCOUNTS = {
    "viomi": ["vibc", "viomi"],
}

_FBA_SALES_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "input" / "FBA Sales"
_SKU_PREFIX_RE  = re.compile(r"^(FBAM|FBA|FBM|FBK|FBP|FBS|FBO)", re.IGNORECASE)

# Layer-2 thresholds — dialable
COVER_WEEKS_THIN = 2       # AMPM ≤ 2 × avg velocity → "thin"
PEAK_DROP_RATIO  = 0.70    # sales that week < 70% of peak → confirmed


def _git_commits_for_file(path_rel: str, since_date: _date) -> list[tuple[str, _date]]:
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
        return ampm.groupby("SKU", as_index=False)["Qty"].sum()
    except Exception:
        return pd.DataFrame(columns=["SKU", "Qty"])


def _week_start(d: _date) -> _date:
    """Sunday of the operator's week containing d."""
    offset = (d.weekday() + 1) % 7  # Sun→0
    return d - timedelta(days=offset)


def _sun_sat_week_num(d: _date) -> int:
    """Operator's Sun-Sat week number (shift by +1 day, then ISO week)."""
    return (d + timedelta(days=1)).isocalendar().week


def _ampm_history(brand: str, weeks: int, current_ws: _date) -> pd.DataFrame:
    """Return wide DataFrame: index=SKU, cols=ISO-date of week_start,
    cells=AMPM Qty. Missing weeks = NaN."""
    key = brand.strip().lower()
    path_rel = BRAND_TO_SNAPSHOT.get(key)
    if not path_rel:
        return pd.DataFrame()
    since = current_ws - timedelta(days=weeks * 7 + 10)
    commits = _git_commits_for_file(path_rel, since)
    if not commits:
        return pd.DataFrame()
    by_week: dict[_date, str] = {}
    for commit_hash, commit_date in commits:
        ws = _week_start(commit_date)
        weeks_ago = (current_ws - ws).days // 7
        if 0 <= weeks_ago <= weeks and ws not in by_week:
            by_week[ws] = commit_hash
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
    hist = hist[sorted(hist.columns)]
    return hist


def _weekly_sales_by_sku(
    weekly_sales: pd.DataFrame,
    brand: str,
    week_numbers: list[int],
    master_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Aggregate weekly_sales_snapshot to (SKU × week_num) for one brand.

    weekly_sales_snapshot rows for the Amazon channel typically don't
    carry the `sku` column — they're attributed by ASIN. So we cascade:
    ASIN → SKU (via master), then SKU direct (1p channel), then Model
    (via master). Master is the SKU⇄ASIN⇄Model dictionary.
    Returns wide DataFrame: index=SKU, cols=week_num, cells=units_sold.
    """
    if weekly_sales is None or weekly_sales.empty:
        return pd.DataFrame()
    brand_tag = BRAND_TO_SALES_TAG.get(brand.lower())
    df = weekly_sales.copy()
    if brand_tag and "brand" in df.columns:
        df = df[df["brand"].astype(str).str.strip() == brand_tag]
    if "week_num" not in df.columns:
        df["week_num"] = (
            df["week"].astype(str).str.extract(r"(\d+)").astype(float).fillna(0).astype(int)
        )
    df = df[df["week_num"].isin(week_numbers)]
    df["_asin"] = df.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    df["_sku"]  = df.get("sku",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    df["_model"]= df.get("model","").astype(str).str.strip().str.upper()
    df["units_sold"] = pd.to_numeric(df["units_sold"], errors="coerce").fillna(0)

    # Canonicalize every row's SKU via master lookup so FC-prefix
    # variants (FBA/FBM/FBP/FBK) all resolve to master's canonical SKU.
    # Reference: memory `reference_master_alignment_hierarchy.md`.
    if master_df is not None and not master_df.empty:
        m = master_df.copy()
        m.columns = m.columns.astype(str).str.strip()
        m["_sku"]   = m.get("SKU", "").astype(str).str.strip().str.upper()
        m["_asin"]  = m.get("ASIN", "").astype(str).str.strip().str.upper()
        m["_model"] = m.get("Model","").astype(str).str.strip().str.upper()
        asin_to_sku  = dict(zip(m["_asin"],  m["_sku"]))
        model_to_sku = dict(zip(m["_model"], m["_sku"]))
        asin_to_sku.pop("", None)
        model_to_sku.pop("", None)

        def _canonical(row):
            # Priority: ASIN → SKU (master), else direct SKU, else Model → SKU
            if row["_asin"] and row["_asin"] in asin_to_sku:
                return asin_to_sku[row["_asin"]]
            if row["_sku"]:
                return row["_sku"]
            if row["_model"] and row["_model"] in model_to_sku:
                return model_to_sku[row["_model"]]
            return ""
        df["SKU"] = df.apply(_canonical, axis=1)
    else:
        df["SKU"] = df["_sku"]

    all_rows = df[df["SKU"] != ""][["SKU", "week_num", "units_sold"]]
    if all_rows.empty:
        return pd.DataFrame()
    piv = (
        all_rows.groupby(["SKU", "week_num"], as_index=False)["units_sold"]
                .sum()
                .pivot(index="SKU", columns="week_num", values="units_sold")
                .fillna(0)
    )
    piv.index.name = "SKU"
    return piv


def _weekly_sales_from_raw_shipments(
    brand: str,
    week_numbers: list[int],
    master_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """Read per-week FBA Sales/Week NN/<alias>.csv for accounts whose
    Seller Central account is distinct but shares a catalog with another
    (Nexlev/Viomi). Aggregates Merchant SKU × week_num.

    SKU canonicalization: strip FC prefix (FBA/FBM/FBK/FBP/FBS/FBO/FBAM)
    on both raw SKU and master SKU, match on the numeric tail, return
    master's canonical SKU. Falls through to raw SKU if unmatched.
    """
    aliases = {a.strip().lower() for a in RAW_SHIPMENTS_ACCOUNTS.get(brand.lower(), [])}
    if not aliases or not _FBA_SALES_ROOT.exists():
        return pd.DataFrame()
    week_pat = re.compile(r"^Week\s+(\d+)$", re.IGNORECASE)
    frames: list[pd.DataFrame] = []
    for wf in _FBA_SALES_ROOT.iterdir():
        if not wf.is_dir():
            continue
        m = week_pat.match(wf.name)
        if not m:
            continue
        wnum = int(m.group(1))
        if wnum not in week_numbers:
            continue
        for csv in wf.glob("*.csv"):
            if csv.stem.strip().lower() in aliases:
                try:
                    d = pd.read_csv(csv, low_memory=False)
                    d["week_num"] = wnum
                    frames.append(d)
                except Exception as e:
                    print(f"⚠️ ampm_history raw read failed {csv}: {e}")
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.columns = df.columns.astype(str).str.strip()
    if "Merchant SKU" not in df.columns or "Shipped Quantity" not in df.columns:
        return pd.DataFrame()
    df["_sku"]       = df["Merchant SKU"].astype(str).str.strip().str.upper()
    df["units_sold"] = pd.to_numeric(df["Shipped Quantity"], errors="coerce").fillna(0)

    def _strip(s: str) -> str:
        return _SKU_PREFIX_RE.sub("", s or "").upper()

    if master_df is not None and not master_df.empty:
        m = master_df.copy()
        m.columns = m.columns.astype(str).str.strip()
        m["_sku"]       = m.get("SKU", "").astype(str).str.strip().str.upper()
        m["_stripped"]  = m["_sku"].map(_strip)
        stripped_to_canon = dict(zip(m["_stripped"], m["_sku"]))
        stripped_to_canon.pop("", None)

        def _canon(raw: str) -> str:
            s = _strip(raw)
            if s and s in stripped_to_canon:
                return stripped_to_canon[s]
            return raw
        df["SKU"] = df["_sku"].map(_canon)
    else:
        df["SKU"] = df["_sku"]

    df = df[df["SKU"] != ""]
    if df.empty:
        return pd.DataFrame()
    piv = (
        df.groupby(["SKU", "week_num"], as_index=False)["units_sold"]
          .sum()
          .pivot(index="SKU", columns="week_num", values="units_sold")
          .fillna(0)
    )
    piv.index.name = "SKU"
    return piv


@lru_cache(maxsize=32)
def _cached_signals(brand_key: str, weeks: int, current_ws_iso: str,
                    sales_hash: int, master_hash: int,
                    lost_basis: str = "peak") -> pd.DataFrame:
    """Memoize the whole compute. Module-level slots hold the sales +
    master DataFrames (not part of cache key because they're heavy).
    lost_basis IS part of the key — different bases are different results."""
    global _SALES_CACHE, _MASTER_CACHE
    return _compute(_SALES_CACHE, _MASTER_CACHE, brand_key, weeks,
                    _date.fromisoformat(current_ws_iso),
                    lost_basis=lost_basis)


_SALES_CACHE: pd.DataFrame | None = None
_MASTER_CACHE: pd.DataFrame | None = None


def _compute(
    weekly_sales: pd.DataFrame | None,
    master_df: pd.DataFrame | None,
    brand: str,
    weeks: int,
    current_ws: _date,
    lost_basis: str = "peak",
) -> pd.DataFrame:
    hist = _ampm_history(brand, weeks, current_ws)
    if hist.empty:
        return pd.DataFrame(columns=[
            "oos_weeks_3m", "thin_weeks_3m",
            "lost_units_3m", "momentum_flag",
        ])

    # Map history week_start iso dates → Sun-Sat week numbers
    week_dates = [_date.fromisoformat(c) for c in hist.columns]
    week_nums  = [_sun_sat_week_num(d) for d in week_dates]

    if brand.lower() in RAW_SHIPMENTS_ACCOUNTS:
        # Viomi et al: pull from raw per-account FBA Sales CSVs so
        # momentum reflects THIS Seller Central account's shipments,
        # not the Nexlev-merged weekly_sales_snapshot.csv.
        sales_wide = _weekly_sales_from_raw_shipments(brand, week_nums, master_df)
    else:
        sales_wide = _weekly_sales_by_sku(weekly_sales, brand, week_nums, master_df)
    # Align sales to the same SKUs and week columns as hist
    sales_wide = sales_wide.reindex(index=hist.index, columns=week_nums, fill_value=0)
    # Rename sales columns to the same iso date labels
    sales_wide.columns = hist.columns

    peak = sales_wide.max(axis=1).fillna(0)
    avg  = sales_wide.mean(axis=1).fillna(0)

    # Benchmark for VALUING a flagged week (see module docstring, lost_basis).
    # Flag detection below still uses avg/peak exactly as before.
    _lb = (lost_basis or "peak").strip().lower()
    if _lb == "avg":
        benchmark = avg
    elif _lb == "2wk":
        # Trailing 2 weeks of the momentum window; falls back to the window
        # average when the tail is empty (new SKU with no recent sales rows).
        benchmark = sales_wide.iloc[:, -2:].mean(axis=1).fillna(0)
        benchmark = benchmark.where(benchmark > 0, avg)
    else:
        benchmark = peak

    oos_weeks  = pd.Series(0, index=hist.index, dtype=int)
    thin_weeks = pd.Series(0, index=hist.index, dtype=int)
    lost_units = pd.Series(0.0, index=hist.index)

    for wk_col in hist.columns:
        ampm_w  = hist[wk_col].fillna(-1)  # -1 = no snapshot for this week
        sales_w = sales_wide[wk_col].fillna(0)

        # Layer 1 — zeroed
        is_oos = (ampm_w == 0)
        oos_weeks = oos_weeks + is_oos.astype(int)

        # Layer 2 — thin (0 < ampm ≤ 2×avg-velocity AND sales < 70% of peak)
        cover_thin_thresh = COVER_WEEKS_THIN * avg
        is_thin = (
            (ampm_w > 0)
            & (ampm_w <= cover_thin_thresh)
            & (sales_w < PEAK_DROP_RATIO * peak)
            & (peak > 0)  # ignore SKUs with no sales at all
        )
        thin_weeks = thin_weeks + is_thin.astype(int)

        # Combined lost units: (benchmark − actual) for each flagged week,
        # clipped ≥ 0. Benchmark follows lost_basis; default is the window
        # average, NOT peak (peak booked fantasy losses — see docstring).
        flagged = is_oos | is_thin
        lost_this_week = (benchmark - sales_w).clip(lower=0)
        lost_units = lost_units + flagged.astype(int) * lost_this_week

    # Momentum flag
    def _flag(sku):
        oos = int(oos_weeks[sku])
        thin = int(thin_weeks[sku])
        if oos >= 2 or thin >= 3:
            return "RED"
        if oos == 1 or (1 <= thin <= 2):
            return "AMBER"
        return ""

    flags = pd.Series([_flag(s) for s in hist.index], index=hist.index)

    out = pd.DataFrame({
        "oos_weeks_3m":   oos_weeks.astype(int),
        "thin_weeks_3m":  thin_weeks.astype(int),
        "lost_units_3m":  lost_units.round(0).astype(int),
        "momentum_flag":  flags,
    })
    out.index.name = "sku"
    return out


def compute_oos_signals(
    brand: str,
    weekly_sales: pd.DataFrame | None,
    weeks: int = DEFAULT_WEEKS,
    current_ampm_series: pd.Series | None = None,  # kept for API compat; unused
    master_df: pd.DataFrame | None = None,
    lost_basis: str = "peak",
) -> pd.DataFrame:
    """Public entry point. brand is one of Nexlev/Viomi/Audio Array/
    White Mulberry/Tonor. `master_df` should be the account's
    replenishment master (needs SKU, ASIN, Model columns) so we can
    attribute Amazon-channel sales (which come by ASIN, not SKU).
    lost_basis: "peak" (default, historical) | "avg" | "2wk" — see module docstring."""
    global _SALES_CACHE, _MASTER_CACHE
    _SALES_CACHE = weekly_sales
    _MASTER_CACHE = master_df
    ws = current_working_week_start()
    sales_hash  = int(len(weekly_sales))  if weekly_sales is not None else 0
    master_hash = int(len(master_df))    if master_df    is not None else 0
    return _cached_signals(brand.lower(), weeks, ws.isoformat(),
                           sales_hash, master_hash,
                           (lost_basis or "peak").strip().lower())
