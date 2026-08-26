"""Replenishment Watchlist — models that need a human decision this week.

Operator brief (2026-08-26): Naresh needs a single view of "what should I be
pushing", built the way a senior replenishment person eyeballs a model —
not a dump of flags. Two signals were named explicitly:

  1. It LOST SALES because the mother warehouse ran thin — and the follow-up
     question that actually decides the action: is relief already on the water
     from China, or is there nothing coming?
  2. It's a NEW LAUNCH, so velocity is built on a couple of weeks of thin
     history, the system extrapolates a muted requirement, and we under-ship a
     product we're trying to rank.

Explicit instruction: "no BS, only real suggestions which can be generated".
So every signal below is computed from data already on the Replenishment row —
nothing is inferred, estimated, or invented. If a field is missing the row
simply doesn't qualify.

Two further signals earn their place because a replenishment lead checks them
in the same pass and both are computable:

  3. DEMAND ACCELERATING — the last-2-week run rate is materially above the
     window average (velocity_basis == "2wk"), so a window-based send
     understates what the model is now doing.
  4. STRANDED AT MOTHER WH — stock is sitting at AMPM, the model is selling,
     and yet the calc suggests sending nothing. Usually a carton-rounding or
     buffer-gate artefact; always worth a human look.

Deliberately NOT flagged:
  - EOL models are never suggested for "push more". Pushing stock into a line
    we're exiting is the most expensive mistake on this page.
  - Fossil is excluded entirely — it has no ASIN Type, its own PO-tracker
    flow, and a different approver chain.
"""
from __future__ import annotations

import io
import contextlib

import pandas as pd

# Accounts this module covers. Fossil deliberately absent (see module docstring).
WATCHLIST_ACCOUNTS = ["NEXLEV", "VIOMI", "AUDIO ARRAY", "WHITE MULBERRY"]

# ASIN Types that mean "still establishing" — velocity is not yet trustworthy.
NEW_LAUNCH_TYPES = {"new", "new launch", "to be launched"}

# MATERIALITY — a watchlist is only useful if every line is worth a decision.
# Without these the module emitted 187 rows including "system asks 0, AMPM
# holds 1", which is noise a replenishment lead would scroll straight past.
# A signal must clear BOTH an absolute floor and one week of the model's own
# velocity, so a fast mover qualifies on a smaller relative gap than a slow one.
MIN_UNITS_AT_STAKE = 20          # absolute floor, units
MIN_WEEKS_OF_VELOCITY = 1.0      # ... and at least this many weeks of demand

# ...but a flat 20-unit floor is the WRONG test for a slow mover, and it was
# silently excluding whole brands. Tonor sells 1-2/wk: TM20 lost 18 units,
# which is NINE WEEKS of its own demand, and the floor threw it away while
# waving through a 20-unit gap on a model that sells 40/wk (half a week).
# So a row also qualifies on a purely relative basis: a long outage measured
# in the model's own weeks of demand. The small absolute guard stops
# near-zero-velocity noise (0.2/wk * 4 = 1 unit is not a decision).
LONG_OUTAGE_WEEKS = 4.0          # weeks of the model's own demand
LONG_OUTAGE_MIN_UNITS = 5        # ... with a floor so tiny movers stay out


def _material(units_at_stake: float, velocity: float) -> bool:
    if (units_at_stake >= MIN_UNITS_AT_STAKE
            and units_at_stake >= velocity * MIN_WEEKS_OF_VELOCITY):
        return True
    return (velocity > 0
            and units_at_stake >= velocity * LONG_OUTAGE_WEEKS
            and units_at_stake >= LONG_OUTAGE_MIN_UNITS)


# Priority order for sorting; lower sorts first.
_SIGNAL_RANK = {
    "LOST_SALES_NO_RELIEF": 0,
    "LOST_SALES_RELIEF_INBOUND": 1,
    "NEW_LAUNCH_MUTED": 2,
    "DEMAND_ACCELERATING": 3,
    "STRANDED_AT_MOTHER_WH": 4,
    "EOL_STILL_SELLING": 5,
}


def _s(row, key) -> str:
    """String field, NaN-safe. `row.get(k) or ""` is NOT enough: pandas puts
    float('nan') in missing object cells and NaN is TRUTHY in Python, so the
    nan survives into the response and FastAPI raises
    "Out of range float values are not JSON compliant: nan".
    """
    v = row.get(key)
    if v is None:
        return ""
    try:
        if isinstance(v, float) and pd.isna(v):
            return ""
    except Exception:
        pass
    sv = str(v).strip()
    return "" if sv.lower() in ("nan", "none", "<na>") else sv


def _int_or_none(row, key):
    """Nullable int for columns that are legitimately empty on some rows.
    cb_soh is None for every account/brand without vendor-warehouse stock —
    that is a real "not applicable", not a zero, and must not render as 0.
    """
    v = row.get(key)
    if v is None or v is pd.NA:
        return None
    try:
        if isinstance(v, float) and pd.isna(v):
            return None
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        return int(v)
    except Exception:
        return None


def _num(row, key, default=0.0) -> float:
    try:
        v = row.get(key, default)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _rows_for_account(account: str, sales_window: int, replenish_weeks: int,
                      velocity_mode: str) -> pd.DataFrame:
    from app.services.replenishment import calculate_replenishment
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return calculate_replenishment(
            sales_window=sales_window,
            replenish_weeks=replenish_weeks,
            account=account,
            velocity_mode=velocity_mode,
        )


def _classify(r: dict, account: str, replenish_weeks: int) -> list[dict]:
    """Return zero or more signals for one model row. A model can legitimately
    raise more than one (e.g. lost sales AND accelerating)."""
    out: list[dict] = []

    asin_type = _s(r, "asin_type")
    is_eol = asin_type.lower() == "eol" or bool(r.get("is_eol"))

    vel        = _num(r, "sales_velocity")
    win_vel    = _num(r, "window_velocity", vel)
    l2_vel     = _num(r, "last_2_velocity")
    ampm       = _num(r, "model_ampm_inventory", _num(r, "ampm_inventory"))
    am_avail   = _num(r, "real_am_inv_available")
    pipeline   = _num(r, "china_pipeline")
    replen     = _num(r, "replenishment_qty")
    shortfall  = _num(r, "warehouse_shortfall")
    lost       = _num(r, "lost_units_3m")
    oos_wks    = _num(r, "oos_weeks_3m")
    thin_wks   = _num(r, "thin_weeks_3m")
    flag       = _s(r, "momentum_flag").upper()
    # CB SOH = final_cb_qty, the 1P vendor stock sitting in the CB warehouse.
    # Populated ONLY for Audio Array and for Tonor under the Viomi account;
    # None everywhere else, which means "no vendor warehouse", not zero.
    cb_soh     = _int_or_none(r, "cb_soh")

    # Weeks of cover currently at Amazon, on the velocity actually in use.
    cover = (am_avail / vel) if vel > 0 else None

    # 1P channel state — see the long note further down for what CB SOH is.
    # Must be computed BEFORE `base`, which publishes both fields.
    cb_cover = (cb_soh / vel) if (cb_soh and vel > 0) else None
    cb_live  = cb_soh is not None and cb_soh > 0
    cb_dark  = cb_soh is not None and cb_soh <= 0

    base = {
        "account":        account,
        "brand":          _s(r, "brand"),
        "model":          _s(r, "model"),
        "sku":            _s(r, "sku"),
        "asin":           _s(r, "asin"),
        "asin_type":      asin_type,
        "velocity":       round(vel, 1),
        "window_velocity": round(win_vel, 1),
        "last_2_velocity": round(l2_vel, 1),
        "velocity_basis": _s(r, "velocity_basis") or "window",
        "amazon_available": int(am_avail),
        "weeks_cover":    (round(cover, 1) if cover is not None else None),
        "mother_wh":      int(ampm),
        "cb_soh":         cb_soh,
        # Weeks of cover the 1P side holds at this model's 3P run rate — a
        # rough read across two channels, but enough to tell "1P was serving
        # the customer" from "both channels dark".
        "cb_soh_weeks":   (round(cb_cover, 1) if cb_cover is not None else None),
        # "live" | "dark" | None (brand has no vendor channel at all)
        "cb_channel":     ("live" if cb_live else "dark" if cb_dark else None),
        # True when 1P cover alone exceeds the replenishment horizon — the
        # "don't buy this" marker the UI leads with.
        "cb_deep":        bool(cb_live and cb_cover is not None
                               and cb_cover >= replenish_weeks),
        "china_pipeline": int(pipeline),
        "replen_qty":     int(replen),
        "warehouse_shortfall": int(shortfall),
        "lost_units_3m":  int(lost),
        "oos_weeks_3m":   int(oos_wks),
        "thin_weeks_3m":  int(thin_wks),
        "momentum_flag":  flag,
    }

    # ---- What CB SOH actually is, and how it must be read -----------------
    # CB SOH = sellableOnHandInventoryUnits from SP-API's
    # GET_VENDOR_INVENTORY_REPORT (scripts/sp_vendor_soh_pull.py), i.e. stock
    # AMAZON ALREADY OWNS and holds in its 1P retail warehouses. It is NOT
    # Cambium warehouse stock and CANNOT be shipped into FBA to cover a 3P
    # gap — it has already been sold to Amazon under the vendor relationship.
    #
    # What it DOES tell us is which channel was serving the customer while the
    # 3P side ran thin, and that changes the read on a lost-sales signal:
    #   * 1P holding cover  -> the ASIN stayed buyable on Amazon.in, so
    #     lost_units_3m (computed from the 3P/AMPM side alone) is an UPPER
    #     BOUND on truly lost demand, not a measured loss.
    #   * 1P at zero        -> the ASIN went dark on BOTH channels. That is
    #     the genuinely urgent case and it is currently invisible on this page.
    #
    # We annotate rather than discount the number: we hold a CURRENT 1P
    # snapshot, not 1P history, so there is no honest way to net it off the
    # last 13 weeks. Stating an upper bound is real; a computed discount
    # would be invented.
    # When the 1P side is holding DEEP cover, "raise a China PO now" is not
    # just imprecise, it is the wrong instruction — AM-W45 showed 387 "lost"
    # units against 355 units sitting in Amazon's 1P warehouse, 71 weeks of
    # cover at the 3P run rate. Buying more of that is the expensive mistake
    # this page exists to prevent, so the ACTION changes, not just the note.
    cb_deep = (cb_live and cb_cover is not None and cb_cover >= replenish_weeks)

    cb_hint = ""
    if cb_deep:
        cb_hint = (f" HOLD: 1P (CB) holds {cb_soh} sellable units, ~{cb_cover:.0f} "
                   f"weeks at this run rate — the demand is being served on the "
                   f"1P offer, so this is a channel shift, not lost demand. Do "
                   f"not raise a China PO on this evidence; if we want the 3P "
                   f"offer live, the question is a 1P->3P commercial decision, "
                   f"not replenishment.")
    elif cb_live and cb_cover is not None and cb_cover >= 2:
        cb_hint = (f" Note: 1P (CB) held {cb_soh} sellable units "
                   f"(~{cb_cover:.0f} wks) at the last vendor snapshot, so the "
                   f"listing stayed buyable — treat the lost-units figure as an "
                   f"upper bound and sanity-check 1P offtake before sizing an "
                   f"urgent PO.")
    elif cb_live:
        cb_hint = (f" 1P (CB) held only {cb_soh} sellable units at the last "
                   f"vendor snapshot — thin on that side too.")
    elif cb_dark:
        cb_hint = (" 1P (CB) is at ZERO sellable as well — the ASIN went dark "
                   "on both channels, so this is lost demand, not a channel "
                   "shift. Treat as urgent.")

    # ---- 1/2. Lost sales, split by whether relief is already coming --------
    # Only counts as lost-sales if we actually have evidence of demand AND of
    # running thin — a zero-velocity SKU sitting at zero isn't a lost sale.
    lost_sales = (lost > 0 or flag in ("RED", "AMBER")) and vel > 0
    if lost_sales and _material(lost, vel):
        if pipeline > 0 and not is_eol:
            out.append({**base,
                "signal": "LOST_SALES_RELIEF_INBOUND",
                "units_at_stake": int(lost),
                "headline": f"Lost ~{int(lost)} units in 3m — {int(pipeline)} inbound from China",
                "why": (
                    f"{int(oos_wks)} week(s) fully out and {int(thin_wks)} thin at the mother "
                    f"warehouse in the last 13. Selling {vel:g}/wk. "
                    f"{int(pipeline)} units are in transit from China."
                ),
                "action": (
                    "Relief is on the water — plan the inward and get an FBA send "
                    "raised the day it lands. Check the ETA covers the gap; if not, "
                    "expedite or air-freight a part quantity." + cb_hint
                ),
            })
        else:
            if is_eol:
                # Never tell anyone to buy into a line we're exiting. The
                # decision here is whether the EOL call itself still holds.
                out.append({**base,
                    "signal": "EOL_STILL_SELLING",
                    "units_at_stake": int(lost),
                    "headline": f"EOL but still selling {vel:g}/wk — lost ~{int(lost)} units",
                    "why": (
                        f"Marked EOL, yet it moved enough to lose ~{int(lost)} units over "
                        f"13 weeks ({int(oos_wks)} out, {int(thin_wks)} thin) and is still "
                        f"selling {vel:g}/wk with {int(ampm)} at AMPM."
                    ),
                    "action": (
                        "Confirm the EOL call. If we are genuinely exiting, no action — "
                        "the lost sales are the plan. If not, re-classify the ASIN Type "
                        "and treat it as a normal China PO."
                    ),
                })
                return out
            out.append({**base,
                "signal": "LOST_SALES_NO_RELIEF",
                "units_at_stake": int(lost),
                "headline": f"Lost ~{int(lost)} units in 3m — nothing inbound from China",
                "why": (
                    f"{int(oos_wks)} week(s) fully out and {int(thin_wks)} thin at the mother "
                    f"warehouse in the last 13. Selling {vel:g}/wk with "
                    f"{int(ampm)} left at AMPM and no China pipeline."
                ),
                "action": (
                    cb_hint.strip() if cb_deep else (
                        "Raise a China PO now — this is repeat lost revenue, not a one-off. "
                        + (f"Mother WH is {int(shortfall)} short of the full ask this week."
                           if shortfall > 0 else
                           "Ship what AMPM holds this week while the PO runs.")
                        + cb_hint
                    )
                ),
            })

    # ---- 3. New launch with a muted requirement ---------------------------
    # Velocity on a launch is built from a couple of weeks of thin history, so
    # the calc under-asks exactly when we're trying to build rank.
    if (asin_type.lower() in NEW_LAUNCH_TYPES) and not is_eol and ampm > 0:
        headroom = int(ampm - replen)
        if headroom > 0 and _material(headroom, vel):
            out.append({**base,
                "signal": "NEW_LAUNCH_MUTED",
                "units_at_stake": int(headroom),
                "headline": f"New launch — system asks {int(replen)}, AMPM holds {int(ampm)}",
                "why": (
                    f"ASIN Type '{asin_type}'. Velocity of {vel:g}/wk is built on a short "
                    f"post-launch history, so {replenish_weeks}-week cover computes a small "
                    f"requirement. {headroom} units of headroom sit at the mother warehouse."
                ),
                "action": (
                    "Judgement call: push above the system number to build rank and "
                    "review velocity weekly. The calc will catch up once real sales "
                    "history accumulates — it is not saying demand is low."
                ),
            })

    # ---- 4. Demand accelerating ------------------------------------------
    # Only when the 2-week rate is MATERIALLY above the window (>=1.5x and a
    # real unit gap), otherwise every mild wobble would flag.
    if (not is_eol and win_vel > 0 and l2_vel >= win_vel * 1.5
            and (l2_vel - win_vel) >= 1):
        thin_cover = cover is not None and cover < replenish_weeks
        gap_units = (l2_vel - win_vel) * replenish_weeks
        if thin_cover and _material(gap_units, vel):
            out.append({**base,
                "signal": "DEMAND_ACCELERATING",
                "units_at_stake": int(gap_units),
                "headline": f"Run rate up: {l2_vel:g}/wk last 2wk vs {win_vel:g}/wk window",
                "why": (
                    f"Amazon holds {int(am_avail)} = {cover:.1f} weeks at the current rate, "
                    f"below the {replenish_weeks}-week target."
                ),
                "action": (
                    "Size the send off the 2-week rate, not the window — set Velocity "
                    "basis to 'Higher of window / 2wk' and re-check the qty before proposing."
                ),
            })

    # ---- 5. Stranded at the mother warehouse ------------------------------
    if (not is_eol and vel > 0 and ampm > 0 and replen <= 0
            and cover is not None and cover < replenish_weeks
            and _material(ampm, vel)):
        out.append({**base,
            "signal": "STRANDED_AT_MOTHER_WH",
                "units_at_stake": int(min(ampm, vel * replenish_weeks)),
            "headline": f"{int(ampm)} at AMPM but nothing suggested",
            "why": (
                f"Selling {vel:g}/wk with only {cover:.1f} weeks at Amazon, yet the calc "
                f"suggests 0. Usually carton rounding or the buffer gate."
            ),
            "action": (
                "Check Master Carton and the buffer note on the Replenishment row — "
                "if the gap is real, override the Working value manually."
            ),
        })

    return out


def build_watchlist(accounts: list[str] | None = None,
                    sales_window: int = 12,
                    replenish_weeks: int = 8,
                    velocity_mode: str = "max",
                    asin_types: list[str] | None = None) -> dict:
    """Watchlist rows across accounts, highest-priority signal first.

    `asin_types` filters to the given ASIN Types (case-insensitive). It is
    applied SERVER-side rather than in the browser so the email draft and the
    on-screen list can never disagree — the draft is built from the same
    filtered set the operator is looking at. `asin_types_available` always
    reports the unfiltered options so the chips don't disappear once one is
    selected.
    """
    accts = [a for a in (accounts or WATCHLIST_ACCOUNTS)
             if a.strip().upper() != "FOSSIL"]
    rows: list[dict] = []
    errors: list[str] = []

    for acct in accts:
        try:
            df = _rows_for_account(acct, sales_window, replenish_weeks, velocity_mode)
        except Exception as e:
            errors.append(f"{acct}: {type(e).__name__}: {e}")
            continue
        if df is None or df.empty:
            continue
        # Normalise the column names this module reads.
        d = df.copy()
        d.columns = [str(c).strip() for c in d.columns]
        # Both cases can be present at once and only ONE of them is populated
        # for a given block of rows — the Tonor rows lifted from the AA sheet
        # carry `SKU` and leave `sku` NaN. Picking the first column that
        # merely EXISTS therefore blanked the SKU on every Tonor card, so
        # coalesce across the candidates instead of choosing one.
        for want, cands in {
            "sku":   ("sku", "SKU"),
            "asin":  ("asin", "ASIN"),
            "model": ("model", "Model"),
        }.items():
            present = [c for c in cands if c in d.columns]
            if not present:
                continue
            col = d[present[0]]
            for c in present[1:]:
                col = col.where(col.notna() & (col.astype(str).str.strip() != ""), d[c])
            d = d.drop(columns=[c for c in present if c != want], errors="ignore")
            d[want] = col
        for r in d.to_dict(orient="records"):
            rows.extend(_classify(r, acct, replenish_weeks))

    # Options for the chip row — computed BEFORE filtering, so selecting one
    # type doesn't remove the others from the UI.
    available = sorted({r["asin_type"] for r in rows if r.get("asin_type")},
                       key=str.lower)

    # Match case-insensitively but report back the canonical labels, so the
    # email subject reads "ASIN Type: New Launch", not "new launch".
    wanted = {t.strip().lower() for t in (asin_types or []) if t and t.strip()}
    selected_labels: list[str] = []
    if wanted:
        rows = [r for r in rows if (r.get("asin_type") or "").lower() in wanted]
        by_lower = {a.lower(): a for a in available}
        selected_labels = [by_lower.get(t, t) for t in sorted(wanted)]

    rows.sort(key=lambda x: (
        _SIGNAL_RANK.get(x["signal"], 99),
        # Within a signal, a model that is ALSO dark on the 1P side outranks
        # one whose 1P offer stayed live — the first is genuinely unbuyable,
        # the second only shifted channel. Rows with no vendor channel at all
        # (cb_channel None) sort between the two: unknown, not good news.
        {"dark": 0, None: 1, "live": 2}.get(x.get("cb_channel"), 1),
        -(x.get("units_at_stake") or 0),
        -(x.get("velocity") or 0),
    ))

    # Final guard: any non-finite float anywhere in the payload would 500 the
    # endpoint at serialization time. Cheap to scrub, expensive to debug live.
    import math
    for r in rows:
        for k, v in list(r.items()):
            if isinstance(v, float) and not math.isfinite(v):
                r[k] = None

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["signal"]] = counts.get(r["signal"], 0) + 1

    return {
        "rows": rows,
        "counts": counts,
        "accounts": accts,
        "asin_types_available": available,
        "asin_types": selected_labels,
        "sales_window": sales_window,
        "replenish_weeks": replenish_weeks,
        "velocity_mode": velocity_mode,
        "errors": errors,
    }


# ============================================================
# EMAIL DRAFT
# ============================================================
# Routing per operator, 2026-08-26. Addresses verified against app_users —
# none invented. Naresh drafts; the approver chain differs by account group.
NARESH = "nareshmore.cambiuamretail@gmail.com"   # domain typo is deliberate,
                                                 # see the RBAC memory note.
_ALWAYS_CC = ["unmesha@cambiumretail.com", "ceo@cambiumretail.com",
              "zaid@cambiumretail.com", "nitesh@cambiumretail.com"]

EMAIL_ROUTING = {
    # Nexlev / Viomi / White Mulberry -> Sagar
    "NEXLEV":         {"to": ["sagar@cambiumretail.com"],  "cc": _ALWAYS_CC},
    "VIOMI":          {"to": ["sagar@cambiumretail.com"],  "cc": _ALWAYS_CC},
    "WHITE MULBERRY": {"to": ["sagar@cambiumretail.com"],  "cc": _ALWAYS_CC},
    # Audio Array / Fossil -> Tushar + Kanwal
    "AUDIO ARRAY":    {"to": ["tushar@cambiumretail.com",
                              "kanwal@cambiumretail.com"], "cc": _ALWAYS_CC},
    "FOSSIL":         {"to": ["tushar@cambiumretail.com",
                              "kanwal@cambiumretail.com"], "cc": _ALWAYS_CC},
}

_SIGNAL_TITLE = {
    "LOST_SALES_NO_RELIEF":      "Lost sales — no China arrival",
    "LOST_SALES_RELIEF_INBOUND": "Lost sales — stock inbound from China",
    "NEW_LAUNCH_MUTED":          "New launch — requirement understated",
    "DEMAND_ACCELERATING":       "Demand accelerating",
    "STRANDED_AT_MOTHER_WH":     "Stock at mother WH, nothing suggested",
    "EOL_STILL_SELLING":         "EOL but still selling — confirm the call",
}


def recipients_for(accounts: list[str]) -> dict:
    """Merge the routing for every account in scope. Keeps `to` de-duplicated
    and never lets an address appear in both to and cc."""
    to, cc = [], []
    for a in accounts:
        r = EMAIL_ROUTING.get(a.strip().upper())
        if not r:
            continue
        for x in r["to"]:
            if x not in to:
                to.append(x)
        for x in r["cc"]:
            if x not in cc:
                cc.append(x)
    cc = [x for x in cc if x not in to]
    return {"from": NARESH, "to": to, "cc": cc}


def build_email_draft(watchlist: dict, week_tag: str | None = None,
                      max_rows_per_signal: int = 8) -> dict:
    """Editable draft summarising the watchlist. Body is plain text so the
    operator can paste it anywhere and edit freely before sending."""
    rows = watchlist.get("rows", [])
    accounts = watchlist.get("accounts", [])
    rec = recipients_for(accounts)

    wk = week_tag or ""
    scope = ", ".join(accounts)
    types = watchlist.get("asin_types") or []
    type_scope = (" · ASIN Type: " + ", ".join(types)) if types else ""
    subject = (f"Replenishment watchlist{(' — ' + wk) if wk else ''} — "
               f"{scope}{type_scope} ({len(rows)} models to review)")

    L: list[str] = []
    L.append("Hi,")
    L.append("")
    L.append(f"Below is this week's replenishment watchlist for {scope}"
             f"{(' (' + wk + ')') if wk else ''}"
             + (f", filtered to ASIN Type {', '.join(types)}" if types else "")
             + ". "
             "These are models where the system number alone would under-serve "
             "demand, with the reason and the suggested action for each.")
    L.append("")

    by_signal: dict[str, list] = {}
    for r in rows:
        by_signal.setdefault(r["signal"], []).append(r)

    for sig in _SIGNAL_RANK:                      # keep priority order
        group = by_signal.get(sig) or []
        if not group:
            continue
        total = sum(int(g.get("units_at_stake") or 0) for g in group)
        L.append(f"{_SIGNAL_TITLE.get(sig, sig)} — {len(group)} model(s), "
                 f"~{total:,} units at stake")
        L.append("-" * 72)
        for g in group[:max_rows_per_signal]:
            L.append(f"  {g['account']} | {g['model']} ({g['sku']}) "
                     f"[{g['asin_type'] or 'no ASIN type'}]")
            L.append(f"    {g['headline']}")
            if g.get("cb_soh") is not None:
                _n = g["cb_soh"]
                _w = g.get("cb_soh_weeks")
                if _n > 0:
                    L.append(f"    1P (CB) SOH: {_n} sellable"
                             + (f" (~{_w:g} wks cover)" if _w else "")
                             + " — listing stayed buyable on the 1P offer")
                else:
                    L.append("    1P (CB) SOH: 0 — dark on the 1P side too")
            L.append(f"    Why   : {g['why']}")
            L.append(f"    Action: {g['action']}")
            L.append("")
        if len(group) > max_rows_per_signal:
            L.append(f"  ... and {len(group) - max_rows_per_signal} more in the "
                     f"attached/linked watchlist.")
            L.append("")

    L.append("Figures are from the Replenishment tab for the selected sales "
             f"window ({watchlist.get('sales_window')} weeks) at "
             f"{watchlist.get('replenish_weeks')}-week cover, velocity basis "
             f"'{watchlist.get('velocity_mode')}'.")
    L.append("")
    L.append("Thanks,")
    L.append("Naresh")

    return {
        "from": rec["from"],
        "to": rec["to"],
        "cc": rec["cc"],
        "subject": subject,
        "body": "\n".join(L),
        "row_count": len(rows),
        "accounts": accounts,
    }
