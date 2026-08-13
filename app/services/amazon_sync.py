"""
On-demand Amazon inventory sync.

Runs the SP-API FBA inventory + ledger pullers for a given account
via subprocess, then busts file_cache so subsequent Replenishment /
FC Allocation GETs see the fresh CSVs. Called from
POST /api/sync/inventory?account=... (see app/api/replenishment.py).

Concurrency: one thread lock per account key so two users clicking
Sync at the same moment don't double-run the pullers (SP-API rate
limits, wasteful CSV rewrites). If a sync is in-flight the second
caller gets status=already_running with the current status.

Not exposed for Fossil (CAMBIUMRETAIL) yet — that account uses a
separate LWA client and different file paths under
'Fossil Replenishment/'; extend the account map if needed.
"""

import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.services import file_cache

REPO_ROOT   = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

# UI account label → (SP-API script account key, [files to invalidate])
# UI labels are the strings the frontend already sends via ?account=.
_ACCOUNT_MAP: dict[str, tuple[str, list[str]]] = {
    "NEXLEV":         ("NEXLEV",        ["inventory_amazon_nexlev.csv",
                                          "inventory_ledger_nexlev.csv"]),
    "VIOMI":          ("VIOMI",         ["inventory_amazon_viomi.csv",
                                          "inventory_ledger_viomi.csv"]),
    "AUDIO ARRAY":    ("AUDIOARRAY",    ["inventory_amazon_audio_array.csv",
                                          "inventory_ledger_Audio Array.csv"]),
    "WHITE MULBERRY": ("WHITEMULBERRY", ["inventory_amazon_WM.csv",
                                          "inventory_ledger_WM.csv"]),
    "FOSSIL":         ("CAMBIUMRETAIL", ["Fossil Replenishment/inventory_amazon_fossil.csv",
                                          "Fossil Replenishment/inventory_ledger_fossil.csv"]),
}

# Cache busting also invalidates any parent-key match (WM unions ledger
# with viomi's, AA unions inv with viomi's — see replenishment.load_data).
# Cheapest correct behavior: also invalidate the viomi files whenever
# WM or AA syncs, and vice-versa when viomi syncs. Real solution would
# split the union sources; for now nuke the neighbours too.
_UNION_ALSO: dict[str, list[str]] = {
    "AUDIO ARRAY":    ["inventory_amazon_viomi.csv", "inventory_ledger_viomi.csv"],
    "WHITE MULBERRY": ["inventory_amazon_viomi.csv", "inventory_ledger_viomi.csv"],
    "VIOMI":          ["inventory_amazon_audio_array.csv", "inventory_amazon_WM.csv",
                       "inventory_ledger_Audio Array.csv",  "inventory_ledger_WM.csv"],
}

_locks:  dict[str, threading.Lock] = {}
_status: dict[str, dict]            = {}


def _lock_for(acct_key: str) -> threading.Lock:
    if acct_key not in _locks:
        _locks[acct_key] = threading.Lock()
    return _locks[acct_key]


def get_status(account: str) -> dict:
    key = (account or "").strip().upper()
    return _status.get(key) or {
        "last_sync_at": None, "in_progress": False, "last_error": None,
    }


def supported_accounts() -> list[str]:
    return list(_ACCOUNT_MAP.keys())


def sync_inventory(account: str, timeout_sec: int = 240) -> dict:
    """Blocking pull + cache-bust. Returns dict with status/timing.
    Raises ValueError on unknown account."""
    key = (account or "").strip().upper()
    if key not in _ACCOUNT_MAP:
        raise ValueError(f"unsupported account: {account} "
                         f"(known: {', '.join(supported_accounts())})")
    sp_key, files = _ACCOUNT_MAP[key]
    lock = _lock_for(key)
    if not lock.acquire(blocking=False):
        return {"status": "already_running", "account": key, **get_status(account)}

    prior = get_status(account)
    _status[key] = {
        "last_sync_at": prior.get("last_sync_at"),
        "in_progress": True, "last_error": None,
        "started_at":  datetime.now(timezone.utc).isoformat(),
    }
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    cmds = [
        [sys.executable, str(SCRIPTS_DIR / "sp_fba_inventory_pull.py"),
         "--account", sp_key],
        [sys.executable, str(SCRIPTS_DIR / "sp_ledger_pull.py"),
         "--account", sp_key],
    ]
    results = []
    try:
        for cmd in cmds:
            script = Path(cmd[1]).name
            print(f"[amazon_sync] {key}: running {script}")
            proc = subprocess.run(
                cmd, cwd=str(REPO_ROOT), env=env,
                capture_output=True, text=True, timeout=timeout_sec,
            )
            results.append({
                "script": script,
                "rc": proc.returncode,
                "stdout_tail": (proc.stdout or "")[-800:],
                "stderr_tail": (proc.stderr or "")[-400:],
            })
            if proc.returncode != 0:
                raise RuntimeError(
                    f"{script} exit={proc.returncode}: "
                    f"{(proc.stderr or proc.stdout or '')[-400:].strip()}"
                )

        for f in files + _UNION_ALSO.get(key, []):
            try: file_cache.invalidate(f)
            except Exception: pass

        now = datetime.now(timezone.utc).isoformat()
        _status[key] = {"last_sync_at": now, "in_progress": False, "last_error": None}
        return {"status": "ok", "account": key, "last_sync_at": now,
                "files_updated": files, "scripts": results}

    except subprocess.TimeoutExpired as e:
        err = f"timeout after {timeout_sec}s on {Path(e.cmd[1]).name}"
        _status[key] = {"last_sync_at": prior.get("last_sync_at"),
                        "in_progress": False, "last_error": err}
        return {"status": "error", "account": key, "error": err, "scripts": results}
    except Exception as e:
        err = str(e)
        _status[key] = {"last_sync_at": prior.get("last_sync_at"),
                        "in_progress": False, "last_error": err}
        return {"status": "error", "account": key, "error": err, "scripts": results}
    finally:
        lock.release()
