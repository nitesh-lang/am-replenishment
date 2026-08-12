import { useEffect, useMemo, useRef, useState } from "react";
import {
  listPlans, getPlan, editLine, addLine, deleteLine, approvePlan, pushPlan,
  sendToApprover, deletePlan, requestRework,
} from "../api/plans";
import { useAuth } from "../auth/AuthContext";

const STATUS_COLORS = {
  draft:    "#8b5cf6",   // purple — editor-owned
  proposed: "#f59e0b",   // amber — approver-owned
  approved: "#10b981",   // green
  pushed:   "#3b82f6",   // blue
  failed:   "#ef4444",   // red
};

function fmt(dt) {
  if (!dt) return "—";
  const d = new Date(dt);
  return d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour12: false });
}

export default function PlansApproval() {
  const { user } = useAuth();
  const isApprover = (user?.allowedModules || []).includes("plans-approver") || user?.role === "admin";
  const isEditor   = (user?.allowedModules || []).includes("plans-editor")   || user?.role === "admin";

  const [batches, setBatches] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [batch, setBatch] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  // Default: show ALL so editors see both their drafts and their already-sent
  // proposals (and approvers see everything they can act on).
  const [statusFilter, setStatusFilter] = useState("");

  async function refreshList() {
    setErr("");
    try {
      const j = await listPlans({ status: statusFilter || undefined });
      setBatches(j.batches || []);
    } catch (e) {
      setErr(e.message);
    }
  }

  async function loadBatch(id) {
    setLoading(true);
    setErr("");
    try {
      const j = await getPlan(id);
      setBatch(j.batch);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refreshList(); }, [statusFilter]);
  useEffect(() => { if (selectedId) loadBatch(selectedId); }, [selectedId]);

  return (
    <div style={{ padding: 24, fontFamily: "Poppins, sans-serif" }}>
      <h2 style={{ margin: 0, marginBottom: 4 }}>Plans Approval</h2>
      <div style={{ color: "#6b7280", fontSize: 13, marginBottom: 16 }}>
        Review, edit, add or remove rows in a proposed plan. Approver has full authority.
        Push to OrderPilot is currently a stub — approval alone doesn't move stock yet.
      </div>

      {err && (
        <div style={{ background: "#fee2e2", color: "#991b1b", padding: 12, borderRadius: 6, marginBottom: 16 }}>
          {err}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 16 }}>
        {/* ─── LEFT: batch list ─── */}
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
            <label style={{ fontSize: 12, color: "#6b7280" }}>Status:</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ padding: 6, borderRadius: 4, border: "1px solid #d1d5db" }}
            >
              <option value="">All</option>
              <option value="draft">Draft (editor)</option>
              <option value="proposed">Proposed (approver)</option>
              <option value="approved">Approved</option>
              <option value="pushed">Pushed</option>
              <option value="failed">Failed</option>
            </select>
          </div>
          <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, maxHeight: "70vh", overflow: "auto" }}>
            {batches.length === 0 && (
              <div style={{ padding: 12, color: "#6b7280", fontSize: 12, lineHeight: 1.5 }}>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>No batches in this view.</div>
                <div style={{ marginBottom: 8 }}>
                  <b>Editor flow (Naresh):</b>
                  <ol style={{ margin: "4px 0 0 18px", padding: 0 }}>
                    <li>FC Allocation or Fossil Replenishment → <b>Save Draft</b> (creates a purple draft)</li>
                    <li>Come here → filter <b>Draft</b> → edit qty / add / remove rows</li>
                    <li>Click <b>→ Send to Approver</b> when ready</li>
                  </ol>
                </div>
                <div style={{ marginBottom: 8 }}>
                  <b>Approver flow (Sagar / Kanwal):</b> filter <b>Proposed</b> → curate → <b>Approve</b>.
                </div>
                <div style={{ color: "#9ca3af" }}>
                  Not seeing the buttons? Confirm the user has <code>plans-editor</code> or
                  <code>plans-approver</code> in allowed_modules (admin panel).
                </div>
              </div>
            )}
            {batches.map((b) => {
              const mine = (b.proposed_by || "").toLowerCase() === (user?.email || "").toLowerCase();
              return (
                <div
                  key={b.batch_id}
                  onClick={() => setSelectedId(b.batch_id)}
                  style={{
                    padding: 10, borderBottom: "1px solid #f3f4f6", cursor: "pointer",
                    background: selectedId === b.batch_id ? "#eff6ff" : "white",
                    borderLeft: mine ? "3px solid #8b5cf6" : "3px solid transparent",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                    <strong style={{ fontSize: 13 }}>
                      {b.account}
                      {mine && <span style={{ marginLeft: 6, fontSize: 10, color: "#8b5cf6", fontWeight: 600 }}>MINE</span>}
                    </strong>
                    <span style={{
                      padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600,
                      background: STATUS_COLORS[b.status] || "#9ca3af", color: "white",
                    }}>{b.status}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
                    {b.proposed_by} · {fmt(b.proposed_at)}
                  </div>
                  {b.source_module && (
                    <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2 }}>
                      from <b>{b.source_module}</b> → {b.approver_email || "any approver"}
                    </div>
                  )}
                  <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 2 }}>{b.batch_id}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ─── RIGHT: batch detail ─── */}
        <div>
          {!batch && !loading && (
            <div style={{ padding: 24, color: "#9ca3af", textAlign: "center" }}>
              Select a batch on the left.
            </div>
          )}
          {loading && <div style={{ padding: 24 }}>Loading…</div>}
          {batch && <BatchDetail batch={batch} onReload={() => loadBatch(batch.batch_id)}
                                 isApprover={isApprover} isEditor={isEditor}
                                 currentEmail={(user?.email || "").toLowerCase()} />}
        </div>
      </div>
    </div>
  );
}

function BatchDetail({ batch, onReload, isApprover, isEditor, currentEmail }) {
  const s = batch.summary || {};
  const ownDraft = batch.status === "draft" &&
                   ((batch.proposed_by || "").toLowerCase() === currentEmail || isApprover);
  // Editors edit their own drafts; approvers edit proposed batches assigned
  // to them. Admin bypasses via isApprover being true.
  const canEdit = (isEditor && ownDraft) ||
                  (isApprover && batch.status === "proposed");
  const canSend = isEditor && ownDraft;
  const canApprove = isApprover && batch.status === "proposed";
  const canPush = isApprover && batch.status === "approved";
  // Delete permissions (mirrored from backend):
  //  - draft    -> proposer (or admin)
  //  - proposed -> assigned approver (or admin)
  //  - approved / pushed -> admin only (audit-preserving)
  const canDelete =
    (batch.status === "draft" && (ownDraft || currentEmail === (batch.proposed_by || "").toLowerCase())) ||
    (batch.status === "proposed" && isApprover) ||
    ((batch.status === "approved" || batch.status === "pushed") && isApprover /* admin has isApprover=true */);

  const [showAdd, setShowAdd] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // Track pending in-flight save Promises from LineRow (qty/notes/exclude
  // auto-saves). Approve and Push must await these before firing so the
  // server sees the fresh qty. Without this, Sagar can edit qty → click
  // Approve immediately; the blur triggers the PATCH but the setTimeout
  // wins the race, approve lands first, PATCH errors out with "batch is
  // approved; not open for edits", and OrderPilot ships the ORIGINAL qty.
  const pendingSavesRef = useRef([]);
  function trackSave(promise) {
    pendingSavesRef.current.push(promise);
    // Prune on settle so the array doesn't grow forever. The .catch on
    // the tail keeps the finally-chain from surfacing as an unhandled
    // rejection — the caller (LineRow) already handles the error via
    // its own try/catch + alert.
    promise
      .finally(() => {
        pendingSavesRef.current = pendingSavesRef.current.filter((p) => p !== promise);
      })
      .catch(() => {});
    return promise;
  }
  async function flushPendingSaves() {
    if (document.activeElement && document.activeElement.blur) {
      document.activeElement.blur();
    }
    // Yield twice — first tick lets the blur event handler run
    // (LineRow.onBlur → save() → editLine → trackSave), second tick lets
    // the pushed Promise land in pendingSavesRef.current.
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    if (pendingSavesRef.current.length) {
      // allSettled — one failed save shouldn't block approve. The user
      // would have seen the alert from the failing save.
      await Promise.allSettled(pendingSavesRef.current.slice());
    }
  }

  async function act(fn) {
    setBusy(true); setErr("");
    try { await fn(); await onReload(); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div>
      {/* Summary strip */}
      <div style={{
        background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6,
        padding: 12, marginBottom: 12, display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)", gap: 12,
      }}>
        <Stat label="Account" value={batch.account} />
        <Stat label="From tab" value={batch.source_module || "—"} />
        <Stat label="Assigned to" value={batch.approver_email || "(any approver)"} />
        <Stat label="Status" value={batch.status} color={STATUS_COLORS[batch.status]} />
      </div>
      <div style={{
        background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6,
        padding: 12, marginBottom: 12, display: "grid",
        gridTemplateColumns: "repeat(6, 1fr)", gap: 12,
      }}>
        <Stat label="Total Units" value={s.total_units} />
        <Stat label="Unique SKUs" value={s.unique_skus} />
        <Stat label="Unique FCs" value={s.unique_fcs} />
        <Stat label="Cover wks" value={batch.cover_weeks ?? "—"} />
        <Stat label="OrderPilot ships" value={_shipmentBuckets(batch.lines || [])}
              color="#8b5cf6" />
        <Stat
          label={_skippedLineCount(batch.lines || []) > 0 ? "Skipped in push" : "Δ vs original"}
          value={_skippedLineCount(batch.lines || []) > 0
            ? `${_skippedLineCount(batch.lines || [])} rows`
            : (s.delta_units > 0 ? "+" : "") + s.delta_units}
          color={_skippedLineCount(batch.lines || []) > 0
            ? "#ef4444"
            : (s.delta_units === 0 ? "#6b7280" : s.delta_units > 0 ? "#10b981" : "#ef4444")} />
      </div>

      {/* Filter context — what Naresh had selected when he proposed */}
      {batch.filter_context && Object.keys(batch.filter_context).length > 0 && (
        <div style={{
          background: "#eef2ff", border: "1px solid #c7d2fe", borderRadius: 6,
          padding: 8, marginBottom: 12, display: "flex", flexWrap: "wrap", gap: 6,
          alignItems: "center",
        }}>
          <span style={{ fontSize: 10, color: "#4338ca", fontWeight: 600, textTransform: "uppercase", marginRight: 4 }}>
            Proposer's filters:
          </span>
          {Object.entries(batch.filter_context).map(([k, v]) => {
            const label = k.replace(/_/g, " ");
            const val =
              v === null || v === undefined || v === "" ? "—" :
              Array.isArray(v) ? (v.length === 0 ? "—" : v.join(", ")) :
              String(v);
            if (val === "—" || val === "all" || val === "All") return null;
            return (
              <span key={k} style={{
                fontSize: 11, background: "white", border: "1px solid #c7d2fe",
                borderRadius: 4, padding: "2px 6px", color: "#312e81",
              }}>
                <span style={{ color: "#6366f1", marginRight: 4 }}>{label}:</span>
                <b>{val}</b>
              </span>
            );
          })}
        </div>
      )}

      {/* Approver feedback — banner visible to everyone who has ever
          worked on this batch. Editor sees this when they view their
          draft after a rework request. */}
      {batch.approver_feedback && (
        <div style={{
          background: "#fef3c7", border: "1px solid #f59e0b", borderRadius: 6,
          padding: 12, marginBottom: 12,
        }}>
          <div style={{ fontSize: 11, color: "#92400e", fontWeight: 600, marginBottom: 4, textTransform: "uppercase" }}>
            Approver Feedback {batch.status === "draft" ? "(rework requested)" : ""}
          </div>
          <div style={{ fontSize: 13, color: "#78350f", whiteSpace: "pre-wrap" }}>
            {batch.approver_feedback}
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {canEdit && (
          <button
            onClick={() => setShowAdd((x) => !x)}
            disabled={busy}
            style={btnStyle("#3b82f6")}
          >
            {showAdd ? "Cancel Add" : "+ Add Row"}
          </button>
        )}
        {canSend && (
          <button
            onClick={() => {
              if (!confirm(`Send draft ${batch.batch_id} to ${batch.approver_email || "the approver"}?`)) return;
              act(() => sendToApprover(batch.batch_id));
            }}
            disabled={busy}
            style={btnStyle("#8b5cf6")}
            title="Flip this draft to 'proposed' and hand it to the assigned approver"
          >
            → Send to Approver
          </button>
        )}
        {canApprove && (
          <>
            <button
              onClick={() => {
                const fb = prompt(`Send back to ${batch.proposed_by} with feedback:\n\n(This flips status to 'draft'. Editor can revise + re-send.)`, "");
                if (fb === null) return;
                const trimmed = fb.trim();
                if (!trimmed) {
                  alert("Feedback required to request rework.");
                  return;
                }
                act(() => requestRework(batch.batch_id, trimmed));
              }}
              disabled={busy}
              style={btnStyle("#f59e0b")}
              title="Send back to the proposer with a feedback note"
            >
              ✎ Request Rework
            </button>
            <button
              onClick={async () => {
                // Await any in-flight qty/notes/exclude PATCHes before
                // showing the confirm — otherwise the approve request
                // can win the race against a pending edit and OrderPilot
                // ends up with the pre-edit qty.
                setBusy(true);
                try {
                  await flushPendingSaves();
                  await onReload();
                } finally {
                  setBusy(false);
                }
                if (!confirm(`Approve batch ${batch.batch_id}?\n\nThis freezes the plan. All pending edits have been flushed.`)) return;
                act(() => approvePlan(batch.batch_id));
              }}
              disabled={busy}
              style={btnStyle("#10b981")}
            >
              ✓ Approve & Freeze
            </button>
          </>
        )}
        {canPush && (
          <>
            <button
              onClick={async () => {
                setBusy(true);
                try { await flushPendingSaves(); await onReload(); }
                finally { setBusy(false); }
                act(() =>
                  pushPlan(batch.batch_id, { dryRun: true }).then((r) => {
                    const preview = r.preview_shipment_ids
                      ? Object.entries(r.preview_shipment_ids).map(([fc, id]) => `  ${fc}: ${id}`).join("\n")
                      : "(no preview_shipment_ids in response)";
                    alert(`DRY RUN — no data written to OrderPilot\n\npreview shipment_ids:\n${preview}`);
                  })
                );
              }}
              disabled={busy}
              style={btnStyle("#6b7280")}
              title="Preview shipment_ids from OrderPilot without persisting"
            >
              ⓘ Dry-run Push
            </button>
            <button
              onClick={async () => {
                // Flush pending edits (exclude-toggle, approver-note,
                // etc.) BEFORE building the push confirmation — approved
                // batches shouldn't be push-editable but exclude_from_push
                // is toggleable on approved batches via edit_line (server
                // gates on 'draft' or 'proposed' only, so this is really
                // just belt-and-suspenders for edits made just before).
                setBusy(true);
                try { await flushPendingSaves(); await onReload(); }
                finally { setBusy(false); }
                if (!confirm(`Push batch ${batch.batch_id} to OrderPilot for real?\n\nThis creates shipment records in OrderPilot's 3P Shipments tab.`)) return;
                act(() =>
                  pushPlan(batch.batch_id).then((r) => {
                    if (r.status === "ok") {
                      const ids = r.shipment_ids || {};
                      alert(`Pushed successfully!\n\nOrderPilot shipment IDs:\n${Object.entries(ids).map(([fc, id]) => `  ${fc}: ${id}`).join("\n")}`);
                    } else {
                      alert(`Push failed: ${r.error || r.message || "unknown"}`);
                    }
                  })
                );
              }}
              disabled={busy}
              style={btnStyle("#f59e0b")}
              title="Push to OrderPilot for real (creates shipments)"
            >
              → Push to OrderPilot
            </button>
          </>
        )}
        {canDelete && (
          <button
            onClick={() => {
              if (!confirm(`⚠ Delete entire batch ${batch.batch_id}?\n\nAll ${batch.lines?.length || 0} rows will be permanently removed. Cannot be undone (audit event is preserved).`)) return;
              act(() => deletePlan(batch.batch_id).then(() => {
                alert("Batch deleted.");
                // Trigger navigation back — parent will re-fetch list
                window.location.hash = "";
              }));
            }}
            disabled={busy}
            style={{ ...btnStyle("#ef4444"), marginLeft: "auto" }}
            title="Delete this batch and all its rows"
          >
            🗑 Delete Plan
          </button>
        )}
      </div>

      {err && <div style={{ color: "#ef4444", marginBottom: 12 }}>{err}</div>}

      {showAdd && canEdit && <AddRowForm batch={batch} onDone={() => { setShowAdd(false); onReload(); }} />}

      {/* Lines table */}
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, overflow: "auto", maxHeight: "55vh" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f9fafb", position: "sticky", top: 0 }}>
              <Th>SKU</Th><Th>Model</Th><Th>ASIN</Th><Th>FC</Th>
              <Th title="Amazon FBA split key: Hazmat × IXD determines which shipment this line goes to">Split</Th>
              <Th align="right">Qty</Th><Th align="right">Original</Th>
              <Th align="right" title="Amazon FBA available at push time">Real AM Inv</Th>
              <Th align="right" title="AMPM / Cambium warehouse stock at push time">Mother Inv</Th>
              <Th align="right" title="Cambium vendor SOH at CB warehouse (AA only)">CB SOH</Th>
              <Th align="right" title="Sales velocity Naresh's calc used (units/wk)">Vel/wk</Th>
              <Th>Remarks</Th>
              <Th title="Approver's reason for changing qty — required whenever qty is edited so Naresh sees why">Approver Note</Th>
              <Th>Added By</Th><Th>Edited By</Th>
              <Th align="center" title="Uncheck to keep this line in the plan for audit but SKIP it when pushing to OrderPilot (e.g. MR-01 stock at Turbhe needs its own dispatch)">Push?</Th>
              {canEdit && <Th>Actions</Th>}
            </tr>
          </thead>
          <tbody>
            {(batch.lines || []).map((l) => (
              <LineRow key={l.id} line={l} canEdit={canEdit} batchId={batch.batch_id}
                       onReload={onReload} isApprover={isApprover}
                       trackSave={trackSave}
                       coverWeeks={batch.cover_weeks}
                       accountLabel={batch.account} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Event log */}
      <details style={{ marginTop: 16 }}>
        <summary style={{ cursor: "pointer", color: "#6b7280", fontSize: 12 }}>
          Event log ({batch.events?.length || 0})
        </summary>
        <div style={{ maxHeight: 240, overflow: "auto", background: "#f9fafb", padding: 8, borderRadius: 4, marginTop: 8 }}>
          {(batch.events || []).map((e) => (
            <div key={e.id} style={{ fontSize: 11, borderBottom: "1px solid #e5e7eb", padding: "4px 0" }}>
              <span style={{ color: "#6b7280" }}>{fmt(e.created_at)}</span>{" · "}
              <strong>{e.event_type}</strong>{" · "}
              <span>{e.actor}</span>
              {e.payload_json && (
                <span style={{ color: "#9ca3af", marginLeft: 8 }}>
                  {JSON.stringify(e.payload_json)}
                </span>
              )}
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

function LineRow({ line, canEdit, batchId, onReload, isApprover, trackSave, coverWeeks, accountLabel }) {
  const track = trackSave || ((p) => p);
  const [showCalc, setShowCalc] = useState(false);
  const [qty, setQty] = useState(String(line.qty));
  const [notes, setNotes] = useState(line.notes || "");
  const [approverNote, setApproverNote] = useState(line.approver_note || "");
  const [busy, setBusy] = useState(false);
  const qtyDirty   = String(line.qty) !== qty;
  const notesDirty = (line.notes || "") !== notes;
  const apprNoteDirty = (line.approver_note || "") !== approverNote;
  const dirty = qtyDirty || notesDirty || apprNoteDirty;
  const deleted = !!line.is_deleted;
  const excluded = !!line.exclude_from_push;

  async function save() {
    // If the approver changed qty, prompt for a reason and store it in
    // approver_note. Naresh sees it in the "Approver Note" column when
    // he opens the batch, so he understands why the qty changed.
    let noteForQty = approverNote;
    if (qtyDirty && isApprover) {
      const reason = prompt(
        `Reason for changing qty from ${line.qty} to ${qty}?\n\n(Required — Naresh will see this in the Approver Note column)`,
        approverNote || ""
      );
      if (reason === null) { setQty(String(line.qty)); return; }  // cancel → revert
      const trimmed = reason.trim();
      if (!trimmed) { alert("Reason is required to change qty."); return; }
      noteForQty = trimmed;
      setApproverNote(trimmed);
    }
    setBusy(true);
    try {
      await track(editLine(batchId, line.id, {
        ...(qtyDirty ? { qty: Number(qty), approver_note: noteForQty } : {}),
        ...(notesDirty ? { notes } : {}),
        ...(apprNoteDirty && !qtyDirty ? { approver_note: approverNote } : {}),
        row_version: line.row_version,
      }));
      await onReload();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  }

  async function saveNotesOnBlur() {
    if (!notesDirty) return;
    setBusy(true);
    try {
      await track(editLine(batchId, line.id, { notes, row_version: line.row_version }));
      await onReload();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  }

  async function saveApproverNoteOnBlur() {
    if (!apprNoteDirty) return;
    setBusy(true);
    try {
      await track(editLine(batchId, line.id, { approver_note: approverNote, row_version: line.row_version }));
      await onReload();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  }

  async function toggleExclude(nextValue) {
    setBusy(true);
    try {
      await track(editLine(batchId, line.id, {
        exclude_from_push: nextValue,
        row_version: line.row_version,
      }));
      await onReload();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  }

  async function del() {
    if (!confirm(`Delete ${line.sku} @ ${line.destination_fc}?`)) return;
    setBusy(true);
    try { await deleteLine(batchId, line.id); await onReload(); }
    catch (e) { alert(e.message); }
    finally { setBusy(false); }
  }

  return (
    <tr style={{
      borderBottom: "1px solid #f3f4f6",
      background: deleted ? "#fef2f2" : (excluded ? "#f3f4f6" : "white"),
      color: deleted ? "#9ca3af" : (excluded ? "#6b7280" : "inherit"),
      textDecoration: deleted ? "line-through" : "none",
      fontStyle: excluded && !deleted ? "italic" : "normal",
    }}>
      <Td>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <button
            onClick={() => setShowCalc(true)}
            title="Show Naresh's calc breakdown — velocity × cover_weeks, Amazon inv, Mother WH, CB SOH, suggested vs Working"
            style={{
              border: "none", background: "transparent", cursor: "pointer",
              fontSize: 12, padding: "2px 4px", color: "#6366f1", lineHeight: 1,
            }}
          >
            🧮
          </button>
          <span>{line.sku}</span>
        </div>
        {showCalc && (
          <CalcBreakdownModal
            line={line}
            coverWeeks={coverWeeks}
            accountLabel={accountLabel}
            onClose={() => setShowCalc(false)}
          />
        )}
      </Td>
      <Td>{line.model || "—"}</Td>
      <Td>{line.asin || "—"}</Td>
      <Td>{line.destination_fc}</Td>
      <Td>
        <div style={{ display: "flex", gap: 3 }}>
          <Badge color={line.hazmat ? "#ef4444" : "#10b981"}>
            {line.hazmat ? "HZ" : "NH"}
          </Badge>
          {line.ixd_flag && (
            <Badge color={line.ixd_flag === "IXD" ? "#3b82f6" : "#6b7280"}>
              {line.ixd_flag === "NON IXD" ? "N-IXD" : "IXD"}
            </Badge>
          )}
        </div>
      </Td>
      <Td align="right">
        {canEdit && !deleted ? (
          <input
            type="number" value={qty} onChange={(e) => setQty(e.target.value)} min={0}
            onBlur={() => { if (qtyDirty) save(); }}
            style={{ width: 70, padding: 4, textAlign: "right", border: qtyDirty ? "1px solid #f59e0b" : "1px solid #d1d5db" }}
          />
        ) : (
          <span>{line.qty}</span>
        )}
      </Td>
      <Td align="right"><span style={{ color: "#9ca3af" }}>{line.original_send_qty}</span></Td>
      <Td align="right"><span style={{ color: "#6b7280" }}>{line.real_am_inv ?? "—"}</span></Td>
      <Td align="right"><span style={{ color: "#6b7280" }}>{line.mother_inv ?? "—"}</span></Td>
      <Td align="right"><span style={{ color: "#6b7280" }}>{line.cb_soh ?? "—"}</span></Td>
      <Td align="right"><span style={{ color: "#6b7280" }}>{line.weekly_velocity != null ? Number(line.weekly_velocity).toFixed(1) : "—"}</span></Td>
      <Td>
        {canEdit && !deleted ? (
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={saveNotesOnBlur}
            placeholder="add remarks…"
            style={{
              width: 180, padding: 4, fontSize: 12,
              border: notesDirty ? "1px solid #f59e0b" : "1px solid #d1d5db",
              borderRadius: 3,
            }}
          />
        ) : (
          <span style={{ fontSize: 12, color: "#6b7280" }}>{line.notes || "—"}</span>
        )}
      </Td>
      <Td>
        {isApprover && canEdit && !deleted ? (
          <input
            type="text"
            value={approverNote}
            onChange={(e) => setApproverNote(e.target.value)}
            onBlur={saveApproverNoteOnBlur}
            placeholder="reason for edit…"
            style={{
              width: 200, padding: 4, fontSize: 12,
              border: apprNoteDirty ? "1px solid #8b5cf6" : "1px solid #d1d5db",
              borderRadius: 3, background: "#faf5ff",
            }}
          />
        ) : (
          <span style={{ fontSize: 12, color: "#7c3aed", fontStyle: line.approver_note ? "normal" : "italic" }}>
            {line.approver_note || "—"}
          </span>
        )}
      </Td>
      <Td><Badge>{line.added_by}</Badge></Td>
      <Td>{line.edited_by ? <Badge color="#f59e0b">{line.edited_by}</Badge> : "—"}</Td>
      <Td align="center">
        {deleted ? (
          <span style={{ color: "#d1d5db" }}>—</span>
        ) : canEdit ? (
          <label style={{ display: "inline-flex", alignItems: "center", gap: 4, cursor: busy ? "wait" : "pointer" }}
                 title={excluded ? "Excluded — won't be sent to OrderPilot" : "Will be included in the OrderPilot push"}>
            <input
              type="checkbox"
              checked={!excluded}
              disabled={busy}
              onChange={(e) => toggleExclude(!e.target.checked)}
              style={{ cursor: busy ? "wait" : "pointer" }}
            />
            {excluded && <span style={{ fontSize: 10, color: "#ef4444", fontWeight: 600 }}>SKIP</span>}
          </label>
        ) : (
          excluded ? <Badge color="#ef4444">SKIP</Badge> : <span style={{ color: "#10b981", fontSize: 12 }}>✓</span>
        )}
      </Td>
      {canEdit && (
        <Td>
          <div style={{ display: "flex", gap: 4 }}>
            {dirty && !deleted && <button disabled={busy} onClick={save} style={btnSmall("#3b82f6")}>Save</button>}
            {!deleted && <button disabled={busy} onClick={del} style={btnSmall("#ef4444")}>Del</button>}
          </div>
        </Td>
      )}
    </tr>
  );
}

function AddRowForm({ batch, onDone }) {
  const [sku, setSku] = useState("");
  const [fc, setFc] = useState("");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await addLine(batch.batch_id, { sku, destination_fc: fc, qty: Number(qty) });
      setSku(""); setFc(""); setQty("");
      onDone();
    } catch (er) { setErr(er.message); }
    finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} style={{
      background: "#eff6ff", border: "1px solid #bfdbfe", padding: 12, borderRadius: 6,
      marginBottom: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap",
    }}>
      <input placeholder="SKU (e.g. FBA79984)" value={sku} onChange={(e) => setSku(e.target.value)}
             required style={inp} />
      <input placeholder="FC (e.g. DEL4)" value={fc} onChange={(e) => setFc(e.target.value)}
             required style={inp} />
      <input placeholder="Qty" type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)}
             required style={{ ...inp, width: 90 }} />
      <button type="submit" disabled={busy} style={btnStyle("#3b82f6")}>Add</button>
      {err && <span style={{ color: "#ef4444", fontSize: 12 }}>{err}</span>}
    </form>
  );
}

// ────────────────────────────── Calc breakdown popup
// Reconstructs the Replenishment calc from the snapshot fields plan_lines
// captured at propose time. Lets the approver audit: what velocity did
// Naresh use, what cover_weeks, what stock did the calc net against,
// and how does his Working (qty) compare to the calc's suggestion
// (original_send_qty)?
function CalcBreakdownModal({ line, coverWeeks, accountLabel, onClose }) {
  const vel   = Number(line.weekly_velocity ?? 0);
  const cover = Number(coverWeeks ?? 0);
  const required = Math.round(vel * cover);
  // Distinguish "was null at propose time" (renders "—") from actual 0.
  const realAmRaw = line.real_am_inv;
  const realAm    = realAmRaw == null ? 0 : Number(realAmRaw);
  const motherRaw = line.mother_inv;
  const mother    = motherRaw == null ? 0 : Number(motherRaw);
  const cbSoh  = line.cb_soh == null ? null : Number(line.cb_soh);
  const shortage = Math.max(0, required - realAm);
  const suggestedPre = Math.min(shortage, mother);  // pre-buffer/carton
  const original  = Number(line.original_send_qty ?? 0);
  const working   = Number(line.qty ?? 0);
  const delta = working - original;
  const isAA = String(accountLabel || "").toUpperCase().includes("AUDIO");

  // ESC key closes the modal — a11y polish.
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "white", borderRadius: 8, padding: 20, minWidth: 420,
          maxWidth: 560, boxShadow: "0 10px 40px rgba(0,0,0,0.3)",
          fontFamily: "Poppins, sans-serif",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 16 }}>
            Calc Breakdown — <span style={{ color: "#6366f1" }}>{line.sku}</span>
          </h3>
          <button onClick={onClose} style={{
            border: "none", background: "transparent", cursor: "pointer",
            fontSize: 18, color: "#6b7280", lineHeight: 1,
          }}>✕</button>
        </div>
        <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 12 }}>
          {line.model || "—"} · {line.destination_fc} · reconstructed from snapshot fields captured at propose time
        </div>

        <CalcSection title="Demand">
          <CalcRow label="Weekly velocity"    value={vel.toFixed(1)}  unit="u/wk" />
          <CalcRow label="Cover weeks"        value={cover || "—"}    unit="wks" />
          <CalcRow label="Required" bold      value={required}        unit="u"
                   note={`= ${vel.toFixed(1)} × ${cover || "?"}`} />
        </CalcSection>

        <CalcSection title="Available">
          <CalcRow label="Real AM Inv"        value={realAmRaw == null ? "—" : realAm} unit="u"
                   note="Amazon FBA + Inbound (ledger-adjusted)" />
          <CalcRow label="Mother WH (AMPM)"   value={motherRaw == null ? "—" : mother} unit="u" />
          {isAA && (
            <CalcRow label="CB SOH (vendor)"  value={cbSoh ?? "—"}    unit="u"
                     note="Cambium 1P vendor warehouse — reference only, not netted" />
          )}
        </CalcSection>

        <CalcSection title="Calc engine">
          <CalcRow label="Amazon shortage"    value={shortage}        unit="u"
                   note={`max(0, required − Real AM Inv) = max(0, ${required} − ${realAm})`} />
          <CalcRow label="Pre-adjust suggested" bold value={suggestedPre} unit="u"
                   note={`min(shortage, Mother) = min(${shortage}, ${mother})`}
                   color="#6366f1" />
          <CalcRow label="Original (as stored)" value={original} unit="u"
                   note="Backend applies AMPM buffer gate (1–10 → 0) + carton rounding on top of the min above" />
        </CalcSection>

        <CalcSection title="Naresh's override">
          <CalcRow label="Working (Naresh)" bold value={working}      unit="u"
                   color="#10b981" />
          <CalcRow label="Δ vs original" bold value={(delta > 0 ? "+" : "") + delta} unit="u"
                   color={delta === 0 ? "#6b7280" : delta > 0 ? "#10b981" : "#ef4444"} />
          {line.notes && (
            <div style={{
              marginTop: 8, padding: 8, background: "#fef3c7",
              border: "1px solid #fde68a", borderRadius: 4, fontSize: 12,
            }}>
              <b style={{ color: "#92400e" }}>Naresh's remark: </b>
              <span style={{ color: "#78350f", whiteSpace: "pre-wrap" }}>{line.notes}</span>
            </div>
          )}
          {line.approver_note && (
            <div style={{
              marginTop: 8, padding: 8, background: "#faf5ff",
              border: "1px solid #e9d5ff", borderRadius: 4, fontSize: 12,
            }}>
              <b style={{ color: "#7c3aed" }}>Approver's note: </b>
              <span style={{ color: "#5b21b6", whiteSpace: "pre-wrap" }}>{line.approver_note}</span>
            </div>
          )}
        </CalcSection>

        <div style={{ marginTop: 12, fontSize: 10, color: "#9ca3af", lineHeight: 1.5 }}>
          Snapshot captured when the plan was proposed. Live source-tab
          numbers may differ (SP-API pull refreshes, AMPM edits).
        </div>
      </div>
    </div>
  );
}

const CalcSection = ({ title, children }) => (
  <div style={{ marginBottom: 14 }}>
    <div style={{ fontSize: 10, color: "#6b7280", fontWeight: 600, textTransform: "uppercase", marginBottom: 6, letterSpacing: 0.5 }}>
      {title}
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {children}
    </div>
  </div>
);

const CalcRow = ({ label, value, unit, note, bold, color }) => (
  <div style={{
    display: "flex", justifyContent: "space-between", alignItems: "baseline",
    padding: "3px 0", borderBottom: "1px dashed #f3f4f6",
  }}>
    <div style={{ fontSize: 12, color: "#374151", fontWeight: bold ? 600 : 400 }}>
      {label}
      {note && <div style={{ fontSize: 10, color: "#9ca3af", fontWeight: 400 }}>{note}</div>}
    </div>
    <div style={{
      fontSize: 13, fontWeight: bold ? 700 : 500, color: color || "inherit",
      textAlign: "right", whiteSpace: "nowrap",
    }}>
      {value} <span style={{ fontSize: 10, color: "#9ca3af" }}>{unit}</span>
    </div>
  </div>
);

// ────────────────────────────── small style helpers
// Bucket by (fc, hazmat, ixd) to preview how many shipments OrderPilot will create.
// Amazon FBA rejects mixed hazmat/non-hazmat AND mixed IXD/non-IXD shipments,
// so each unique triple = one distinct shipment. Match push_plan's filter:
// exclude soft-deleted, zero-qty, and exclude_from_push rows.
function _shipmentBuckets(lines) {
  const pushable = (lines || []).filter(
    (l) => !l.is_deleted && Number(l.qty) > 0 && !l.exclude_from_push
  );
  if (!pushable.length) return 0;
  const keys = new Set(pushable.map((l) =>
    `${l.destination_fc}|${l.hazmat ? "H" : "N"}|${l.ixd_flag || "?"}`
  ));
  return keys.size;
}

function _skippedLineCount(lines) {
  return (lines || []).filter((l) => !l.is_deleted && l.exclude_from_push).length;
}

const Stat = ({ label, value, color }) => (
  <div>
    <div style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase" }}>{label}</div>
    <div style={{ fontSize: 18, fontWeight: 600, color: color || "inherit" }}>{value ?? "—"}</div>
  </div>
);
const Th = ({ children, align }) => (
  <th style={{ padding: "8px 10px", textAlign: align || "left", fontWeight: 600, fontSize: 12, color: "#6b7280", borderBottom: "1px solid #e5e7eb" }}>{children}</th>
);
const Td = ({ children, align }) => (
  <td style={{ padding: "6px 10px", textAlign: align || "left" }}>{children}</td>
);
const Badge = ({ children, color = "#6b7280" }) => (
  <span style={{ background: color, color: "white", padding: "1px 6px", borderRadius: 4, fontSize: 10 }}>{children}</span>
);
const btnStyle = (bg) => ({
  padding: "6px 12px", background: bg, color: "white", border: "none", borderRadius: 4,
  cursor: "pointer", fontSize: 12, fontWeight: 600,
});
const btnSmall = (bg) => ({
  padding: "2px 6px", background: bg, color: "white", border: "none", borderRadius: 3,
  cursor: "pointer", fontSize: 10,
});
const inp = { padding: 6, border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13, minWidth: 160 };
