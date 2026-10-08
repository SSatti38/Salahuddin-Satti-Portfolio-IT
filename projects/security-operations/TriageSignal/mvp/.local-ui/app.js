"use strict";
const $ = (id) => document.getElementById(id);
const statusEl = $("status");
let currentState = { records: [], audit: [] };
let csrfToken = "";
let selectedId = "";
let busy = false;

function node(tag, cls, value) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (value !== undefined && value !== null) el.textContent = String(value);
  return el;
}
function status(message, kind = "") {
  statusEl.textContent = message;
  statusEl.dataset.kind = kind;
}
function localDate(value) {
  if (!value) return "Not supplied";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(date) + " UTC";
}
function badge(text, extra = "") {
  return node("span", `badge ${extra || `badge-${text}`}`, text.replaceAll("_", " "));
}
function field(label, value) {
  const item = node("div", "detail-item");
  item.append(node("small", "", label), node("span", "", value || "Not supplied"));
  return item;
}
function metric(label, value, hint) {
  const box = node("div", "metric");
  box.append(node("span", "metric-label", label), node("strong", "metric-value", value), node("span", "metric-hint", hint));
  return box;
}
function renderMetrics(records) {
  const counts = (s) => records.filter((row) => row.status === s).length;
  $("metrics").replaceChildren(
    metric("Total alerts", records.length, "Imported local records"),
    metric("New", counts("new"), "Awaiting analyst review"),
    metric("In review", counts("in_review"), "Human workflow state"),
    metric("Follow-up", counts("follow_up"), "Human-owned note only")
  );
}
function renderAudit(items) {
  const root = $("audit");
  root.replaceChildren();
  if (!items.length) {
    root.append(node("p", "subtle", "No local audit events yet."));
    return;
  }
  for (const entry of items.slice(0, 18)) {
    const row = node("div", "audit-entry");
    row.append(node("strong", "", entry.action.replaceAll("_", " ")), node("div", "", `Target: ${entry.target_id}`), node("time", "", localDate(entry.created_at)));
    root.append(row);
  }
}
function renderRecords(records) {
  const root = $("records");
  root.replaceChildren();
  $("record-count").textContent = `${records.length} ${records.length === 1 ? "record" : "records"}`;
  if (!records.length) {
    const empty = node("div", "empty");
    empty.append(node("span", "empty-icon", "◌"), node("strong", "", "No alerts in this workspace"), node("span", "", "Load the fictional sample or import a synthetic JSON/CSV file. The app remains empty until you choose.") );
    root.append(empty);
    return;
  }
  if (!records.some((r) => r.id === selectedId)) selectedId = records[0].id;
  for (const record of records) {
    const button = node("button", "record-card");
    button.type = "button";
    button.setAttribute("aria-pressed", String(record.id === selectedId));
    const top = node("div", "record-top");
    top.append(node("span", "record-title", record.id), badge(record.severity, `badge-${record.severity === "critical" || record.severity === "high" ? "critical" : "review"}`));
    button.append(top, node("div", "record-meta", `${record.source} · ${localDate(record.occurred_at)}`), node("p", "record-summary", record.summary), badge(record.status));
    button.addEventListener("click", () => { selectedId = record.id; renderRecords(currentState.records); renderDetail(); });
    root.append(button);
  }
  renderDetail();
}
function renderDetail() {
  const root = $("detail");
  const record = currentState.records.find((row) => row.id === selectedId);
  root.replaceChildren();
  if (!record) {
    const empty = node("div", "empty");
    empty.append(node("strong", "", "No alert selected"), node("span", "", "Select an alert to inspect its source references and record a review."));
    root.append(empty);
    return;
  }
  root.append(node("h3", "", record.id), node("p", "", record.summary));
  const grid = node("div", "detail-grid");
  grid.append(field("Source", record.source), field("Severity", record.severity), field("Observed", localDate(record.occurred_at)), field("Updated locally", localDate(record.updated_at)));
  root.append(grid, node("h3", "", "Evidence references"));
  const list = node("ul", "evidence-list");
  if (!record.evidence.length) list.append(node("li", "", "No evidence references were supplied. Treat the alert as incomplete; do not infer supporting facts."));
  for (const evidence of record.evidence) {
    const item = node("li", "");
    item.append(node("strong", "", `${evidence.id} · ${evidence.source}`), node("div", "", `${localDate(evidence.observed_at)} — ${evidence.summary}`));
    list.append(item);
  }
  root.append(list);
  const citationField = node("fieldset", "citation-field");
  citationField.append(node("legend", "", "Cite sources for your review"));
  const citationOptions = node("div", "citation-options");
  const sourceCitation = node("label", "citation-option");
  const sourceCheckbox = node("input", ""); sourceCheckbox.type = "checkbox"; sourceCheckbox.value = `alert:${record.id}`; sourceCheckbox.checked = record.citations.includes(sourceCheckbox.value);
  sourceCitation.append(sourceCheckbox, node("span", "", `Alert source record · ${record.source} · ${record.id}`));
  citationOptions.append(sourceCitation);
  for (const evidence of record.evidence) {
    const option = node("label", "citation-option");
    const checkbox = node("input", ""); checkbox.type = "checkbox"; checkbox.value = evidence.id; checkbox.checked = record.citations.includes(evidence.id);
    option.append(checkbox, node("span", "", `Evidence ${evidence.id} · ${evidence.source}`));
    citationOptions.append(option);
  }
  citationField.append(citationOptions, node("span", "field-hint", "Required when marking Reviewed or Follow-up. Only this alert's source record and evidence IDs are accepted."));
  const form = node("form", "inline-form");
  const statusField = node("div", "field");
  const statusLabel = node("label", "", "Analyst workflow status"); statusLabel.htmlFor = "alert-status";
  const statusSelect = node("select", "");
  statusSelect.id = "alert-status"; statusSelect.setAttribute("aria-label", "Analyst workflow status");
  for (const [value, label] of [["new", "New"], ["in_review", "In review"], ["reviewed", "Reviewed by human"], ["follow_up", "Follow-up queued locally"]]) {
    const option = node("option", "", label); option.value = value; statusSelect.append(option);
  }
  statusSelect.value = record.status;
  statusField.append(statusLabel, statusSelect);
  const noteField = node("div", "field");
  const noteLabel = node("label", "", "Analyst note"); noteLabel.htmlFor = "analyst-note";
  const textarea = node("textarea", "");
  textarea.id = "analyst-note"; textarea.maxLength = 4000;
  textarea.value = record.analyst_note;
  textarea.placeholder = "Record a source-cited observation or what remains unknown. This is a human note, not an automated conclusion.";
  noteField.append(noteLabel, textarea, node("span", "field-hint", "Max 4,000 characters. Avoid production/confidential content."));
  const save = node("button", "btn btn-primary"); save.type = "submit"; save.textContent = "Save review note & status";
  form.append(statusField, noteField, citationField, save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const citations = Array.from(citationField.querySelectorAll('input[type="checkbox"]:checked'), (input) => input.value);
    await sendAction("save_alert", { id: record.id, status: statusSelect.value, analyst_note: textarea.value, citations });
  });
  root.append(node("div", "divider"), form);
}
function render() {
  const records = currentState.records || [];
  renderMetrics(records);
  renderAudit(currentState.audit || []);
  renderRecords(records);
}
async function refresh() {
  try {
    const response = await fetch("/api/state", { cache: "no-store", headers: { Accept: "application/json" } });
    const body = await response.json();
    if (!response.ok || !body.ok) throw new Error(body.error || "Local workspace did not respond.");
    currentState = body.state;
    csrfToken = body.state.csrf_token;
    render();
    status("Local workspace ready · no external connections", "success");
  } catch (_) {
    status("Could not reach the local app. Check the terminal and reload this page.", "error");
    $("records").replaceChildren(node("div", "empty", "The local service is unavailable. Start it with ./run.sh, then reload."));
  }
}
async function sendAction(action, payload = {}) {
  if (busy) return;
  busy = true;
  document.body.classList.add("loading");
  status("Validating and saving locally…");
  try {
    const response = await fetch("/api/action", {
      method: "POST", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Local-Token": csrfToken, "Sec-Fetch-Site": "same-origin" },
      body: JSON.stringify({ action, payload })
    });
    const body = await response.json();
    if (!response.ok || !body.ok) throw new Error(body.error || "Local action failed.");
    currentState = body.state;
    csrfToken = body.state.csrf_token;
    status(body.result.message || "Saved locally.", "success");
    render();
  } catch (error) {
    status(error.message || "Local action failed.", "error");
  } finally {
    busy = false;
    document.body.classList.remove("loading");
  }
}
$("load-demo").addEventListener("click", () => sendAction("load_demo"));
$("reset-demo").addEventListener("click", () => {
  if (window.confirm("Replace all local alerts, analyst notes, and prior audit history with the fictional sample? This cannot be undone.")) sendAction("reset_demo");
});
$("import-file-button").addEventListener("click", async () => {
  const input = $("import-file");
  const file = input.files && input.files[0];
  if (!file) { status("Choose a synthetic JSON or CSV file first.", "error"); return; }
  if (file.size > 512 * 1024) { status("File exceeds the 512 KiB limit.", "error"); return; }
  const format = file.name.toLowerCase().endsWith(".csv") ? "csv" : file.name.toLowerCase().endsWith(".json") ? "json" : "";
  if (!format) { status("Only .json and .csv files are accepted.", "error"); return; }
  try { const content = await file.text(); await sendAction("import", { format, content }); input.value = ""; }
  catch (_) { status("Could not read the selected file.", "error"); }
});
refresh();
