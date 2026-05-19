"""Healthcheck for the AM Inventory Replenishment app.

Hits each major module endpoint against the running app and verifies:
  - The endpoint exists (HTTP 200, not 404 / 500)
  - Response shape is what the frontend expects
  - At least one row of data is being served
  - Removed modules are still gone

Designed to be run post-deploy. Exits 0 if every check is green, 1 otherwise.

Stdlib-only — no extra dependencies. Just:
    python scripts/healthcheck.py
    python scripts/healthcheck.py --base https://am-replenishment.onrender.com
    python scripts/healthcheck.py --local          # http://localhost:8060

Add a new check by:
  1. Writing a `def check_<module>(base) -> (bool, str)` function
  2. Adding it to the CHECKS list at the bottom
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_BASE = "https://am-replenishment.onrender.com"
LOCAL_BASE   = "http://localhost:8060"

# Routes that MUST be present on the live app
EXPECTED_ROUTES = [
    "/health",
    "/auth/login",
    "/replenishment",
    "/fc-final-allocation",
    "/china-reorder/",
    "/api/cb-replenishment/",
    "/api/wm-replenishment/",
    "/api/fossil-replenishment",
    "/api/blinkit-replenishment/",
    "/api/blinkit-replenishment/statewise",
    "/admin/users",
    "/usage/summary",
]

# Routes that MUST NOT be present (deleted modules — catches accidental
# resurrection or a stale deploy)
FORBIDDEN_ROUTES = [
    "/china-reorder-working/",
]


# ──────────────────────────────────────────────────────────────────────
# HTTP helper
# ──────────────────────────────────────────────────────────────────────

def fetch(base, path, timeout=90):
    """GET base+path. Returns (status, parsed_body, elapsed_seconds, error_str)."""
    url = base + path
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read()
            try:
                return r.status, json.loads(body), time.time() - t0, None
            except json.JSONDecodeError:
                return r.status, body.decode("utf-8", errors="replace"), time.time() - t0, None
    except urllib.error.HTTPError as e:
        return e.code, None, time.time() - t0, f"HTTPError {e.code}"
    except urllib.error.URLError as e:
        return None, None, time.time() - t0, f"URLError: {e.reason}"
    except Exception as e:
        return None, None, time.time() - t0, f"{type(e).__name__}: {e}"


# ──────────────────────────────────────────────────────────────────────
# Individual checks — each returns (ok: bool, detail: str)
# ──────────────────────────────────────────────────────────────────────

def check_health(base):
    s, j, el, err = fetch(base, "/health", timeout=30)
    if err:               return False, f"{err} ({el:.1f}s)"
    if s != 200:          return False, f"HTTP {s} ({el:.1f}s)"
    if isinstance(j, dict) and j.get("status") == "ok":
        return True, f"OK ({el:.1f}s)"
    return False, f"unexpected body: {str(j)[:80]}"


def check_routes(base):
    s, j, el, err = fetch(base, "/openapi.json", timeout=30)
    if err or s != 200 or not isinstance(j, dict):
        return False, f"openapi unreachable: HTTP {s} {err or ''}"
    paths = set(j.get("paths", {}).keys())
    missing = [p for p in EXPECTED_ROUTES  if p not in paths]
    leaked  = [p for p in FORBIDDEN_ROUTES if p in paths]
    if missing or leaked:
        bits = []
        if missing: bits.append(f"missing: {missing}")
        if leaked:  bits.append(f"resurrected: {leaked}")
        return False, " ; ".join(bits)
    return True, f"{len(paths)} routes registered ({el:.1f}s)"


def _list_with_data(base, path):
    """For endpoints that return a plain list of rows."""
    s, j, el, err = fetch(base, path)
    if err:                       return False, f"{err} ({el:.1f}s)"
    if s != 200:                  return False, f"HTTP {s} ({el:.1f}s)"
    if not isinstance(j, list):   return False, f"expected list, got {type(j).__name__}"
    if not j:                     return False, f"empty data"
    return True, f"{len(j)} rows ({el:.1f}s)", j


def _envelope_with_data(base, path):
    """For endpoints that return {data: [...], ...}."""
    s, j, el, err = fetch(base, path)
    if err:                       return False, f"{err} ({el:.1f}s)"
    if s != 200:                  return False, f"HTTP {s} ({el:.1f}s)"
    data = j.get("data") if isinstance(j, dict) else None
    if not data:                  return False, f"empty data"
    return True, f"{len(data)} rows ({el:.1f}s)", data


def check_replenishment(base):
    res = _list_with_data(base, "/replenishment?account=NEXLEV&sales_window=12&replenish_weeks=8")
    if len(res) == 2: return res
    ok, detail, rows = res
    # Spot-check expected keys are present
    r0 = rows[0]
    for k in ("sku", "model", "sales_velocity", "replenishment_qty"):
        if k not in r0:
            return False, f"missing key in row: {k!r}"
    return ok, detail


def check_cb_replenishment(base):
    res = _envelope_with_data(base, "/api/cb-replenishment/")
    if len(res) == 2: return res
    ok, detail, _ = res
    return ok, detail


def check_wm_replenishment(base):
    res = _envelope_with_data(base, "/api/wm-replenishment/")
    if len(res) == 2: return res
    ok, detail, _ = res
    return ok, detail


def check_fossil_allocation(base):
    res = _list_with_data(base, "/fc-final-allocation?account=fossil")
    if len(res) == 2: return res
    ok, detail, rows = res
    r0 = rows[0]
    for k in ("sku", "model", "fulfillment_center", "cluster"):
        if k not in r0:
            return False, f"Fossil row missing key {k!r}"
    return ok, detail


def check_reorder_intelligence(base):
    qs = urllib.parse.urlencode(
        [("brand", "Nexlev"), ("brand", "Audio Array"), ("months", 3)]
    )
    res = _envelope_with_data(base, f"/china-reorder/?{qs}")
    if len(res) == 2: return res
    ok, detail, rows = res
    brands = {r.get("brand", "?") for r in rows}
    if not {"Nexlev", "Audio Array"}.issubset(brands):
        return False, f"multi-brand stamping broken — got brands={brands}"
    return ok, f"{detail.split('(')[0].strip()} · brands={sorted(brands)}"


def check_blinkit_per_sku(base):
    res = _envelope_with_data(base, "/api/blinkit-replenishment/?cover_weeks=8")
    if len(res) == 2: return res
    ok, detail, rows = res
    r0 = rows[0]
    expected_keys = ("item_id", "product_id", "asin", "blinkit_soh", "ampm_inv", "send_qty")
    missing = [k for k in expected_keys if k not in r0]
    if missing:
        return False, f"missing keys: {missing}"
    # product_id should be a 13-char digit string, not scientific notation
    pid = str(r0.get("product_id", ""))
    if pid and ("e+" in pid.lower() or "." in pid):
        return False, f"product_id rendering wrong: {pid!r}"
    return ok, detail


def check_blinkit_statewise(base):
    res = _envelope_with_data(base, "/api/blinkit-replenishment/statewise?cover_weeks=8")
    if len(res) == 2: return res
    ok, detail, rows = res
    states = {r.get("customer_state", "?") for r in rows}
    # Delhi + Haryana must be merged
    if "Delhi" in states or "Haryana" in states:
        return False, f"Delhi/Haryana merge broken (saw {[s for s in states if s in ('Delhi','Haryana')]})"
    if "Delhi + Haryana" not in states:
        return False, f"expected 'Delhi + Haryana' state, saw {sorted(states)}"
    # Spot-check state-wise keys
    r0 = rows[0]
    for k in ("customer_state", "state_sales", "state_avg_weekly", "state_required", "state_soh", "state_deficiency"):
        if k not in r0:
            return False, f"missing key: {k!r}"
    return ok, f"{detail.split('(')[0].strip()} · {len(states)} states"


# ──────────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────────

CHECKS = [
    ("Health",                  check_health),
    ("Routes inventory",        check_routes),
    ("Replenishment (Nexlev)",  check_replenishment),
    ("CB Replenishment",        check_cb_replenishment),
    ("WM Replenishment",        check_wm_replenishment),
    ("Fossil (FC allocation)",  check_fossil_allocation),
    ("Reorder (multi-brand)",   check_reorder_intelligence),
    ("Blinkit Per-SKU",         check_blinkit_per_sku),
    ("Blinkit Per-State",       check_blinkit_statewise),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base",  default=DEFAULT_BASE, help=f"Base URL (default: {DEFAULT_BASE})")
    ap.add_argument("--local", action="store_true",  help=f"Hit local dev server at {LOCAL_BASE}")
    args = ap.parse_args()

    base = (LOCAL_BASE if args.local else args.base).rstrip("/")
    print(f"Healthcheck against {base}")
    print("-" * 78)

    fails = 0
    for label, fn in CHECKS:
        try:
            ok, detail = fn(base)
        except Exception as e:
            ok, detail = False, f"exception: {type(e).__name__}: {e}"
        mark = "[ OK ]" if ok else "[FAIL]"
        print(f"  {mark}  {label:28s}  {detail}")
        if not ok:
            fails += 1

    print("-" * 78)
    if fails:
        print(f"RESULT  FAIL  ({fails}/{len(CHECKS)} checks failed)")
        sys.exit(1)
    print(f"RESULT  PASS  ({len(CHECKS)}/{len(CHECKS)} checks green)")
    sys.exit(0)


if __name__ == "__main__":
    main()
