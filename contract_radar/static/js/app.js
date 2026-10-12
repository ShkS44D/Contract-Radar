"use strict";
const input = document.querySelector("#file-input");
const area = document.querySelector("#drop-area");
const label = document.querySelector("#file-label");
if (input && area && label) {
  const selected = () => {
    label.textContent = input.files.length ? `Selected: ${input.files[0].name}` : "Drag and drop, or browse your files.";
  };
  input.addEventListener("change", selected);
  ["dragenter", "dragover"].forEach(event => area.addEventListener(event, e => {
    e.preventDefault();
    area.classList.add("drag-over");
  }));
  ["dragleave", "drop"].forEach(event => area.addEventListener(event, e => {
    e.preventDefault();
    area.classList.remove("drag-over");
  }));
  area.addEventListener("drop", e => {
    if (e.dataTransfer.files.length !== 1) {
      label.textContent = "Choose one .sol file or one ZIP project.";
      return;
    }
    input.files = e.dataTransfer.files;
    selected();
  });
}
const filters = document.querySelectorAll(".filter");
const search = document.querySelector("#finding-search");
const findings = document.querySelectorAll(".finding[data-severity]");
let severity = "all";

function updateFindings() {
  let shown = 0;
  const query = search ? search.value.toLowerCase() : "";
  findings.forEach(finding => {
    const visible = (severity === "all" || finding.dataset.severity === severity) && finding.textContent.toLowerCase().includes(query);
    finding.hidden = !visible;
    if (visible) shown++;
  });
  const empty = document.querySelector("#no-results");
  if (empty) empty.hidden = shown !== 0;
}
filters.forEach(button => button.addEventListener("click", () => {
  severity = button.dataset.severity;
  filters.forEach(item => {
    const active = item === button;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", String(active));
  });
  updateFindings();
}));
if (search) search.addEventListener("input", updateFindings);
const progress = document.querySelector("#scan-progress");
if (progress) {
  const status = document.querySelector("#scan-status");
  const retry = document.querySelector("#retry-status");
  let failures = 0;
  async function poll() {
    try {
      const response = await fetch(progress.dataset.statusUrl, {
        cache: "no-store"
      });
      if (response.status === 404) {
        status.textContent = "This report has expired or is unavailable. Start a new scan.";
        return;
      }
      if (!response.ok) throw new Error("Status unavailable");
      const result = await response.json();
      failures = 0;
      if (!["queued", "running"].includes(result.state)) {
        window.location.reload();
        return;
      }
      status.textContent = result.state === "queued" ? "Queued. Waiting for an available scan slot." : "Running. Resolving the compiler and analyzing your sources.";
      setTimeout(poll, 2000);
    } catch {
      failures++;
      status.textContent = "Could not check scan status. Your scan may still be running.";
      if (failures < 3) setTimeout(poll, 3000);
      else retry.hidden = false;
    }
  }
  retry.addEventListener("click", () => {
    retry.hidden = true;
    failures = 0;
    poll();
  });
  setTimeout(poll, 1000);
}
