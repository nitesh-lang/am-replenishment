# AM Inventory Replenishment

Internal multi-brand FBA inventory replenishment app for Cambium Retail / Nexlev's
operational team. Reads weekly Excel/CSV snapshots (master, inventory, sales,
in-transit POs), computes per-SKU and per-FC send quantities, and exposes a
React dashboard one page per brand/channel.

This doc is the **first thing to read** when opening a new Claude session in this
repo. Skim everything below before touching anything.

---

## 1. Tech stack at a glance

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLAlchemy, psycopg2-binary, pandas, openpyxl |
| Frontend | React 18 + Vite 5 + Tailwind 3 + axios + react-router-dom 6 |
| Database | PostgreSQL (Render-managed) |
| Hosting | Render — single web service + managed Postgres (Virginia region) |
| Auth | HMAC-SHA256 signed bearer tokens (stdlib only, no extra deps) |
| Frontend bundle | Production build served from `frontend/dist/` via the FastAPI app |

Render live URL: **https://am-replenishment.onrender.com**

---

## 2. Repo layout

```
AM_Replenishment/
├── app/
│   ├── api/                       # FastAPI routers — one file per module
│   │   ├── main.py                #   THE entry point (uvicorn app.api.main:app)
│   │   ├── auth.py                #   /auth/login + /admin/users
│   │   ├── usage.py               #   usage logging + /usage/summary (admin)
│   │   ├── replenishment.py       #   /replenishment + Fossil cluster routes
│   │   ├── cb_replenishment.py    #   /api/cb-replenishment/
│   │   ├── wm_replenishment.py    #   /api/wm-replenishment/
│   │   ├── fossil_replenishment.py
│   │   ├── blinkit_replenishment.py  # /api/blinkit-replenishment/ (+ /statewise)
│   │   ├── china_reorder.py       #   /china-reorder/  (now "Reorder Intelligence")
│   │   ├── fc_planning.py · fc_transfer.py · fc_final_allocation.py
│   │   ├── region_sales.py · dashboard.py · kpis.py · master_carton.py
│   ├── services/                  # business logic; one file per concern
│   │   ├── db.py                  #   context-manager get_conn() — all psycopg2 goes through this
│   │   ├── auth_users.py · auth_tokens.py  # users table, bearer token signing/verify
│   │   ├── replenishment.py       # the main calc engine (Nexlev/Viomi/AA/WM accounts)
│   │   ├── fc_planning.py · fc_transfer.py · fc_final_allocation.py
│   │   ├── cb_replenishment.py · cb_replenishment_saved.py
│   │   ├── wm_replenishment.py
│   │   ├── fossil_replenishment_service.py
│   │   ├── blinkit_replenishment.py
│   │   ├── china_reorder.py
│   │   ├── region_sales.py · validation_engine.py · week_helper.py
│   │   ├── file_cache.py          # in-memory cache for data/input files (preload at startup)
│   │   ├── usage_log.py · replenishment_saved.py
│   └── core/models/               # SQLAlchemy Base + a couple of inert ORM classes
├── frontend/                      # Vite + React
│   ├── src/
│   │   ├── App.jsx                # routes
│   │   ├── auth/                  # AuthContext, ProtectedRoute, ModuleGate
│   │   ├── layout/Layout.jsx      # sidebar (gated per module)
│   │   ├── pages/                 # one file per module page
│   │   ├── services/api.js        # axios base
├── data/input/                    # ALL excel/csv input files served at runtime
│   ├── replenishment_master_nexlev.xlsx
│   ├── replenishment_master_viomi.xlsx
│   ├── Audio Array & WM Replenishment/AA & WM Replenishment.xlsx  (sheets: AA, WM)
│   ├── CB Replenishment_Master.xlsx
│   ├── Inventory_snapshot_{nexlev,audio_array,WM,tonor}.xlsx
│   ├── inventory_amazon_{nexlev,viomi,audio_array,WM}.csv
│   ├── inventory_ledger_{nexlev,viomi,Audio Array,WM}.csv
│   ├── fba_shipments_{nexlev,viomi,Audio Array,WM}.csv
│   ├── weekly_sales_snapshot.csv               # main sales — Amazon + 1p Sales channels
│   ├── weekly_sales_snapshot - ChinaReorder.csv  # has more channels incl. Blinkit Sales
│   ├── weekly_sales_snapshot - CB Replenishment.csv
│   ├── In_Transit_PO data.xlsx · In_Transit_PO data - WM.xlsx
│   ├── Fossil Replenishment/                    # Fossil-specific subfolder
│   └── Blinkit/                                  # Blinkit-specific subfolder
├── scripts/
│   └── healthcheck.py             # post-deploy smoke test — hits every module endpoint
├── tests/tests/                   # pytest suite
├── requirements.txt · package.json
└── CLAUDE.md                      # THIS FILE
```

`venv/` and `node_modules/` are gitignored. The `.gitignore` is **UTF-8** —
do NOT save it as UTF-16 from Notepad; that breaks every ignore rule.

---

## 3. Modules — what each one does

Every module is a separate page in the React app, backed by its own service.
They share the same data files but slice/aggregate differently.

| Module | URL slug | Brand(s) | Source | Key output |
|---|---|---|---|---|
| **Replenishment** | `/replenishment` | Nexlev / Viomi / Audio Array / White Mulberry | weekly_sales_snapshot + Inventory_snapshot_* + inventory_amazon_* | Per-model send qty, AMPM/Amazon SOH, risky/overstock flags |
| **FC Allocation** | `/fc-allocation` | same 4 + Fossil | fba_shipments_* + inventory_ledger_* + per-account master | Per-(SKU × FC) send qty, transfer-in, fill_pct, IXD governance |
| **Reorder Intelligence** | `/china-reorder` | multi-brand (multi-select Nexlev / Audio Array / Tonor / WM) | weekly_sales_snapshot - ChinaReorder.csv + Inventory_snapshot_* | Per-model 12-week sales, suggested reorder qty |
| **CB Replenishment** | `/cb-replenishment` | Audio Array + Tonor (CB = "China Buy") | CB Replenishment_Master.xlsx + In_Transit_PO data.xlsx + AA/Tonor snapshots | Per-model PO requirement with working-week save flow |
| **Clicktech (WM)** | `/wm-replenishment` | White Mulberry only | AA & WM Replenishment.xlsx (WM sheet) + Inventory_snapshot_WM.xlsx + In_Transit_PO data - WM.xlsx | Per-model PO requirement |
| **Fossil Replenishment** | `/fossil-replenishment` | Fossil only | Fossil Replenishment/* subfolder | Detail page, separate cluster math |
| **Blinkit Replenishment** | `/blinkit-replenishment` | Nexlev + Audio Array | Blinkit/* subfolder (master + AMPM + sales) | Per-SKU + per-State views (toggle in UI) |
| **Sales Analytics** | `/sales-analytics` | all | weekly_sales_snapshot.csv | Cross-brand sales drilldown |
| **Region Sales** | `/region-sales` | Nexlev / Viomi only | weekly_sales_snapshot.csv | 30-day regional perf |
| **Dashboard** | `/dashboard` | all | aggregations | Landing page |
| **Admin** | `/admin` | — | DB | User management (admin role only) |
| **Usage Analytics** | `/usage` | — | DB | Per-user activity (admin role only) |

**Removed:** China Reorder Working module (deleted in commit `2c7fbd4` — was unused).

---

## 4. Brands & channel portfolio (context)

Cambium Retail operates **multiple brands across ~11 channels, ~90% volume on Amazon**:

| Brand | Vertical |
|---|---|
| **Nexlev** | Home & Kitchen + Home Personal Care (H&K + HPC) |
| **Viomi** | (rebrands of Nexlev SKUs onto separate Amazon listings) |
| **Audio Array** | Microphones + pro audio gear |
| **White Mulberry** | Desks + monitor arms |
| **Fossil** | Watches (B2B with Fossil India) |
| **Tonor** | USB microphones (CB program) |

Channels: Amazon (primary), 1p Sales (Cloudtail / Clicktech), Blinkit Sales,
Myntra, D2C, B2B, BI Worldwide, Pharmaeasy, CRED, POP UPI.

---

## 5. AMPM — the central concept

**AMPM** = the *mother warehouse* (the company's own warehouse before stock
goes out to Amazon FCs or other channels). It's a single shared pool per
SKU/Model. Inventory snapshot files carry it as `Channel == "AMPM"`.

Every replenishment module ultimately answers "how much can I ship to the
sales channel given AMPM availability and current SOH?".

### Model-matching rule (settled — current behaviour)

**Exact case-insensitive Model match** across all modules
(Replenishment / FC Allocation / CB / WM). No SKU layer, no variant /
base-token fallback. The rule lives in 4 services and looks like:

```python
ampm_inv = inventory[inventory["Channel"].str.strip().str.lower() == "ampm"]
key = inventory_model.str.strip().str.lower()      # same for master
ampm = inventory.groupby(key)["Qty"].sum().to_dict()
df["ampm_inventory"] = master_model.str.strip().str.lower().map(ampm).fillna(0)
```

If master Model and inventory Model don't match character-for-character
(modulo upper/lower case), result is **0** — and the data team must align
the names. We tried SKU-keyed and base-token-fallback variants earlier;
both surfaced edge-case bugs, user explicitly chose strict Model match.

**Implication:** when master refreshes introduce a name like
`AI-02 2x2| Metallic Red` but inventory only has `AI-02`, AMPM shows 0
until either file is realigned. Use `scripts/healthcheck.py` and the
audit script (see §11) to find these.

### Fossil exception

Fossil **does not** use the inventory snapshot for AMPM. It pulls AMPM
from the `Fossil SOH` column of `Fossil Replenishment/Fossil Replenishment.xlsx`.
The Model-matching rule above does not apply there.

---

## 6. Conventions & gotchas

### File-loading
All data files go through `app.services.file_cache` (`get()` for plain
files, `get_excel_sheet()` for specific sheets). Files are preloaded at
FastAPI startup. **When adding a new input file, add it to the `preload()`
function** in `file_cache.py` or it gets loaded lazily per-request.

### Excel quirks
- `Blinkit/Inventory/InventoryData.xlsx` has banner + grouped header rows;
  it's read with `header=2`. The `get_excel_sheet` helper supports a
  `header` kwarg specifically for this.
- Excel writes UTF-16 lock files (`~$Foo.xlsx`) when a file is open —
  these are gitignored via `~$*`.

### Database access
Everything goes through `app.services.db.get_conn()` — a context manager
that guarantees `conn.close()` on exception. **Never** call
`psycopg2.connect()` directly; that pattern leaked connections under load
before commit `8c6d879`.

### Auth model
- Login (`/auth/login`) returns `{user, token}`. Token is HMAC-SHA256 signed
  via `AUTH_SECRET_KEY` env var.
- Admin endpoints (`/admin/users`, `/usage/summary`) require
  `Authorization: Bearer <token>` AND the user's `role` is re-checked
  against the DB on every call (immediate demotion).
- Set **`AUTH_SECRET_KEY`** in the Render env, otherwise sessions
  invalidate on every restart (ephemeral key with a stderr warning).

### Frontend
- Sidebar entries are **gated per-user-per-module** via `allowed_modules`
  (JSONB column on `app_users`). New module = add the slug to
  `ALL_MODULES` in `auth_users.py` AND grant access via `/admin`.
- Export CSV buttons are **always right-aligned** in toolbars
  (`ml-auto` or `justify-end`) — applied uniformly across modules.

### Time conventions
- Replenishment/CB sales windows use **ISO week numbers** (`Week 12` style).
- Blinkit state-wise view derives ISO week from each order's `Order Date`.
- Working-week save flow (`replenishment_saved`, `cb_replenishment_saved`)
  uses **IST midnight Sunday** as week boundary (see `week_helper.py`),
  saves locked at Saturday 11:59 PM IST.

### Blinkit specifics
- **17 dark stores** mapped to 7 states (Bengaluru/MH/UP/Haryana/TN/Telangana/Gujarat).
- **Delhi + Haryana are merged** into one demand pool (Delhi is fulfilled
  from Haryana NCR warehouses). See `_STATE_ALIASES` in `app/services/blinkit_replenishment.py`.
- State-wise velocity uses a **fixed `/12` divisor** regardless of
  selected window (planning convention — `STATEWISE_VELOCITY_DIVISOR`).
- Active universe = `Expansion Level ∈ {Level 1, Level 2, Level 4, Trial}`.
  Drops DISCONTINUED / Launch Awaited / blank.

---

## 7. Deployment

Render deploys on every push to `main`.

```
Build command:  pip install -r requirements.txt && cd frontend && npm ci && npm run build
Start command:  uvicorn app.api.main:app --host 0.0.0.0 --port $PORT
```

### Required env vars on Render
| Var | Purpose |
|---|---|
| `DATABASE_URL` | Render's managed Postgres (auto-linked) |
| `AUTH_SECRET_KEY` | HMAC secret for session tokens — set manually |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | One-time admin seed if `app_users` is empty |
| `LOG_LEVEL` / `LOG_DIR` | optional |

### Post-deploy ritual
1. Wait for Render's "Deploy live" event
2. `python scripts/healthcheck.py` — runs ~9 endpoint checks, exits 0 on green
3. Hard-refresh browser (Ctrl+Shift+R) — picks up new frontend bundle
4. Smoke-test one page from each affected module

---

## 8. Running locally (dev)

```bash
# Backend
cd "AM_Replenishment"
python -m venv venv
venv/Scripts/activate    # or venv/bin/activate on macOS/Linux
pip install -r requirements.txt
# create .env with DATABASE_URL=<external Render postgres URL>
uvicorn app.api.main:app --reload --port 8060

# Frontend
cd frontend
npm install
npm run dev              # serves on http://localhost:5173

# Healthcheck against local
python scripts/healthcheck.py --local
```

`.env` is gitignored. Never commit DB credentials. The Render Postgres
password was leaked once in early commits (`67a19b4` / `6e84574` in history);
it was rotated and the file removed from tracking in `ccdc9c5`.

---

## 9. Common operations

### Refreshing data files (weekly cycle)
1. Drop new versions into `data/input/<path>`
2. `git status` — confirm only the expected files changed
3. Commit + push — Render auto-redeploys with new data
4. Skip committing untracked `data/input/Blinkit/Sales/` files unless
   they're needed (they aren't currently used by code)

### Adding a new module / page
1. Create `app/services/<name>.py` (business logic)
2. Create `app/api/<name>.py` (FastAPI router with `prefix="/..."`)
3. Mount in `app/api/main.py`
4. Add slug to `ALL_MODULES` in `app/services/auth_users.py`
5. Add `data/input/<file>` paths to `file_cache.preload()` if heavy
6. Create `frontend/src/pages/<NameOfPage>.jsx`
7. Add `<Route>` in `frontend/src/App.jsx`
8. Add sidebar entry in `frontend/src/layout/Layout.jsx`
9. Add label in `Admin.jsx` and `UsageAnalytics.jsx` `MODULE_LABELS`
10. Grant yourself access via `/admin` after deploy

### Rotating the Render Postgres password
1. Render dashboard → DB service → Info → **New default credential**
2. After credential created, the new user becomes default
3. **Manually update `DATABASE_URL`** on the web service (it's a manual
   literal string, not auto-linked — confirmed during last rotation)
4. Update local `.env` with the new External Database URL
5. Verify old credential has 0 open connections, then delete it from the
   Credentials section

---

## 10. Healthcheck & audit scripts

### `scripts/healthcheck.py`
Hits every major module endpoint after a deploy. Stdlib only, no deps.

```bash
python scripts/healthcheck.py                     # vs prod
python scripts/healthcheck.py --local             # vs localhost:8060
python scripts/healthcheck.py --base https://...  # vs anything
```

9 checks: Health · Routes inventory · Replenishment · CB · WM · Fossil · Reorder
multi-brand · Blinkit Per-SKU · Blinkit Per-State. Exits 0 if all green,
1 otherwise.

**Catches:** module silently dropped, endpoint returning 500, empty data
(missing input file), response shape changed (e.g. Product ID rendering
as scientific notation again), deleted modules silently resurrected.

### SKU master alignment audit (`D:\Nitesh\Normalization\`)
Off-repo workflow. Folder contains the canonical `sku_master.xlsx` plus
copies of the brand replenishment masters. Scripts in this repo's history
(`mismatches_*.xlsx` generators) compare each operational master against
sku_master and emit a worksheet listing every SKU / Model / ASIN that
differs. Outcome is usually: data team aligns the operational master to
sku_master's canonical names. Then re-run.

Currently AA / WM / CB / Nexlev / Viomi all sit at 0 or near-0 mismatches
against sku_master. The 4–5K units of Audio Array "at-risk" stock is
specific to Pro/variant naming where master has descriptive names
(`AH-50 Ear Cushion`) but inventory has the short ones (`AH-50`). These
are tracked in `D:\Nitesh\Normalization\model_dropouts_for_review_2026-05-21.xlsx`.

---

## 11. Recent architectural decisions (decision log)

These are the calls already locked in — don't re-litigate without strong
reason.

| When | Decision | File |
|---|---|---|
| 2026-05-18 | **HMAC bearer tokens** replace `X-Admin-Email` for admin endpoints — admin role re-checked from DB on every call | `auth_tokens.py` |
| 2026-05-18 | Single `get_conn()` context manager — every psycopg2 connect goes through it | `db.py` |
| 2026-05-18 | `.gitignore` rewritten as UTF-8 (was UTF-16, silently broken) | `.gitignore` |
| 2026-05-18 | Removed China Reorder Working module (unused) | (deletion) |
| 2026-05-19 | Blinkit module: Per-SKU + Per-State views, toggle in UI | `blinkit_replenishment.*` |
| 2026-05-19 | Blinkit State: fixed `/12` velocity divisor; Delhi+Haryana merged | `blinkit_replenishment.py` |
| 2026-05-19 | Blinkit sales source: `weekly_sales_snapshot - ChinaReorder.csv` (channel = "Blinkit Sales") for Per-SKU; monthly Excels for Per-State | `blinkit_replenishment.py` |
| 2026-05-20 | China Reorder renamed to "Reorder Intelligence"; multi-brand selection | `china_reorder.py` |
| 2026-05-21 | AMPM lookup: **exact Model match, case-insensitive only**. No SKU layer, no fallback | `replenishment.py`, `fc_final_allocation.py`, `cb_replenishment.py`, `wm_replenishment.py` |
| 2026-05-21 | sku_master alignment is **owned at the data layer** — code does not auto-canonicalise (user chose not to add a Layer 2 normaliser) | n/a |

Commits land on `main`; there is no `develop` branch or PR review process.
Co-author on commits is `Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.

---

## 12. Known issues / data-hygiene watchlist

Things the team is aware of but hasn't fixed:

- **Audio Array model naming drift** — variants like `AM-W47 Wired` vs
  warehouse `AM-W47 WIRED` were case-only and resolve via case-insens. But
  `AH-50 Ear Cushion` (master) vs `AH-50` (inv) is real semantic drift —
  needs data alignment.
- **Viomi has ~6 SKUs the sku_master doesn't carry** (`FBP79350`, `FBA79779`,
  `FBK79598`, `FBK79569`, `FBK79685`, `FBA79991`). These are operational /
  pipeline SKUs — decision pending whether to add to sku_master.
- **`weekly_sales_snapshot.csv` has zero Blinkit-channel rows** — code is
  wired to use `weekly_sales_snapshot - ChinaReorder.csv` (channel
  `"Blinkit Sales"`) instead.
- **Old DB password lives forever in git history** (commits `67a19b4` /
  `6e84574`). It's invalidated by the rotation, so it's just history
  noise — not a live risk.
- **`requirements.txt` is unpinned** — fresh installs could pull newer
  versions and break. Worth pinning when there's time.
- **No Alembic** — schema changes are ad-hoc `CREATE TABLE IF NOT EXISTS`
  in service files. Acceptable for now given the small surface.

---

## 13. When you (Claude) start a fresh session here

1. **Read this file first.** It saves 30+ minutes of context-building.
2. Run `git log --oneline -20` to see what's recent.
3. If the user says "rerun the audit", check `D:/Nitesh/Normalization/`
   for the latest sku_master/master files and produce a new
   `mismatches_<date>.xlsx`.
4. If the user mentions "AMPM 0 for X" — the rule is exact case-insens
   Model match (§5). Don't propose SKU-keyed or base-token fallback;
   that ground was covered.
5. Before any deploy-affecting change, smoke-test locally where possible,
   then push and ask the user to verify with `scripts/healthcheck.py`.
6. The user prefers **short messages**, **fast-ship over enterprise**,
   and commit+push together when authorized. Always show what will be
   committed (`git status`) before committing.
