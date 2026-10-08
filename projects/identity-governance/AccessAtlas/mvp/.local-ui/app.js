"use strict";
const $ = (id) => document.getElementById(id);
const statusEl = $("status");
let currentState = { records: [], audit: [] };
let csrfToken = "";
let selectedId = "";
let busy = false;
function node(tag, cls, value) { const el = document.createElement(tag); if (cls) el.className = cls; if (value !== undefined && value !== null) el.textContent = String(value); return el; }
function status(message, kind = "") { statusEl.textContent = message; statusEl.dataset.kind = kind; }
function localDate(value) { if (!value) return "Not supplied"; const d = new Date(value); return Number.isNaN(d.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(d) + " UTC"; }
function badge(text, cls) { return node("span", `badge ${cls || `badge-${text}`}`, text.replaceAll("_", " ")); }
function metric(label, value, hint) { const box = node("div", "metric"); box.append(node("span", "metric-label", label), node("strong", "metric-value", value), node("span", "metric-hint", hint)); return box; }
function detailField(label, value) { const item = node("div", "detail-item"); item.append(node("small", "", label), node("span", "", value || "Not supplied")); return item; }
function renderMetrics(records) {
  const reviewed = records.filter((row) => row.latest_outcome).length;
  const follow = records.filter((row) => row.latest_outcome === "follow_up").length;
  const pending = records.length - reviewed;
  $("metrics").replaceChildren(metric("Identities", records.length, "Synthetic snapshot rows"), metric("Awaiting review", pending, "No human decision recorded"), metric("Reviewed", reviewed, "Retain or follow-up"), metric("Follow-up", follow, "Local note only; no account change"));
}
function renderAudit(items) {
  const root = $("audit"); root.replaceChildren();
  if (!items.length) { root.append(node("p", "subtle", "No decision audit entries yet.")); return; }
  for (const entry of items.slice(0, 18)) { const row = node("div", "audit-entry"); row.append(node("strong", "", entry.action.replaceAll("_", " ")), node("div", "", `Target: ${entry.target_id}`), node("time", "", localDate(entry.created_at))); root.append(row); }
}
function renderRecords(records) {
  const root = $("records"); root.replaceChildren();
  $("record-count").textContent = `${records.length} ${records.length === 1 ? "identity" : "identities"}`;
  if (!records.length) { const empty = node("div", "empty"); empty.append(node("span", "empty-icon", "◌"), node("strong", "", "No identities in this workspace"), node("span", "", "Load the fictional sample or import a synthetic JSON/CSV snapshot. Nothing is imported automatically.")); root.append(empty); return; }
  if (!records.some((r) => r.id === selectedId)) selectedId = records[0].id;
  for (const record of records) {
    const button = node("button", "record-card"); button.type = "button"; button.setAttribute("aria-pressed", String(record.id === selectedId));
    const top = node("div", "record-top"); top.append(node("span", "record-title", record.display_name), record.latest_outcome ? badge(record.latest_outcome, record.latest_outcome === "retain" ? "badge-retain" : "badge-follow_up") : badge("review", "badge-review"));
    button.append(top, node("div", "record-meta", `${record.id} · ${record.entitlement}`), node("p", "record-summary", record.evidence), node("div", "record-meta", `Snapshot: ${localDate(record.snapshot_at)}`));
    button.addEventListener("click", () => { selectedId = record.id; renderRecords(currentState.records); renderDetail(); }); root.append(button);
  }
  renderDetail();
}
function renderDetail() {
  const root = $("detail"); root.replaceChildren();
  const record = currentState.records.find((r) => r.id === selectedId);
  if (!record) { const empty = node("div", "empty"); empty.append(node("strong", "", "No identity selected"), node("span", "", "Select a row to inspect evidence and record a human decision.")); root.append(empty); return; }
  root.append(node("h3", "", record.display_name), node("p", "", "Review signal is contextual only. Verify the source snapshot and business need; the app does not infer misuse or modify access."));
  const grid = node("div", "detail-grid"); grid.append(detailField("Identity reference", record.id), detailField("Account state (source-reported)", record.account_state), detailField("Entitlement", record.entitlement), detailField("Source", record.source), detailField("Last sign-in", localDate(record.last_sign_in)), detailField("Snapshot captured", localDate(record.snapshot_at))); root.append(grid);
  const evidence = node("div", "map-evidence"); evidence.append(node("strong", "", "Snapshot evidence · "), node("span", "", record.evidence)); root.append(evidence);
  root.append(node("div", "divider"), node("h3", "", "Record a reviewer decision"));
  const form = node("form", "inline-form");
  const rows = node("div", "field-row");
  const outcomeWrap = node("div", "field"); const outcomeLabel = node("label", "", "Outcome"); outcomeLabel.htmlFor = "decision-outcome"; outcomeWrap.append(outcomeLabel);
  const outcome = node("select", ""); outcome.id = "decision-outcome"; outcome.setAttribute("aria-label", "Decision outcome"); outcome.required = true;
  const blank = node("option", "", "Choose a decision"); blank.value = ""; blank.disabled = true; outcome.append(blank);
  for (const [value, label] of [["retain", "Retain / reviewed"], ["follow_up", "Follow-up queued locally"]]) { const option = node("option", "", label); option.value = value; outcome.append(option); }
  outcome.value = record.latest_outcome || ""; outcomeWrap.append(outcome);
  const reviewerWrap = node("div", "field"); const reviewerLabel = node("label", "", "Reviewer label"); reviewerLabel.htmlFor = "reviewer-label"; reviewerWrap.append(reviewerLabel); const reviewer = node("input", ""); reviewer.id = "reviewer-label"; reviewer.maxLength = 120; reviewer.value = record.latest_reviewer || "Local reviewer"; reviewer.required = true; reviewer.setAttribute("aria-label", "Reviewer label"); reviewerWrap.append(reviewer); rows.append(outcomeWrap, reviewerWrap);
  const rationaleWrap = node("div", "field"); const rationaleLabel = node("label", "", "Rationale"); rationaleLabel.htmlFor = "review-rationale"; rationaleWrap.append(rationaleLabel); const rationale = node("textarea", ""); rationale.id = "review-rationale"; rationale.maxLength = 1500; rationale.required = true; rationale.value = ""; rationale.placeholder = "Explain the decision using the snapshot evidence and known business context. This rationale is saved in local decision history."; rationale.setAttribute("aria-label", "Decision rationale"); rationaleWrap.append(rationale, node("span", "field-hint", "Required · max 1,500 characters · fictional content only."));
  const submit = node("button", "btn btn-primary"); submit.type = "submit"; submit.textContent = "Record human decision"; form.append(rows, rationaleWrap, submit);
  form.addEventListener("submit", async (event) => { event.preventDefault(); await sendAction("review", { id: record.id, outcome: outcome.value, reviewer: reviewer.value, rationale: rationale.value }); }); root.append(form);
  root.append(node("div", "divider"), node("h3", "", "Decision history"));
  const history = node("ul", "evidence-list");
  if (!record.decisions.length) history.append(node("li", "", "No decision recorded yet. A reviewer must choose an outcome and enter a rationale."));
  for (const decision of record.decisions) { const li = node("li", ""); li.append(node("strong", "", `${decision.outcome.replaceAll("_", " ")} · ${decision.reviewer}`), node("div", "", `${localDate(decision.created_at)} — ${decision.rationale}`)); history.append(li); }
  root.append(history);
}
function render() { renderMetrics(currentState.records || []); renderAudit(currentState.audit || []); renderRecords(currentState.records || []); }
async function refresh() {
  try { const response = await fetch("/api/state", { cache: "no-store", headers: { Accept: "application/json" } }); const body = await response.json(); if (!response.ok || !body.ok) throw new Error(); currentState = body.state; csrfToken = body.state.csrf_token; render(); status("Local workspace ready · no provider connection", "success"); }
  catch (_) { status("Could not reach the local app. Check the terminal and reload this page.", "error"); $("records").replaceChildren(node("div", "empty", "Local service unavailable. Start it with ./run.sh, then reload.")); }
}
async function sendAction(action, payload = {}) {
  if (busy) return; busy = true; document.body.classList.add("loading"); status("Validating and saving locally…");
  try { const response = await fetch("/api/action", { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json", "X-Local-Token": csrfToken }, body: JSON.stringify({ action, payload }) }); const body = await response.json(); if (!response.ok || !body.ok) throw new Error(body.error || "Local action failed."); currentState = body.state; csrfToken = body.state.csrf_token; status(body.result.message || "Saved locally.", "success"); render(); }
  catch (error) { status(error.message || "Local action failed.", "error"); }
  finally { busy = false; document.body.classList.remove("loading"); }
}
$("load-demo").addEventListener("click", () => sendAction("load_demo"));
$("reset-demo").addEventListener("click", () => { if (window.confirm("Replace local identity snapshots, review decisions, and prior audit history with the fictional sample? This cannot be undone.")) sendAction("reset_demo"); });
$("import-file-button").addEventListener("click", async () => {
  const input = $("import-file"), file = input.files && input.files[0];
  if (!file) { status("Choose a synthetic JSON or CSV file first.", "error"); return; }
  if (file.size > 512 * 1024) { status("File exceeds the 512 KiB limit.", "error"); return; }
  const format = file.name.toLowerCase().endsWith(".csv") ? "csv" : file.name.toLowerCase().endsWith(".json") ? "json" : "";
  if (!format) { status("Only .json and .csv files are accepted.", "error"); return; }
  try { await sendAction("import", { format, content: await file.text() }); input.value = ""; } catch (_) { status("Could not read the selected file.", "error"); }
});
refresh();
