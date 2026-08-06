from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


# =====================================================
# IMPORT ROUTERS
# =====================================================
from app.api.kpis import router as kpis_router
from app.api.replenishment import router as replenishment_router
from app.api.dashboard import router as dashboard_router
from app.api.fc_planning import router as fc_planning_router
from app.api.fc_transfer import router as fc_transfer_router
from app.api.fc_final_allocation import router as fc_final_allocation_router
from app.api.region_sales import router as region_sales_router  # ✅ NEW
from app.api.china_reorder import router as china_reorder_router
from app.api.cb_replenishment import router as cb_replenishment_router
from app.api.wm_replenishment import router as wm_replenishment_router
from app.api.fossil_replenishment import router as fossil_router
from app.api.blinkit_replenishment import router as blinkit_router
from app.api.inbound_shipments import router as inbound_shipments_router
from app.api.data_freshness import router as data_freshness_router
from app.api.master_carton import router as master_carton_router
from app.api.auth import router as auth_router
from app.api.usage import router as usage_router
from app.api.internal_po import router as internal_po_router
from app.api.plans import router as plans_router



# =====================================================
# CREATE APP
# =====================================================
app = FastAPI(
    title="AM Inventory Replenishment API",
    version="1.0.0"
)
from app.db import engine
from app.core.models.base import Base

@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)
    try:
        from app.services import auth_users
        auth_users.ensure_table_and_seed()
        print("✅ App users table ready")
    except Exception as e:
        print(f"⚠️ User table init warning: {e}")
    try:
        from app.services import usage_log
        usage_log.ensure_table()
        print("✅ Usage log table ready")
    except Exception as e:
        print(f"⚠️ Usage log init warning: {e}")
    try:
        from app.services import plans_service
        plans_service.ensure_plans_tables()
        print("✅ Plans tables ready")
    except Exception as e:
        print(f"⚠️ Plans table init warning: {e}")
    _unshallow_repo()
    _preload_data_files()


def _unshallow_repo():
    """Render clones with --depth 1 for speed AND strips the origin remote
    from the runtime .git — so `git log -- <file>` returns today's tip
    commit for every file (only 1 commit visible). Set the remote back
    up and unshallow at startup so git-log-based freshness + OOS-history
    features get real dates.

    Public repo, no auth needed. Best-effort — swallowed errors."""
    import subprocess

    def _run(cmd):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=90)

    try:
        # Check if we're actually shallow first — skip the whole dance on
        # local dev / already-full clones.
        is_shallow = _run(["git", "rev-parse", "--is-shallow-repository"])
        if (is_shallow.stdout or "").strip() != "true":
            print("✅ Repo already full history — no unshallow needed")
            return

        # Ensure origin remote exists (Render strips it). Public URL, safe
        # to hardcode. `git remote add` errors if it already exists; try
        # set-url as a fallback.
        remotes = _run(["git", "remote"]).stdout.strip().splitlines()
        url = "https://github.com/nitesh-lang/am-replenishment.git"
        if "origin" not in remotes:
            _run(["git", "remote", "add", "origin", url])
            print(f"→ Added origin remote for unshallow")
        else:
            _run(["git", "remote", "set-url", "origin", url])

        # Now fetch full history
        result = _run(["git", "fetch", "--unshallow"])
        if result.returncode == 0:
            after = _run(["git", "rev-list", "--count", "HEAD"]).stdout.strip()
            print(f"✅ Repo unshallowed — {after} commits now visible")
        else:
            msg = (result.stderr or result.stdout or "").strip()[:200]
            print(f"⚠️ Unshallow fetch failed: {msg}")
    except Exception as e:
        print(f"⚠️ Repo unshallow warning: {e}")

def _preload_data_files():
    """Pre-load all heavy Excel/CSV files into memory at startup."""
    try:
        from app.services import file_cache
        file_cache.preload()
        print("✅ Data files preloaded into cache")
    except Exception as e:
        print(f"⚠️ Preload warning: {e}")


@app.get("/_debug/git-state")
def debug_git_state():
    """Diagnose git-log-based freshness on the deployed runtime. Returns
    the current shallow status, PATH lookup for git, the count of commits
    visible, and a probe log line for the WM In-Transit PO file."""
    import subprocess, shutil
    from pathlib import Path as _P
    repo_root = _P(__file__).resolve().parent.parent.parent

    def run(cmd):
        try:
            r = subprocess.run(cmd, cwd=str(repo_root), capture_output=True,
                               text=True, timeout=10)
            return {"rc": r.returncode,
                    "stdout": (r.stdout or "").strip()[:400],
                    "stderr": (r.stderr or "").strip()[:400]}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    return {
        "cwd_from_python":  str(repo_root),
        "dot_git_exists":   (repo_root / ".git").exists(),
        "git_in_path":      shutil.which("git"),
        "is_shallow":       run(["git", "rev-parse", "--is-shallow-repository"]),
        "commit_count":     run(["git", "rev-list", "--count", "HEAD"]),
        "head":             run(["git", "log", "-1", "--format=%H %cs %s"]),
        "remote_urls":      run(["git", "remote", "-v"]),
        "unshallow_now":    run(["git", "fetch", "--unshallow"]),
        "after_shallow":    run(["git", "rev-parse", "--is-shallow-repository"]),
        "after_count":      run(["git", "rev-list", "--count", "HEAD"]),
        "wm_pofile_log":    run(["git", "log", "-1", "--format=%H %cs",
                                  "--", "data/input/In_Transit_PO data - WM.xlsx"]),
        "nex_snap_log":     run(["git", "log", "-1", "--format=%H %cs",
                                  "--", "data/input/inventory_snapshot_nexlev.xlsx"]),
    }
# =====================================================
# CORS (REQUIRED FOR VITE FRONTEND)
# =====================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://am-replenishment-1.onrender.com",
        "https://am-replenishment.onrender.com",
    ],
    # Cap the preflight cache at 1 min. If the API cold-starts and the
    # browser gets a failed preflight, Chrome caches that failure for
    # max_age seconds and blocks every subsequent request without asking
    # the server. 10 min was too painful; 60s recovers automatically.
    max_age=60,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# HEALTH CHECK
# =====================================================
@app.get("/health")
def health():
    return {"status": "ok"}


# =====================================================
# INCLUDE ROUTERS
# =====================================================
app.include_router(kpis_router)
app.include_router(replenishment_router)
# Alias the same router under /api so stale frontend bundles that call
# /api/replenishment?... don't 404 spam. Both prefixes hit the same code.
app.include_router(replenishment_router, prefix="/api")
app.include_router(dashboard_router)
app.include_router(fc_planning_router)
app.include_router(fc_transfer_router)
app.include_router(fc_final_allocation_router)
app.include_router(region_sales_router)  # ✅ NEW
app.include_router(china_reorder_router)
app.include_router(cb_replenishment_router, prefix="/api")
app.include_router(wm_replenishment_router, prefix="/api")
app.include_router(fossil_router)
app.include_router(blinkit_router, prefix="/api")
app.include_router(inbound_shipments_router)
app.include_router(data_freshness_router)
app.include_router(master_carton_router)
app.include_router(auth_router)
app.include_router(usage_router)
app.include_router(internal_po_router)
# /api alias so bundle callers that use /api/ prefix don't 404
app.include_router(internal_po_router, prefix="/api")
app.include_router(plans_router)
app.include_router(plans_router, prefix="/api")

# =====================================================
# SPA — serve the Vite-built React app so frontend + API are
# the same origin (no CORS handshake, works across every
# browser / ISP / network path).
#
# 1. /assets/* and other static files served from frontend/dist
# 2. SPA fallback: any GET not matching an API route returns
#    index.html so client-side routing works (/plans, /dashboard, ...)
# 3. API routes registered above still win over the fallback.
# =====================================================
_SPA_ROOT = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _SPA_ROOT.exists() and (_SPA_ROOT / "index.html").exists():
    # Mount static assets (JS/CSS bundles, favicon, etc.) under /assets/*
    app.mount(
        "/assets",
        StaticFiles(directory=str(_SPA_ROOT / "assets")),
        name="spa-assets",
    )

    @app.get("/", include_in_schema=False)
    def _spa_root():
        return FileResponse(_SPA_ROOT / "index.html")

    @app.get("/vite.svg", include_in_schema=False)
    def _vite_svg():
        return FileResponse(_SPA_ROOT / "vite.svg")

    # SPA fallback for any GET not matched by an API route above.
    # Placed at the END so router routes have priority.
    @app.exception_handler(StarletteHTTPException)
    async def _spa_fallback(request, exc):
        # Only rewrite 404s on non-API GET routes to serve the SPA.
        if (
            exc.status_code == 404
            and request.method == "GET"
            and not request.url.path.startswith(("/api/", "/auth/"))
        ):
            return FileResponse(_SPA_ROOT / "index.html")
        # For everything else, re-raise the original exception so FastAPI
        # emits its normal JSON error response with CORS headers intact.
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    print(f"✅ SPA mounted from {_SPA_ROOT}")
else:
    print(f"⚠️  SPA dist not found at {_SPA_ROOT}; frontend served separately")

    @app.get("/")
    def root():
        return {"message": "AM Inventory Replenishment API running"}