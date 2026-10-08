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
function badge(value) { return node("span", `badge badge-${value}`, value.replaceAll("_", " ")); }
function detailField(label, value) { const item = node("div", "detail-item"); item.append(node("small", "", label), node("span", "", value === 0 ? "0" : (value || "Not supplied"))); return item; }
function metric(label, value, hint) { const box = node("div", "metric"); box.append(node("span", "metric-label", label), node("strong", "metric-value", value), node("span", "metric-hint", hint)); return box; }
function renderMetrics(records) {
  const count = (state) => records.filter((r) => r.health === state).length;
  $("metrics").replaceChildren(metric("Sources", records.length, "Fictional/manual metadata"), metric("Healthy", count("healthy"), "Within stated cadence and thresholds"), metric("Degraded", count("degraded"), "Parser or backlog evidence"), metric("Stale / failed", count("stale") + count("failed") + count("unknown"), "Check source values; no response action"));
}
function renderAudit(items) {
  const root = $("audit"); root.replaceChildren();
  if (!items.length) { root.append(node("p", "subtle", "No metadata audit events yet.")); return; }
  for (const entry of items.slice(0, 18)) { const row = node("div", "audit-entry"); row.append(node("strong", "", entry.action.replaceAll("_", " ")), node("div", "", `Target: ${entry.target_id}`), node("time", "", localDate(entry.created_at))); root.append(row); }
}
function renderRecords(records) {
  const root = $("records"); root.replaceChildren(); $("record-count").textContent = `${records.length} ${records.length === 1 ? "source" : "sources"}`;
  if (!records.length) { const empty = node("div", "empty"); empty.append(node("span", "empty-icon", "◌"), node("strong", "", "No source metadata yet"), node("span", "", "Use the manual form or load the fictional sample. No collector or source is contacted.")); root.append(empty); return; }
  if (!records.some((r) => r.id === selectedId)) selectedId = records[0].id;
  for (const record of records) {
    const button = node("button", "record-card"); button.type = "button"; button.setAttribute("aria-pressed", String(record.id === selectedId));
    const top = node("div", "record-top"); top.append(node("span", "record-title", record.name), badge(record.health));
    button.append(top, node("div", "record-meta", `${record.id} · ${record.environment} · owner ${record.owner}`), node("p", "record-summary", `Freshness ${record.age_minutes === null ? "unknown" : `${record.age_minutes} min`} · parser ${record.parser_status} · backlog ${record.backlog_count}/${record.backlog_threshold}`), node("div", "record-meta", `Mapping ${record.coverage_ref}`));
    button.addEventListener("click", () => { selectedId = record.id; renderRecords(currentState.records); renderDetail(); }); root.append(button);
  }
  renderDetail();
}
function renderDetail() {
  const root = $("detail"); root.replaceChildren(); const record = currentState.records.find((r) => r.id === selectedId);
  if (!record) { const empty = node("div", "empty"); empty.append(node("strong", "", "No source selected"), node("span", "", "Select a source to inspect freshness, parser, backlog, and mapping evidence.")); root.append(empty); return; }
  root.append(node("h3", "", record.name), node("p", "", "Derived health describes only the supplied local metadata and thresholds. It is not a detection-readiness or security-effectiveness finding."));
  const grid = node("div", "detail-grid");
  grid.append(detailField("Health state", record.health), detailField("Source reference", record.id), detailField("Environment · owner", `${record.environment} · ${record.owner}`), detailField("Expected cadence", `${record.expected_minutes} minutes`), detailField("Last seen", localDate(record.last_seen_at)), detailField("Age at display", record.age_minutes === null ? "Unknown" : `${record.age_minutes} minutes`), detailField("Parser state", record.parser_status), detailField("Accepted / rejected", `${record.accepted_count} / ${record.rejected_count}`), detailField("Backlog / threshold", `${record.backlog_count} / ${record.backlog_threshold}`), detailField("Heartbeat", localDate(record.heartbeat_at)), detailField("Last local edit", localDate(record.updated_at)));
  root.append(grid, node("h3", "", "Why this state?"));
  const list = node("ul", "evidence-list"); for (const reason of record.reasons) list.append(node("li", "", reason)); root.append(list);
  const mapping = node("div", "map-evidence"); mapping.append(node("strong", "", `Mapping reference ${record.coverage_ref} · `), node("span", "", record.coverage_notes), node("div", "", "Threshold evidence is manually supplied and not validated against any external catalog.")); root.append(mapping);
}
function render() { renderMetrics(currentState.records || []); renderAudit(currentState.audit || []); renderRecords(currentState.records || []); }
async function refresh() {
  try { const response = await fetch("/api/state", { cache: "no-store", headers: { Accept: "application/json" } }); const body = await response.json(); if (!response.ok || !body.ok) throw new Error(); currentState = body.state; csrfToken = body.state.csrf_token; render(); status("Local workspace ready · no collector or external connection", "success"); }
  catch (_) { status("Could not reach the local app. Check the terminal and reload this page.", "error"); $("records").replaceChildren(node("div", "empty", "Local service unavailable. Start it with ./run.sh, then reload.")); }
}
async function sendAction(action, payload = {}) {
  if (busy) return; busy = true; document.body.classList.add("loading"); status("Validating and saving locally…");
  try { const response = await fetch("/api/action", { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json", "X-Local-Token": csrfToken }, body: JSON.stringify({ action, payload }) }); const body = await response.json(); if (!response.ok || !body.ok) throw new Error(body.error || "Local action failed."); currentState = body.state; csrfToken = body.state.csrf_token; status(body.result.message || "Saved locally.", "success"); render(); }
  catch (error) { status(error.message || "Local action failed.", "error"); }
  finally { busy = false; document.body.classList.remove("loading"); }
}
$("load-demo").addEventListener("click", () => sendAction("load_demo"));
$("reset-demo").addEventListener("click", () => { if (window.confirm("Replace local health metadata and prior audit history with the fictional sample? This cannot be undone.")) sendAction("reset_demo"); });
$("source-form").addEventListener("submit", async (event) => { event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget).entries()); await sendAction("save_source", payload); });
$("import-file-button").addEventListener("click", async () => {
  const input = $("import-file"), file = input.files && input.files[0];
  if (!file) { status("Choose a synthetic JSON or CSV file first.", "error"); return; }
  if (file.size > 512 * 1024) { status("File exceeds the 512 KiB limit.", "error"); return; }
  const format = file.name.toLowerCase().endsWith(".csv") ? "csv" : file.name.toLowerCase().endsWith(".json") ? "json" : "";
  if (!format) { status("Only .json and .csv files are accepted.", "error"); return; }
  try { await sendAction("import", { format, content: await file.text() }); input.value = ""; } catch (_) { status("Could not read the selected file.", "error"); }
});
refresh();
