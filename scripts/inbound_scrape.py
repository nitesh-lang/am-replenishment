"""
Amazon Seller Central inbound-inventory scraper (Playwright)
=============================================================

Pulls per-SKU inbound shipment data by visiting:
    https://sellercentral.amazon.in/skucentral?mSku=<SKU>&condition=New

Persists the logged-in browser session so weekly re-runs don't need
manual login. When the session expires (Amazon typically logs you out
every 2–7 days) the script tells you to run --login again.

Modes
-----
    python scripts/inbound_scrape.py --login            # one-time interactive login
    python scripts/inbound_scrape.py                    # normal headless run (Nexlev)
    python scripts/inbound_scrape.py --account viomi    # different account
    python scripts/inbound_scrape.py --headed           # debug: watch the browser

Output: data/input/inbound_scrape_<account>.csv

Requires: playwright + chromium browser (already used by render-preview helper).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path

# Force UTF-8 on Windows consoles (cp1252 can't print arrows/check marks)
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_IN   = REPO_ROOT / "data" / "input"

SC_HOME      = "https://sellercentral.amazon.in"
SC_SKU_URL   = SC_HOME + "/skucentral?mSku={sku}&condition=New"
SC_INVENTORY = SC_HOME + "/inventoryplanning/manageinventory"

# Throttle in seconds (be polite to Amazon — too fast triggers bot flags)
PER_SKU_DELAY = 3.0
PAGE_TIMEOUT  = 45_000  # 45s — Amazon pages can be slow

# Match a real Chrome fingerprint in both login + scrape modes so the saved
# cookies stay valid. Amazon's bot detection treats a different UA/viewport
# as a "new device" and forces re-login.
CONTEXT_OPTS = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "viewport":          {"width": 1366, "height": 768},
    "locale":            "en-US",
    "timezone_id":       "Asia/Kolkata",
}


# ──────────────────────────────────────────────────────────────────────
# Account → SKU source file mapping. Reuses the Amazon FBA inventory CSV
# we already pull weekly — its `sku` column is the merchant SKU list.
# ──────────────────────────────────────────────────────────────────────
ACCOUNTS = {
    "nexlev":      DATA_IN / "inventory_amazon_nexlev.csv",
    "viomi":       DATA_IN / "inventory_amazon_viomi.csv",
    "audio_array": DATA_IN / "inventory_amazon_audio_array.csv",
    "wm":          DATA_IN / "inventory_amazon_WM.csv",
}


def profile_dir(account: str) -> Path:
    """Persistent user-data dir — real Chrome profile, mimics a normal browser."""
    return REPO_ROOT / f".amazon_profile_{account}"


def output_path(account: str) -> Path:
    return DATA_IN / f"inbound_scrape_{account}.csv"


def load_sku_list(account: str) -> list[str]:
    src = ACCOUNTS[account]
    if not src.exists():
        raise FileNotFoundError(f"SKU source missing: {src}")
    df = pd.read_csv(src)
    skus = (
        df["sku"].dropna().astype(str).str.strip()
        .loc[lambda s: s != ""].unique().tolist()
    )
    return sorted(skus)


# ──────────────────────────────────────────────────────────────────────
# Login mode — opens a visible browser, you log in by hand, session
# is persisted to disk for future headless runs.
# ──────────────────────────────────────────────────────────────────────
def do_login(account: str):
    """Open a real Chrome profile, let the user log in, save the profile dir."""
    pdir = profile_dir(account)
    pdir.mkdir(exist_ok=True)
    print(f"→ Opening Seller Central for {account}. Log in, complete 2FA, then come back to this terminal.")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(pdir),
            headless=False,
            channel="chrome",      # use installed Google Chrome (not bundled Chromium)
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--no-first-run",
            ],
            **CONTEXT_OPTS,
        )
        page = ctx.new_page()
        page.goto(SC_HOME, timeout=PAGE_TIMEOUT)
        print("\n→ Waiting until you reach the Seller Central home (or any non-signin URL)…")
        try:
            page.wait_for_function(
                """() => !location.host.includes('amazon') ? false :
                       !location.pathname.includes('/ap/signin') &&
                       !location.pathname.includes('/ap/mfa')""",
                timeout=300_000,
            )
        except PWTimeout:
            print("⚠ Login took longer than 5 min — aborting. Re-run --login.")
            ctx.close()
            sys.exit(1)
        print(f"✓ Saved profile → {pdir.name}/")
        ctx.close()


# ──────────────────────────────────────────────────────────────────────
# Per-SKU scrape — extracts inbound qty + any FC-level breakdown that
# the skucentral page renders for that SKU.
# ──────────────────────────────────────────────────────────────────────
def scrape_sku(page, sku: str, debug: bool = False) -> dict:
    url = SC_SKU_URL.format(sku=sku)
    page.goto(url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
    # Brief settle for late-loading widgets + redirects
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PWTimeout:
        pass

    final_url = page.url
    if debug:
        print(f"    debug: landed on {final_url[:120]}")
        print(f"    debug: title    {page.title()[:80]}")

    # Detect bounce-to-login (only fail if we LAND on sign-in, not if we pass through)
    if "/ap/signin" in final_url or "/ap/mfa" in final_url:
        if debug:
            # Save a screenshot for diagnosis
            shot = REPO_ROOT / f".debug_{sku}.png"
            try: page.screenshot(path=str(shot), full_page=False)
            except Exception: pass
            print(f"    debug: screenshot saved → {shot.name}")
        raise RuntimeError(f"Session expired (landed on {final_url[:80]})")

    row = {"sku": sku, "url": url}

    # ── grab the whole page text once and pluck values via regex ──
    text = page.inner_text("body", timeout=10_000)

    def grab(label_pattern: str):
        m = re.search(label_pattern + r"\s*[\n:]?\s*([\d,]+)", text, re.IGNORECASE)
        return int(m.group(1).replace(",", "")) if m else None

    row["inbound_qty"]      = grab(r"Inbound\s*(?:quantity|inventory|shipment)?")
    row["fulfillable_qty"]  = grab(r"Fulfillable")
    row["reserved_qty"]     = grab(r"Reserved")
    row["unfulfillable_qty"]= grab(r"Unfulfillable")
    row["working_qty"]      = grab(r"Working")
    row["shipped_qty"]      = grab(r"Shipped")
    row["receiving_qty"]    = grab(r"Receiving")

    # Capture title for sanity (and so you can spot any SKU that errored)
    try:
        row["product_title"] = (page.title() or "").split("|")[0].strip()
    except Exception:
        row["product_title"] = ""

    return row


# ──────────────────────────────────────────────────────────────────────
# Main run
# ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", default="nexlev", choices=sorted(ACCOUNTS.keys()))
    parser.add_argument("--login", action="store_true", help="One-time interactive login")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser (debug)")
    parser.add_argument("--limit", type=int, default=None, help="Cap SKUs for a smoke test")
    parser.add_argument("--debug", action="store_true", help="Print URLs + save screenshots on bounce")
    args = parser.parse_args()

    if args.login:
        do_login(args.account)
        return

    pdir = profile_dir(args.account)
    if not pdir.exists() or not any(pdir.iterdir()):
        print(f"❌ No saved profile for {args.account}. Run once with --login first.")
        sys.exit(1)

    skus = load_sku_list(args.account)
    if args.limit:
        skus = skus[: args.limit]
    print(f"→ Scraping {len(skus)} SKUs for {args.account}…")

    out_rows: list[dict] = []
    start = time.time()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(pdir),
            headless=not args.headed,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--no-first-run",
            ],
            **CONTEXT_OPTS,
        )
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        page = ctx.new_page()
        page.set_default_timeout(PAGE_TIMEOUT)

        for i, sku in enumerate(skus, 1):
            try:
                row = scrape_sku(page, sku, debug=args.debug)
                out_rows.append(row)
                print(f"  [{i:3d}/{len(skus)}] {sku:12s} inbound={row.get('inbound_qty')!s:>6}  "
                      f"working={row.get('working_qty')!s:>5}  shipped={row.get('shipped_qty')!s:>5}")
            except RuntimeError as e:
                print(f"  ❌ {sku}: {e}")
                if "Session expired" in str(e):
                    break
            except Exception as e:
                print(f"  ⚠ {sku}: {type(e).__name__}: {e}")
                out_rows.append({"sku": sku, "error": str(e)[:120]})

            time.sleep(PER_SKU_DELAY)

        # Persistent context auto-saves cookies/state when closed
        ctx.close()

    # Write CSV (idempotent — overwrites each run)
    if out_rows:
        out = output_path(args.account)
        cols = ["sku", "product_title", "inbound_qty", "fulfillable_qty",
                "reserved_qty", "unfulfillable_qty", "working_qty",
                "shipped_qty", "receiving_qty", "url", "error"]
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in out_rows:
                w.writerow(r)
        elapsed = (time.time() - start) / 60
        print(f"\n✓ Wrote {len(out_rows)} rows → {out.relative_to(REPO_ROOT)}  ({elapsed:.1f} min)")


if __name__ == "__main__":
    main()
