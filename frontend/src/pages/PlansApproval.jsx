import { useEffect, useMemo, useState } from "react";
import {
  listPlans, getPlan, editLine, addLine, deleteLine, approvePlan, pushPlan,
  sendToApprover,
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
  // Editor defaults to seeing their own drafts; approver defaults to proposed.
  const [statusFilter, setStatusFilter] = useState(isEditor && !isApprover ? "draft" : "proposed");

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
            {batches.map((b) => (
              <div
                key={b.batch_id}
                onClick={() => setSelectedId(b.batch_id)}
                style={{
                  padding: 10, borderBottom: "1px solid #f3f4f6", cursor: "pointer",
                  background: selectedId === b.batch_id ? "#eff6ff" : "white",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong style={{ fontSize: 13 }}>{b.account}</strong>
                  <span style={{
                    padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600,
                    background: STATUS_COLORS[b.status] || "#9ca3af", color: "white",
                  }}>{b.status}</span>
                </div>
                <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
                  {b.proposed_by} · {fmt(b.proposed_at)}
                </div>
                <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 2 }}>{b.batch_id}</div>
              </div>
            ))}
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

  const [showAdd, setShowAdd] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

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
        gridTemplateColumns: "repeat(4, 1fr)", gap: 12,
      }}>
        <Stat label="Total Units" value={s.total_units} />
        <Stat label="Unique SKUs" value={s.unique_skus} />
        <Stat label="Unique FCs" value={s.unique_fcs} />
        <Stat label="Δ vs original"
              value={(s.delta_units > 0 ? "+" : "") + s.delta_units}
              color={s.delta_units === 0 ? "#6b7280" : s.delta_units > 0 ? "#10b981" : "#ef4444"} />
      </div>

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
          <button
            onClick={() => {
              if (!confirm(`Approve batch ${batch.batch_id}? This freezes the plan.`)) return;
              act(() => approvePlan(batch.batch_id));
            }}
            disabled={busy}
            style={btnStyle("#10b981")}
          >
            ✓ Approve & Freeze
          </button>
        )}
        {canPush && (
          <button
            onClick={() => act(() => pushPlan(batch.batch_id).then((r) => alert(r.message || "Pushed")))}
            disabled={busy}
            style={btnStyle("#f59e0b")}
            title="Push to OrderPilot — currently a stub"
          >
            → Push to OrderPilot (stub)
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
              <Th align="right">Qty</Th><Th align="right">Original</Th>
              <Th>Added By</Th><Th>Edited By</Th>
              {canEdit && <Th>Actions</Th>}
            </tr>
          </thead>
          <tbody>
            {(batch.lines || []).map((l) => (
              <LineRow key={l.id} line={l} canEdit={canEdit} batchId={batch.batch_id} onReload={onReload} />
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

function LineRow({ line, canEdit, batchId, onReload }) {
  const [qty, setQty] = useState(String(line.qty));
  const [busy, setBusy] = useState(false);
  const dirty = String(line.qty) !== qty;
  const deleted = !!line.is_deleted;

  async function save() {
    setBusy(true);
    try {
      await editLine(batchId, line.id, { qty: Number(qty), row_version: line.row_version });
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
      background: deleted ? "#fef2f2" : "white",
      color: deleted ? "#9ca3af" : "inherit",
      textDecoration: deleted ? "line-through" : "none",
    }}>
      <Td>{line.sku}</Td>
      <Td>{line.model || "—"}</Td>
      <Td>{line.asin || "—"}</Td>
      <Td>{line.destination_fc}</Td>
      <Td align="right">
        {canEdit && !deleted ? (
          <input
            type="number" value={qty} onChange={(e) => setQty(e.target.value)} min={0}
            style={{ width: 70, padding: 4, textAlign: "right", border: dirty ? "1px solid #f59e0b" : "1px solid #d1d5db" }}
          />
        ) : (
          <span>{line.qty}</span>
        )}
      </Td>
      <Td align="right"><span style={{ color: "#9ca3af" }}>{line.original_send_qty}</span></Td>
      <Td><Badge>{line.added_by}</Badge></Td>
      <Td>{line.edited_by ? <Badge color="#f59e0b">{line.edited_by}</Badge> : "—"}</Td>
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

// ────────────────────────────── small style helpers
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
