import "./style.css";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
import brandMark from "./forge3d-mark.png";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import { filmstripArtifacts, selectedArtifactForRun } from "./preview-routing.mjs";

const api = window.forge3d;
const app = document.querySelector("#app");

let state = { runs: [], tools: {}, models: [], skill: null, activeJob: null };
let selectedRunId = null;
let selectedArtifactPath = null;
let attachments = [];
let approval = null;
let previewDispose = () => {};
let refreshTimer = null;
let viewportApi = null;

const panels = { library: false, inspector: true };
const viewportTools = { transform: "orbit", shading: "rendered", grid: true };

function readPreference(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch { return fallback; }
}
function writePreference(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* preferences are optional */ }
}
Object.assign(panels, readPreference("forge3d.panels", panels));
Object.assign(viewportTools, readPreference("forge3d.viewport", viewportTools));

const glyphs = {
  add: '<path d="M12 5v14M5 12h14"/>',
  archive: '<path d="M4 8h16v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z"/><path d="M3 4h18v4H3zM10 12h4"/>',
  attach: '<path d="m21.4 11.6-8.9 8.9a6 6 0 0 1-8.5-8.5l9.6-9.6a4 4 0 0 1 5.7 5.7L9.7 17.7a2 2 0 0 1-2.8-2.8l8.9-8.9"/>',
  camera: '<path d="M14.5 4 16 7h4a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h4l1.5-3h5Z"/><circle cx="12" cy="13" r="3"/>',
  check: '<path d="m5 13 4 4 10-11"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8.2 12.2 2.6 2.6 5-6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  chevronLeft: '<path d="m15 18-6-6 6-6"/>',
  clipboard: '<path d="M9 4H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2"/><rect x="9" y="2.6" width="6" height="3.6" rx="1.2"/><path d="M9 11.5h6M9 15.5h4"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  cube: '<path d="m21 8-9-5-9 5 9 5 9-5Z"/><path d="m3 8 9 5 9-5M3 8v8l9 5 9-5V8M12 13v8"/>',
  duplicate: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M12 18v-6M9 15h6"/>',
  film: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 5v14M17 5v14M3 12h18"/>',
  folder: '<path d="M3 6.5h6.2l2 2.2H21V19a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 19Z"/>',
  frame: '<path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4"/><rect x="9" y="9" width="6" height="6"/>',
  fullscreen: '<path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/>',
  grid: '<rect x="4" y="4" width="16" height="16" rx="1"/><path d="M4 10h16M4 16h16M10 4v16M16 4v16"/>',
  hand: '<path d="M9 11V5.6a1.6 1.6 0 0 1 3.2 0V11M12.2 11V4.4a1.6 1.6 0 0 1 3.2 0V11M15.4 11V6.6a1.6 1.6 0 0 1 3.2 0V15a6 6 0 0 1-6 6h-1.2a5 5 0 0 1-4.1-2.2l-3-4.3a1.7 1.7 0 0 1 2.5-2.2L9 14.6Z"/>',
  image: '<rect x="3" y="4.5" width="18" height="15" rx="2"/><circle cx="8.6" cy="9.6" r="1.4"/><path d="m4 17.5 5-4.6 3.6 3.4 3-2.6L20 17"/>',
  logs: '<rect x="3.5" y="4" width="17" height="16" rx="2"/><path d="m8 9.5 3 2.5-3 2.5M13 15h4"/>',
  more: '<circle cx="5.2" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="18.8" cy="12" r="1.5"/>',
  nodes: '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="19" r="2"/><path d="M7 7.2 10.8 17M17 7.2 13.2 17M7 6h10"/>',
  open: '<path d="M14 4h6v6M20 4 11 13"/><path d="M18 13.5V19a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 19V8a1.5 1.5 0 0 1 1.5-1.5H11"/>',
  orbit: '<circle cx="12" cy="12" r="3"/><path d="M3.5 12c0-4.7 3.8-8.5 8.5-8.5 2.2 0 4.2.8 5.7 2.2M20.5 12c0 4.7-3.8 8.5-8.5 8.5-2.2 0-4.2-.8-5.7-2.2M17 2v4h4M7 22v-4H3"/>',
  output: '<path d="M3.5 15v4a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-4"/><path d="M12 16V3.5M8.4 7.1 12 3.5l3.6 3.6"/>',
  play: '<path d="m8 5 11 7-11 7Z"/>',
  resume: '<path d="M3.5 12a8.5 8.5 0 1 0 2.8-6.3M3.5 4v5h5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
  shield: '<path d="M12 3.2 20 6v5.9c0 4.5-3.3 8.4-8 9.1-4.7-.7-8-4.6-8-9.1V6Z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
  sparkle: '<path d="M12 3.2 13.9 8.6 19.3 10.5 13.9 12.4 12 17.8 10.1 12.4 4.7 10.5 10.1 8.6Z"/><path d="m18.2 15.2.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8Z"/>',
  steer: '<path d="M21.5 2.5 10.8 13.2M21.5 2.5 14.9 21l-4.1-7.8L3 9.1Z"/>',
  stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="1.5"/>',
  text: '<path d="M5 5.5h14M5 10.5h14M5 15.5h9"/>',
  trash: '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l.9 13h9.2l.9-13M10 11v6M14 11v6"/>',
};

function glyph(name, className = "") {
  return `<svg class="ui-icon ${className}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${glyphs[name] || ""}</svg>`;
}

const selectOptions = {
  workflow: [["auto", "Auto route"], ["authored-blender", "Authored Blender"], ["image-to-mesh", "Image to mesh"], ["gaussian-splat", "Gaussian splat"], ["process", "Process existing"], ["rig", "Rig"], ["animate", "Animate"], ["retarget", "Retarget"], ["validate", "Validate"]],
  quality: [["balanced", "Balanced"], ["draft", "Draft"], ["production", "Production"]],
  target: [["glb", "GLB"], ["blend", "BLEND"], ["splat", "SPLAT / PLY"], ["gif", "GIF / sequence"]],
  tool: [["auto", "Auto"], ["blender", "Blender"], ["triposplat", "TripoSplat"], ["spar3d", "SPAR3D"], ["tripo-cloud", "Tripo cloud"]],
  effort: [["auto", "Model default"], ["low", "Low"], ["medium", "Medium"], ["high", "High"], ["xhigh", "Extra high"]],
};
function optionMarkup(name) {
  return selectOptions[name].map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
}

app.innerHTML = `
  <header class="topbar">
    <div class="brand" aria-label="Forge3D"><img src="${brandMark}" alt="" /><strong>Forge3D</strong></div>

    <div class="omnibox">
      <div class="omnibox-field">
        <textarea id="prompt" rows="1" aria-label="Forge3D prompt" placeholder="Describe the asset or change…"></textarea>
        <kbd title="Ctrl + Enter runs the prompt">Ctrl ↵</kbd>
      </div>
      <div id="attachments" class="attachment-row"></div>
    </div>

    <div class="topbar-actions">
      <button id="attach" class="ghost-action" title="Attach source files">${glyph("attach")}<span>Attach</span></button>
      <span class="v-sep"></span>
      <button id="settings-toggle" class="icon-action" aria-expanded="false" title="Run settings" aria-label="Run settings">${glyph("settings")}</button>
      <button id="cancel" class="icon-action danger hidden" title="Cancel the active run" aria-label="Cancel the active run">${glyph("stop")}</button>
      <button id="send" class="run-button"></button>
    </div>

    <div id="topbar-progress" class="topbar-progress"></div>
  </header>

  <main class="stage">
    <div id="preview" class="viewport"></div>

    <nav class="toolrail" aria-label="Viewport tools">
      <button class="rail-button" data-transform="orbit" title="Orbit" aria-label="Orbit">${glyph("orbit")}</button>
      <button class="rail-button" data-transform="pan" title="Pan" aria-label="Pan">${glyph("hand")}</button>
      <button class="rail-button" data-action="frame" title="Frame the asset" aria-label="Frame the asset">${glyph("frame")}</button>
      <div class="rail-sep"></div>
      <button class="rail-button" data-toggle="grid" title="Ground grid" aria-label="Ground grid">${glyph("grid")}</button>
      <div class="rail-sep"></div>
      <button class="rail-button" data-shading="matte" title="Clay shading" aria-label="Clay shading"><i class="shade-dot matte"></i></button>
      <button class="rail-button" data-shading="rendered" title="Rendered shading" aria-label="Rendered shading"><i class="shade-dot rendered"></i></button>
      <button class="rail-button" data-shading="wireframe" title="Wireframe" aria-label="Wireframe">${glyph("cube")}</button>
      <div class="rail-sep"></div>
      <button class="rail-button" data-action="capture" title="Capture the viewport" aria-label="Capture the viewport">${glyph("camera")}</button>
      <button class="rail-button" data-action="fullscreen" title="Fullscreen viewport" aria-label="Fullscreen viewport">${glyph("fullscreen")}</button>
    </nav>

    <div id="viewport-hud" class="viewport-hud"></div>

    <div class="dock-right">
      <aside id="library" class="panel library" aria-label="Run library">
        <header class="panel-head"><h2>Runs</h2><span id="run-count" class="head-count"></span></header>
        <div class="panel-tools">
          <button id="new-run" class="new-run">${glyph("add")}<span>New run</span></button>
          <label class="search-wrap">${glyph("search")}<input id="run-search" class="search" type="search" placeholder="Search runs" /></label>
        </div>
        <div id="run-list" class="panel-body"></div>
      </aside>

      <aside id="inspector" class="panel inspector" aria-label="Run inspector">
        <header class="panel-head">
          <h2>Inspector</h2>
          <button id="inspector-close" class="icon-action" title="Hide the inspector" aria-label="Hide the inspector">${glyph("close")}</button>
        </header>
        <div id="run-brief"></div>
        <div class="tabbar" role="tablist">
          <button class="tab active" role="tab" data-tab="steps">Steps</button>
          <button class="tab" role="tab" data-tab="artifacts">Files</button>
          <button class="tab" role="tab" data-tab="validation">Checks</button>
          <button class="tab" role="tab" data-tab="logs">Logs</button>
        </div>
        <div id="inspector-content" class="panel-body"></div>
        <footer id="inspector-actions" class="panel-foot"></footer>
      </aside>
    </div>

    <div class="edge-rail">
      <button id="library-toggle" class="edge-tab" aria-controls="library" aria-expanded="false" title="Run library (Ctrl+B)">Runs${glyph("chevronLeft")}</button>
      <button id="inspector-toggle" class="edge-tab" aria-controls="inspector" aria-expanded="true" title="Inspector (Ctrl+I)">Inspect${glyph("chevronLeft")}</button>
    </div>
  </main>

  <section class="dock" aria-label="Production pipeline">
    <div id="pipeline" class="pipeline"></div>
    <div id="filmstrip" class="filmstrip" aria-label="Run outputs"></div>
  </section>

  <footer class="statusbar">
    <div id="dependency-strip" class="dependency-strip"></div>
    <div id="agent-state" class="agent-state"></div>
    <span class="spacer"></span>
    <time id="status-time"></time>
  </footer>

  <section id="settings-popover" class="popover hidden" aria-label="Run settings">
    <div class="popover-head">
      <h3>Run settings</h3>
      <button id="settings-close" class="icon-action" title="Close" aria-label="Close run settings">${glyph("close")}</button>
    </div>
    <div class="popover-grid">
      <label class="field"><span>Workflow</span><select id="workflow">${optionMarkup("workflow")}</select></label>
      <label class="field"><span>Quality</span><select id="quality">${optionMarkup("quality")}</select></label>
      <label class="field"><span>Target</span><select id="target">${optionMarkup("target")}</select></label>
      <label class="field"><span>Tool / model</span><select id="tool">${optionMarkup("tool")}</select></label>
      <label class="field"><span>Codex model</span><select id="model"><option value="auto">Codex default</option></select></label>
      <label class="field"><span>Reasoning</span><select id="effort">${optionMarkup("effort")}</select></label>
      <label class="check consent wide"><input id="cloud-approved" type="checkbox" /><span>Allow cloud execution or file upload for this job only</span></label>
    </div>
  </section>

  <div id="approval-layer"></div>
  <div id="dialog-layer"></div>
  <div id="menu-layer"></div>
  <div id="toast-layer" aria-live="polite"></div>
`;

const elements = Object.fromEntries([
  "prompt", "attachments", "attach", "send", "cancel", "settings-toggle", "settings-popover", "topbar-progress",
  "preview", "viewport-hud", "library", "inspector", "run-list", "run-search", "run-count", "run-brief",
  "inspector-content", "inspector-actions", "library-toggle", "inspector-toggle",
  "pipeline", "filmstrip", "dependency-strip", "agent-state", "status-time",
  "workflow", "quality", "target", "tool", "model", "effort", "cloud-approved",
  "approval-layer", "dialog-layer", "menu-layer", "toast-layer",
].map((id) => [id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), document.querySelector(`#${id}`)]));

/* ── helpers ────────────────────────────────────────────────── */

function artifactUrl(runId, relativePath) {
  return `forge3d-artifact://${runId}/${relativePath.split("/").map(encodeURIComponent).join("/")}`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

function formatDate(value) {
  if (!value) return "Unknown time";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
}

function formatClock(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "" : new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KiB`;
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MiB`;
  return `${(bytes / 1073741824).toFixed(2)} GiB`;
}

function basename(value) {
  return String(value).split(/[\\/]/).pop();
}

function statusLabel(status) {
  return String(status || "unknown").replaceAll("_", " ");
}

function titleCase(value) {
  return String(value || "").replaceAll("-", " ").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function selectedRun() {
  return state.runs.find((run) => run.run_id === selectedRunId) || null;
}

function selectedArtifact(run = selectedRun()) {
  return selectedArtifactForRun(run, selectedArtifactPath);
}

function isImageRole(role) {
  return ["primary-image", "image", "animation", "image-sequence"].includes(role);
}

function artifactIcon(artifact) {
  const role = artifact?.preview_role;
  if (role === "model") return "cube";
  if (role === "gaussian-splat") return "sparkle";
  if (role === "validation") return "shield";
  if (role === "animation" || role === "image-sequence") return "film";
  if (isImageRole(role)) return "image";
  return "text";
}

function toast(message, kind = "info") {
  const item = document.createElement("div");
  item.className = `toast ${kind}`;
  item.textContent = message;
  elements.toastLayer.append(item);
  setTimeout(() => item.remove(), 4800);
}

/* ── overlay primitives ─────────────────────────────────────── */

function closeMenu() {
  elements.menuLayer.innerHTML = "";
}

function openMenu(box, items) {
  closeMenu();
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.innerHTML = items.map((item) => item === "-" ? "<hr />"
    : `<button data-menu-action="${escapeHtml(item.id)}" class="${item.danger ? "danger" : ""}">${glyph(item.icon)}<span>${escapeHtml(item.label)}</span></button>`).join("");
  elements.menuLayer.append(menu);
  const size = menu.getBoundingClientRect();
  menu.style.top = `${Math.min(box.bottom + 6, innerHeight - size.height - 12)}px`;
  menu.style.left = `${Math.max(12, Math.min(box.right - size.width, innerWidth - size.width - 12))}px`;
  menu.querySelectorAll("[data-menu-action]").forEach((button) => button.addEventListener("click", () => {
    const chosen = items.find((item) => item !== "-" && item.id === button.dataset.menuAction);
    closeMenu();
    chosen?.run?.();
  }));
  setTimeout(() => document.addEventListener("pointerdown", function once(event) {
    if (menu.contains(event.target)) return document.addEventListener("pointerdown", once, { once: true });
    closeMenu();
  }, { once: true }), 0);
}

function askDialog({ eyebrow = "Forge3D", title, body = "", detail = "", input = null, confirmLabel = "Continue", danger = false }) {
  return new Promise((resolve) => {
    const scrim = document.createElement("div");
    scrim.className = "scrim";
    scrim.innerHTML = `
      <section class="modal" role="dialog" aria-modal="true">
        <div class="modal-head">
          <small>${escapeHtml(eyebrow)}</small>
          <h2>${escapeHtml(title)}</h2>
          ${body ? `<p>${escapeHtml(body)}</p>` : ""}
        </div>
        <div class="modal-body">
          ${detail ? `<pre>${escapeHtml(detail)}</pre>` : ""}
          ${input ? `<textarea id="dialog-input">${escapeHtml(input.value || "")}</textarea>` : ""}
        </div>
        <div class="modal-foot">
          <button class="btn ghost" data-choice="cancel">Cancel</button>
          <button class="btn ${danger ? "danger" : "primary"}" data-choice="ok">${escapeHtml(confirmLabel)}</button>
        </div>
      </section>`;
    elements.dialogLayer.append(scrim);
    const field = scrim.querySelector("#dialog-input");
    field?.focus();
    field?.setSelectionRange(field.value.length, field.value.length);
    if (!field) scrim.querySelector(danger ? '[data-choice="cancel"]' : '[data-choice="ok"]').focus();
    const finish = (value) => { scrim.remove(); resolve(value); };
    scrim.querySelectorAll("[data-choice]").forEach((button) => button.addEventListener("click", () => {
      finish(button.dataset.choice === "cancel" ? null : input ? (field?.value ?? "") : true);
    }));
    scrim.addEventListener("pointerdown", (event) => { if (event.target === scrim) finish(null); });
    scrim.addEventListener("keydown", (event) => {
      if (event.key === "Escape") finish(null);
      if (event.key === "Enter" && !danger && (event.ctrlKey || event.metaKey || !input)) { event.preventDefault(); finish(input ? (field?.value ?? "") : true); }
    });
  });
}

/* ── status bar ─────────────────────────────────────────────── */

function renderDependencies() {
  const tools = [
    ["Codex", state.tools?.codex],
    ["Blender", state.tools?.blender],
    ["Godot", state.tools?.godot],
    ["WSL", state.tools?.wsl],
  ];
  const known = tools.filter(([, value]) => value !== undefined);
  const missing = known.filter(([, value]) => !value).map(([name]) => name);
  const checking = known.length < tools.length;
  const failed = Boolean(state.appServerError);
  const overall = failed ? "offline" : missing.length ? "attention" : checking ? "checking" : "ready";
  const overallLabel = failed ? "Toolchain offline" : missing.length ? "Toolchain attention" : checking ? "Checking toolchain" : "Local toolchain ready";
  elements.dependencyStrip.innerHTML = `<span class="status-item ${overall}"><i></i>${overallLabel}</span><span class="status-divider"></span>${
    tools.map(([name, value]) => `<span class="status-item ${value ? "ready" : value === undefined ? "checking" : "offline"}"><i></i>${name}${name === "Blender" && value ? " 4.5" : name === "Godot" && value ? " 4.4" : ""}</span>`).join("")}`;

  const skill = state.skill;
  const needsRepair = skill && skill.state !== "ready";
  const message = failed ? state.appServerError
    : needsRepair ? (skill.state === "version-mismatch" ? `Plugin ${skill.installedVersion} → ${skill.bundledVersion}` : "Plugin repair available")
    : "";
  elements.agentState.classList.toggle("hidden", !message);
  elements.agentState.innerHTML = message ? `<span>${escapeHtml(message)}</span>${needsRepair ? '<button id="repair-skill" class="link-button">Repair</button>' : ""}` : "";
  document.querySelector("#repair-skill")?.addEventListener("click", repairPlugin);
}

function renderModelOptions() {
  const current = elements.model.value;
  elements.model.innerHTML = '<option value="auto">Codex default</option>' + (state.models || [])
    .map((model) => `<option value="${escapeHtml(model.id || model.model)}">${escapeHtml(model.displayName || model.id || model.model)}</option>`).join("");
  if ([...elements.model.options].some((option) => option.value === current)) elements.model.value = current;
}

/* ── run library ────────────────────────────────────────────── */

function runGroups(runs) {
  const groups = new Map();
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const sameDay = (left, right) => left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth() && left.getDate() === right.getDate();
  for (const run of runs) {
    const date = new Date(run.updated_at || run.created_at || Date.now());
    const label = sameDay(date, today) ? "Today"
      : sameDay(date, yesterday) ? "Yesterday"
      : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: date.getFullYear() === today.getFullYear() ? undefined : "numeric" }).format(date);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push({ run, date });
  }
  return groups;
}

function runThumb(run) {
  const artifact = run.artifacts?.find((item) => item.preview_role === "primary-image")
    || run.artifacts?.find((item) => isImageRole(item.preview_role));
  if (artifact) return `<img src="${artifactUrl(run.run_id, artifact.path)}" alt="" loading="lazy" />`;
  return glyph(run.artifacts?.length ? artifactIcon(run.artifacts[0]) : "cube");
}

function renderRuns() {
  const query = elements.runSearch.value.trim().toLowerCase();
  const runs = state.runs.filter((run) => [run.prompt, run.workflow_route, run.status, run.name]
    .some((value) => String(value || "").toLowerCase().includes(query)));
  elements.runCount.textContent = state.runs.length ? String(state.runs.length) : "";
  const groups = runGroups(runs);
  elements.runList.innerHTML = groups.size ? [...groups.entries()].map(([label, entries]) => `
    <section class="run-group">
      <h3>${escapeHtml(label)}</h3>
      ${entries.map(({ run, date }) => `
        <div class="run-card ${run.run_id === selectedRunId ? "selected" : ""}" data-run-id="${escapeHtml(run.run_id)}" role="button" tabindex="0">
          <span class="run-tile">${runThumb(run)}</span>
          <span class="run-lines">
            <strong>${escapeHtml(run.prompt || run.name || "Untitled run")}</strong>
            <small><i class="run-state ${escapeHtml(run.status || "")}"></i><em>${escapeHtml(titleCase(run.workflow_route || run.status || "run"))}</em> · ${escapeHtml(formatClock(date))}</small>
          </span>
          <button class="run-more" data-run-menu="${escapeHtml(run.run_id)}" title="Run actions" aria-label="Run actions">${glyph("more")}</button>
        </div>`).join("")}
    </section>`).join("")
    : `<div class="empty-list">${glyph("search")}<span>${query ? "No runs match that search." : "No runs yet. Describe an asset to forge the first one."}</span></div>`;

  elements.runList.querySelectorAll("[data-run-id]").forEach((card) => {
    card.addEventListener("click", (event) => { if (!event.target.closest("[data-run-menu]")) selectRun(card.dataset.runId); });
    card.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectRun(card.dataset.runId); } });
  });
  elements.runList.querySelectorAll("[data-run-menu]").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    const run = state.runs.find((item) => item.run_id === button.dataset.runMenu);
    if (!run) return;
    const box = button.getBoundingClientRect();
    selectRun(run.run_id);
    openMenu(box, [
      { id: "continue", icon: "resume", label: "Resume this run", run: () => runAction("continue") },
      { id: "duplicate", icon: "duplicate", label: "Duplicate", run: () => runAction("duplicate") },
      "-",
      { id: "archive", icon: "archive", label: "Archive", run: () => runAction("archive") },
      { id: "trash", icon: "trash", label: "Move to trash", danger: true, run: () => runAction("trash") },
    ]);
  }));
}

/* ── production pipeline ────────────────────────────────────── */

function summarizeValidation(validation) {
  const entries = Object.entries(validation || {});
  const flags = entries.filter(([, value]) => typeof value === "boolean");
  if (flags.length) return `${flags.filter(([, value]) => value).length}/${flags.length} checks passed`;
  if (typeof validation?.status === "string") return titleCase(validation.status);
  return `${entries.length} result${entries.length === 1 ? "" : "s"}`;
}

function pipelineStages(run) {
  const steps = run?.steps || [];
  const artifacts = run?.artifacts || [];
  const completed = steps.filter((step) => step.status === "completed").length;
  const running = steps.find((step) => step.status === "running" || step.status === "inProgress");
  const status = run?.status || null;
  const live = Boolean(state.activeJob && run && state.activeJob.runId === run.run_id);
  const finished = status === "completed";
  const failed = status === "failed";
  const stopped = status === "interrupted" || status === "cancelled";
  const starting = status === "prepared" || status === "launching";
  const validation = run?.validation && Object.keys(run.validation).length ? run.validation : null;
  const reports = artifacts.filter((artifact) => artifact.preview_role === "validation");
  const checked = Boolean(validation) || reports.length > 0;

  const plan = !run ? { state: "idle", fill: 0, detail: "Waiting for a prompt" }
    : starting ? { state: "active", fill: 0.55, detail: "Routing the request" }
    : { state: "done", fill: 1, detail: run.workflow_route ? titleCase(run.workflow_route) : "Request routed" };

  const buildFill = finished ? 1 : live ? 0.62 : completed ? 0.45 : 0;
  const currentActivity = running?.detail || running?.name;
  const build = !run || starting ? { state: "idle", fill: 0, detail: "Not started" }
    : failed ? { state: "failed", fill: buildFill, detail: run.failure || "The run failed" }
    : stopped ? { state: "failed", fill: buildFill, detail: titleCase(status) }
    : finished ? { state: "done", fill: 1, detail: `${completed} tool action${completed === 1 ? "" : "s"} complete` }
    : { state: "active", fill: buildFill, detail: currentActivity ? titleCase(currentActivity) : completed ? `${completed} tool action${completed === 1 ? "" : "s"} complete · working` : "Starting local tools" };

  const failedChecks = Object.values(validation || {}).some((value) => value === false);
  const check = !run ? { state: "idle", fill: 0, detail: "Not started" }
    : checked ? { state: failed ? "failed" : failedChecks ? "warn" : "done", fill: 1, detail: validation ? summarizeValidation(validation) : `${reports.length} report${reports.length === 1 ? "" : "s"}` }
    : finished ? { state: "idle", fill: 0, detail: "No validation recorded" }
    : build.state === "active" ? { state: "idle", fill: 0, detail: "Waiting for the build" }
    : { state: "idle", fill: 0, detail: "Not started" };

  const output = !run ? { state: "idle", fill: 0, detail: "No outputs yet" }
    : artifacts.length ? { state: finished ? "done" : "active", fill: finished ? 1 : 0.6, detail: `${artifacts.length} artifact${artifacts.length === 1 ? "" : "s"}` }
    : failed ? { state: "failed", fill: 0, detail: "Nothing produced" }
    : { state: "idle", fill: 0, detail: "Preparing deliverables" };

  return [
    { key: "plan", label: "Plan", icon: "clipboard", ...plan },
    { key: "build", label: "Build", icon: "cube", ...build },
    { key: "check", label: "Check", icon: "shield", ...check },
    { key: "output", label: "Output", icon: "output", ...output },
  ];
}

function renderPipeline() {
  const run = selectedRun();
  elements.pipeline.innerHTML = pipelineStages(run).map((stage) => `
    <div class="stage-node ${stage.state}">
      <span class="stage-icon">${glyph(stage.state === "done" ? "check" : stage.icon)}</span>
      <div class="stage-body">
        <div class="stage-top">
          <span class="stage-label">${stage.label.toUpperCase()}</span>
          <span class="stage-rail"><i class="stage-fill" style="width:${Math.round(Math.min(1, stage.fill) * 100)}%"></i></span>
        </div>
        <div class="stage-detail">${escapeHtml(stage.detail)}</div>
      </div>
    </div>`).join("");
}

function renderFilmstrip() {
  const run = selectedRun();
  const artifacts = filmstripArtifacts(run, selectedArtifactPath, 16);
  if (!artifacts.length) {
    elements.filmstrip.innerHTML = Array.from({ length: 4 }, () => '<div class="film-tile film-ghost"></div>').join("");
    return;
  }
  const active = selectedArtifact(run);
  elements.filmstrip.innerHTML = artifacts.map((artifact) => `
    <button class="film-tile ${artifact.path === active?.path ? "selected" : ""}" data-film-path="${escapeHtml(artifact.path)}" title="${escapeHtml(artifact.name)}">
      ${isImageRole(artifact.preview_role)
        ? `<img src="${artifactUrl(run.run_id, (artifact.frames && artifact.frames[0]) || artifact.path)}" alt="${escapeHtml(artifact.name)}" loading="lazy" />`
        : `<span class="film-glyph">${glyph(artifactIcon(artifact))}<span>${escapeHtml(String(artifact.preview_role || "file").split("-")[0])}</span></span>`}
    </button>`).join("");
  elements.filmstrip.querySelectorAll("[data-film-path]").forEach((tile) => tile.addEventListener("click", () => selectArtifact(tile.dataset.filmPath)));
}

function renderHud() {
  const run = selectedRun();
  const artifact = selectedArtifact(run);
  if (!run) { elements.viewportHud.innerHTML = ""; return; }
  const status = String(run.status || "");
  elements.viewportHud.innerHTML = `
    <strong>${escapeHtml(run.prompt || run.name || "Untitled run")}</strong>
    ${artifact ? `<span class="hud-dot"></span><strong>${escapeHtml(artifact.name)}</strong>` : ""}
    <span class="hud-tag ${escapeHtml(status)}">${escapeHtml(statusLabel(status))}</span>`;
}

/* ── inspector ──────────────────────────────────────────────── */

function activeTab() {
  return document.querySelector(".tab.active")?.dataset.tab || "steps";
}

function renderRunBrief() {
  const run = selectedRun();
  if (!run) { document.querySelector("#run-brief").innerHTML = ""; return; }
  document.querySelector("#run-brief").innerHTML = `
    <div class="run-brief">
      <p>${escapeHtml(run.prompt || run.name || "Untitled run")}</p>
      <div class="run-brief-meta">
        <span class="pill ${escapeHtml(String(run.status || ""))}">${escapeHtml(statusLabel(run.status))}</span>
        ${run.workflow_route ? `<span>${escapeHtml(titleCase(run.workflow_route))}</span>` : ""}
        <span>${escapeHtml(formatDate(run.updated_at || run.created_at))}</span>
      </div>
    </div>`;
}

function renderInspector() {
  const run = selectedRun();
  const tab = activeTab();
  if (!run) {
    elements.inspectorContent.innerHTML = `<div class="empty-list">${glyph("cube")}<span>Select a run to inspect its steps, files, and logs.</span></div>`;
    renderInspectorActions();
    return;
  }
  if (tab === "steps") {
    elements.inspectorContent.innerHTML = run.steps?.length
      ? `<ol class="step-list">${run.steps.map((step) => `
          <li>
            <i class="step-dot ${escapeHtml(step.status)}"></i>
            <div class="step-text"><strong>${escapeHtml(titleCase(step.name))}</strong><small>${escapeHtml(statusLabel(step.status))}${step.detail ? ` · ${escapeHtml(String(step.detail).slice(0, 90))}` : ""}</small></div>
          </li>`).join("")}</ol>`
      : `<div class="empty-list">${glyph("nodes")}<span>Steps appear as soon as the run starts.</span></div>`;
  } else if (tab === "artifacts") {
    elements.inspectorContent.innerHTML = run.artifacts?.length
      ? `<div class="artifact-list">${run.artifacts.map((artifact) => `
          <button class="artifact-card ${artifact.path === selectedArtifact(run)?.path ? "selected" : ""}" data-artifact-path="${escapeHtml(artifact.path)}">
            <span class="artifact-thumb">${isImageRole(artifact.preview_role)
              ? `<img src="${artifactUrl(run.run_id, (artifact.frames && artifact.frames[0]) || artifact.path)}" alt="" loading="lazy" />`
              : glyph(artifactIcon(artifact))}</span>
            <span class="artifact-lines"><strong>${escapeHtml(artifact.name)}</strong><small>${escapeHtml(titleCase(artifact.preview_role))} · ${escapeHtml(formatBytes(artifact.size_bytes))}</small></span>
          </button>`).join("")}</div>`
      : `<div class="empty-list">${glyph("folder")}<span>Files are discovered inside this run directory only.</span></div>`;
    elements.inspectorContent.querySelectorAll("[data-artifact-path]").forEach((button) => button.addEventListener("click", () => selectArtifact(button.dataset.artifactPath)));
  } else if (tab === "validation") {
    const validation = run.validation && Object.keys(run.validation).length ? run.validation : null;
    const reports = (run.artifacts || []).filter((artifact) => artifact.preview_role === "validation");
    const rows = validation ? Object.entries(validation).map(([key, value]) => `
      <div><span>${escapeHtml(titleCase(key))}</span><strong class="${value === true ? "ok" : value === false ? "bad" : ""}">${escapeHtml(typeof value === "object" ? JSON.stringify(value) : String(value))}</strong></div>`).join("") : "";
    elements.inspectorContent.innerHTML = `${validation ? `<div class="kv">${rows}</div>` : `<div class="empty-list">${glyph("shield")}<span>No inline validation result yet.</span></div>`}
      ${reports.length ? `<div class="section-label">Reports</div>${reports.map((report) => `<button class="report-link" data-artifact-path="${escapeHtml(report.path)}">${glyph("file")}<span>${escapeHtml(report.name)}</span></button>`).join("")}` : ""}`;
    elements.inspectorContent.querySelectorAll("[data-artifact-path]").forEach((button) => button.addEventListener("click", () => selectArtifact(button.dataset.artifactPath)));
  } else {
    const entries = run.transcript || [];
    const labels = {
      agent: "Assistant",
      log: "Tool output",
      activity: "Tool activity",
      event: "Forge3D",
      "approval-request": "Approval needed",
      "approval-decision": "Approval",
      "app-server-stderr": "App Server",
      error: "Error",
      user: "Prompt",
      "user-steer": "Steering note",
    };
    elements.inspectorContent.innerHTML = entries.length
      ? `<div class="log-list">${entries.slice(-200).map((entry) => `
          <article class="log-entry ${escapeHtml(entry.kind)}">
            <small>${escapeHtml(labels[entry.kind] || titleCase(entry.kind))} · ${escapeHtml(formatDate(entry.at))}</small>
            <pre>${escapeHtml(entry.text || entry.method || JSON.stringify(entry.params || {}))}</pre>
          </article>`).join("")}</div>`
      : `<div class="empty-list">${glyph("logs")}<span>Assistant messages and useful tool output appear here.</span></div>`;
    elements.inspectorContent.scrollTop = elements.inspectorContent.scrollHeight;
  }
  renderInspectorActions();
}

function renderInspectorActions() {
  const run = selectedRun();
  const artifact = selectedArtifact(run);
  const lower = String(artifact?.path || "").toLowerCase();
  const actions = [
    { id: "reveal", icon: "folder", label: "Reveal in Explorer" },
    { id: "copy", icon: "copy", label: "Copy path" },
    { id: "open", icon: "open", label: "Open" },
  ];
  if ([".blend", ".glb", ".gltf", ".fbx", ".obj"].some((extension) => lower.endsWith(extension))) actions.push({ id: "blender", icon: "cube", label: "Open in Blender" });
  if ([".glb", ".gltf", ".splat", ".ply", ".sog"].some((extension) => lower.endsWith(extension))) actions.push({ id: "godot", icon: "play", label: "Review in Godot" });
  elements.inspectorActions.innerHTML = actions.map((action) => `
    <button data-artifact-action="${action.id}" title="${escapeHtml(action.label)}" aria-label="${escapeHtml(action.label)}" ${artifact ? "" : "disabled"}>${glyph(action.icon)}</button>`).join("");
  elements.inspectorActions.querySelectorAll("[data-artifact-action]").forEach((button) => button.addEventListener("click", () => artifactAction(button.dataset.artifactAction)));
}

/* ── viewport ───────────────────────────────────────────────── */

const clayMaterial = new THREE.MeshStandardMaterial({ color: 0x9ba1a8, roughness: 0.74, metalness: 0.02 });
const wireMaterial = new THREE.MeshBasicMaterial({ color: 0xe2571c, wireframe: true });

function disposeThree(scene, renderer, animationId, observer) {
  cancelAnimationFrame(animationId.value);
  observer.disconnect();
  scene.traverse((object) => {
    object.geometry?.dispose?.();
    const materials = [object.material, object.userData?.originalMaterial]
      .flatMap((value) => Array.isArray(value) ? value : value ? [value] : [])
      .filter((material) => material !== clayMaterial && material !== wireMaterial);
    for (const material of materials) {
      for (const value of Object.values(material)) if (value?.isTexture) value.dispose();
      material.dispose?.();
    }
    if (object instanceof SplatMesh) object.dispose();
  });
  renderer.dispose();
}

function applyShading(root, mode) {
  root?.traverse((object) => {
    if (!object.isMesh) return;
    if (!object.userData.originalMaterial) object.userData.originalMaterial = object.material;
    object.material = mode === "matte" ? clayMaterial : mode === "wireframe" ? wireMaterial : object.userData.originalMaterial;
  });
}

function applyTransformTool(controls) {
  controls.mouseButtons = {
    LEFT: viewportTools.transform === "pan" ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE,
    MIDDLE: THREE.MOUSE.DOLLY,
    RIGHT: THREE.MOUSE.PAN,
  };
}

function threeBase(container, withSpark = false) {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 1000);
  camera.position.set(2.5, 1.8, 3.2);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance", preserveDrawingBuffer: true });
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  container.append(renderer.domElement);

  let grid = null;
  if (withSpark) scene.add(new SparkRenderer({ renderer }));
  else {
    scene.add(new THREE.HemisphereLight(0xd7e1ea, 0x0a0d12, 2.1));
    const key = new THREE.DirectionalLight(0xffb27a, 3.2);
    key.position.set(3, 6, 4);
    const rim = new THREE.DirectionalLight(0x89b4e8, 1.1);
    rim.position.set(-4, 2.5, -3.5);
    grid = new THREE.GridHelper(14, 28, 0x46586a, 0x22303c);
    grid.material.transparent = true;
    grid.material.opacity = 0.5;
    grid.visible = viewportTools.grid;
    scene.add(key, rim, grid);
  }

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  applyTransformTool(controls);

  const resize = () => {
    const { width, height } = container.getBoundingClientRect();
    renderer.setSize(Math.max(width, 1), Math.max(height, 1), false);
    camera.aspect = Math.max(width, 1) / Math.max(height, 1);
    camera.updateProjectionMatrix();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(container);
  resize();
  return { scene, camera, renderer, controls, observer, grid };
}

// A SplatMesh carries no mesh geometry, so Box3.setFromObject cannot see its extents.
// Spark reports them itself; everything else measures normally.
function objectBounds(object) {
  if (object instanceof SplatMesh && typeof object.getBoundingBox === "function") {
    const local = object.getBoundingBox();
    if (local && !local.isEmpty()) {
      object.updateMatrixWorld(true);
      return local.clone().applyMatrix4(object.matrixWorld);
    }
  }
  return new THREE.Box3().setFromObject(object);
}

function frameObject(object, camera, controls) {
  const box = objectBounds(object);
  if (box.isEmpty()) return;
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const radius = Math.max(sphere.radius, 0.1);
  const distance = (radius / Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5))) * 1.45;
  controls.target.copy(sphere.center);
  camera.position.copy(sphere.center).addScaledVector(new THREE.Vector3(1, 0.72, 1.25).normalize(), distance);
  camera.near = Math.max(distance / 100, 0.001);
  camera.far = Math.max(distance * 40, 100);
  camera.updateProjectionMatrix();
  controls.update();
}

function publishViewportApi(base, root, { shading = true } = {}) {
  viewportApi = {
    frame: () => root && frameObject(root, base.camera, base.controls),
    setGrid: (visible) => { if (base.grid) base.grid.visible = visible; },
    setShading: (mode) => { if (shading) applyShading(root, mode); },
    setTransform: () => applyTransformTool(base.controls),
  };
  if (shading) applyShading(root, viewportTools.shading);
}

async function renderModel(container, run, artifact) {
  const status = document.createElement("div");
  status.className = "preview-status";
  status.textContent = "Loading model…";
  container.append(status);
  const base = threeBase(container);
  const animationId = { value: 0 };
  const clock = new THREE.Clock();
  let mixer = null;
  const animate = () => {
    animationId.value = requestAnimationFrame(animate);
    mixer?.update(clock.getDelta());
    base.controls.update();
    base.renderer.render(base.scene, base.camera);
  };
  animate();
  try {
    const gltf = await new GLTFLoader().loadAsync(artifactUrl(run.run_id, artifact.path));
    base.scene.add(gltf.scene);
    if (gltf.animations.length) {
      mixer = new THREE.AnimationMixer(gltf.scene);
      mixer.clipAction(gltf.animations[0]).play();
    }
    frameObject(gltf.scene, base.camera, base.controls);
    publishViewportApi(base, gltf.scene);
    status.textContent = gltf.animations.length
      ? `${gltf.animations.length} animation clip${gltf.animations.length === 1 ? "" : "s"} · first clip playing`
      : "Drag to orbit · scroll to zoom";
  } catch (error) {
    status.textContent = `Could not load model: ${error.message}`;
  }
  return () => disposeThree(base.scene, base.renderer, animationId, base.observer);
}

async function renderSplat(container, run, artifact) {
  const status = document.createElement("div");
  status.className = "preview-status";
  status.textContent = "Reading splat…";
  container.append(status);
  const base = threeBase(container, true);
  const animationId = { value: 0 };
  const animate = () => {
    animationId.value = requestAnimationFrame(animate);
    base.controls.update();
    base.renderer.render(base.scene, base.camera);
  };
  animate();
  try {
    const response = await fetch(artifactUrl(run.run_id, artifact.path));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const fileBytes = new Uint8Array(await response.arrayBuffer());
    const splat = new SplatMesh({ fileBytes, fileName: basename(artifact.path), onProgress: (event) => {
      const progress = event.lengthComputable ? ` ${Math.round((event.loaded / event.total) * 100)}%` : "";
      status.textContent = `Decoding splat${progress}…`;
    } });
    splat.quaternion.set(1, 0, 0, 0);
    base.scene.add(splat);
    await splat.initialized;
    frameObject(splat, base.camera, base.controls);
    publishViewportApi(base, splat, { shading: false });
    status.textContent = `${splat.numSplats.toLocaleString()} splats · drag to orbit`;
  } catch (error) {
    status.textContent = `Could not load splat: ${error.message}`;
  }
  return () => disposeThree(base.scene, base.renderer, animationId, base.observer);
}

function emptyViewport() {
  return `<div class="viewport-empty" aria-label="Empty viewport">
    <span class="empty-glow"></span>
    <div class="empty-body">
      <img src="${brandMark}" alt="" />
      <h2>Nothing forged yet</h2>
      <p>Describe an asset in the prompt bar. Forge3D routes it, builds it locally, and shows the result here.</p>
    </div>
  </div>`;
}

async function renderPreview() {
  previewDispose();
  previewDispose = () => {};
  viewportApi = null;
  const run = selectedRun();
  const artifact = selectedArtifact(run);
  renderHud();
  if (!run || !artifact) {
    elements.preview.classList.add("inset-panels");
    elements.preview.innerHTML = emptyViewport();
    return;
  }
  selectedArtifactPath = artifact.path;
  elements.preview.innerHTML = "";
  const role = artifact.preview_role;
  elements.preview.classList.toggle("inset-panels", role !== "model" && role !== "gaussian-splat");
  if (["primary-image", "image", "animation"].includes(role)) {
    const image = new Image();
    image.className = "media-preview";
    image.alt = artifact.name;
    image.src = artifactUrl(run.run_id, artifact.path);
    elements.preview.append(image);
  } else if (role === "image-sequence") {
    const image = new Image();
    image.className = "media-preview";
    elements.preview.append(image);
    let index = 0;
    const frames = artifact.frames || [artifact.path];
    const draw = () => { image.src = artifactUrl(run.run_id, frames[index % frames.length]); index += 1; };
    draw();
    const timer = setInterval(draw, 1000 / 12);
    previewDispose = () => clearInterval(timer);
  } else if (role === "model") {
    previewDispose = await renderModel(elements.preview, run, artifact);
  } else if (role === "gaussian-splat") {
    previewDispose = await renderSplat(elements.preview, run, artifact);
  } else if (["validation", "text"].includes(role)) {
    const pre = document.createElement("pre");
    pre.className = "text-preview";
    pre.textContent = "Loading…";
    elements.preview.append(pre);
    try {
      const response = await fetch(artifactUrl(run.run_id, artifact.path));
      const text = await response.text();
      pre.textContent = artifact.media_type === "application/json" ? JSON.stringify(JSON.parse(text), null, 2) : text;
    } catch (error) {
      pre.textContent = `Could not load ${artifact.name}: ${error.message}`;
    }
  } else {
    elements.preview.innerHTML = `<div class="blank-state">${glyph(artifactIcon(artifact))}<h2>${escapeHtml(artifact.name)}</h2><p>${escapeHtml(artifact.media_type)} · ${escapeHtml(formatBytes(artifact.size_bytes))}</p><p>This file has no embedded preview. Use Reveal or Open in the inspector.</p></div>`;
  }
}

function captureViewport() {
  const canvas = elements.preview.querySelector("canvas");
  if (!canvas) return toast("The viewport has no rendered 3D output to capture", "error");
  try {
    canvas.toBlob((blob) => {
      if (!blob) return toast("The viewport could not be captured", "error");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `forge3d-viewport-${Date.now()}.png`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      toast("Viewport captured");
    }, "image/png");
  } catch (error) {
    toast(error.message, "error");
  }
}

/* ── composer, approvals, and orchestration ─────────────────── */

function renderAttachments() {
  elements.attachments.innerHTML = attachments.map((item, index) => `
    <span class="attachment-chip">${escapeHtml(basename(item))}<button data-remove-attachment="${index}" aria-label="Remove ${escapeHtml(basename(item))}">×</button></span>`).join("");
  elements.attachments.querySelectorAll("[data-remove-attachment]").forEach((button) => button.addEventListener("click", () => {
    attachments.splice(Number(button.dataset.removeAttachment), 1);
    renderAttachments();
  }));
}

function renderComposer() {
  const active = state.activeJob;
  elements.send.innerHTML = active ? `${glyph("steer")}<span>Steer</span>` : `${glyph("play")}<span>Run</span>`;
  elements.send.classList.toggle("steering", Boolean(active));
  elements.send.title = active ? "Send a steering note to the running job" : "Run the prompt";
  elements.cancel.classList.toggle("hidden", !active);
  elements.topbarProgress.classList.toggle("on", Boolean(active));
  elements.cloudApproved.disabled = Boolean(active);
  elements.prompt.placeholder = active ? "Steer the running job…" : "Describe the asset or change…";
}

function renderApproval() {
  if (!approval) {
    elements.approvalLayer.innerHTML = "";
    return;
  }
  const params = approval.params || {};
  const request = params.request || {};
  const network = params.networkApprovalContext;
  const isMcp = approval.method === "mcpServer/elicitation/request";
  const persistence = request._meta?.persist;
  const canPersistSession = persistence === "session" || persistence === "always" || (Array.isArray(persistence) && persistence.includes("session"));
  const title = network ? `Network access to ${network.host || "an external host"}`
    : isMcp ? `${titleCase(params.serverName || "Local")} tool approval`
      : approval.method.includes("fileChange") ? "Approve file changes" : "Approve command";
  const detail = network ? `${network.protocol || "network"} access${network.port ? ` on port ${network.port}` : ""}`
    : request.message || params.command || params.reason || JSON.stringify(params, null, 2);
  const explanation = isMcp ? "A local Forge3D tool is ready to perform this action." : params.reason || "Forge3D needs your decision before continuing.";
  elements.approvalLayer.innerHTML = `
    <div class="scrim">
      <section class="modal" role="dialog" aria-modal="true">
        <div class="modal-head">
          <small>Codex approval</small>
          <h2>${escapeHtml(title)}</h2>
          <p>${escapeHtml(explanation)}</p>
        </div>
        <div class="modal-body"><pre>${escapeHtml(detail)}</pre></div>
        <div class="modal-foot">
          <button class="btn ghost" data-decision="cancel">Cancel job action</button>
          <button class="btn danger" data-decision="decline">Deny</button>
          ${canPersistSession ? '<button class="btn" data-decision="acceptForSession">Approve for session</button>' : ""}
          <button class="btn primary" data-decision="accept">Approve once</button>
        </div>
      </section>
    </div>`;
  elements.approvalLayer.querySelectorAll("[data-decision]").forEach((button) => button.addEventListener("click", () => decideApproval(button.dataset.decision)));
}

function renderAll({ preview = true } = {}) {
  if (!selectedRunId && state.runs.length) selectedRunId = state.runs[0].run_id;
  if (selectedRunId && !state.runs.some((run) => run.run_id === selectedRunId)) selectedRunId = state.runs[0]?.run_id || null;
  renderDependencies();
  renderModelOptions();
  renderRuns();
  renderRunBrief();
  renderInspector();
  renderPipeline();
  renderFilmstrip();
  renderComposer();
  renderApproval();
  renderHud();
  if (preview) renderPreview();
}

function selectRun(runId) {
  if (runId === selectedRunId) return;
  selectedRunId = runId;
  selectedArtifactPath = null;
  renderAll();
}

function selectArtifact(path) {
  selectedArtifactPath = path;
  renderInspector();
  renderFilmstrip();
  renderPreview();
}

function setPanel(name, open) {
  panels[name] = open;
  elements[name].dataset.open = String(open);
  elements[`${name}Toggle`].setAttribute("aria-expanded", String(open));
  writePreference("forge3d.panels", panels);
  updateDockOffset();
}

// Keeps flat previews and the empty state centred in the space the panels leave free.
function updateDockOffset() {
  const styles = getComputedStyle(document.documentElement);
  const width = (name) => parseFloat(styles.getPropertyValue(name)) || 0;
  const open = (panels.library ? width("--lib-w") + 12 : 0) + (panels.inspector ? width("--insp-w") + 12 : 0);
  document.querySelector(".stage").style.setProperty("--dock-offset", `${open + 60}px`);
}

function setViewportTool(key, value) {
  viewportTools[key] = value;
  writePreference("forge3d.viewport", viewportTools);
  document.querySelectorAll(`[data-${key === "transform" ? "transform" : key === "shading" ? "shading" : "toggle"}]`).forEach((button) => {
    if (key === "grid") button.classList.toggle("active", Boolean(value));
    else button.classList.toggle("active", button.dataset[key] === value);
  });
  if (key === "grid") viewportApi?.setGrid(Boolean(value));
  if (key === "shading") viewportApi?.setShading(value);
  if (key === "transform") viewportApi?.setTransform();
}

async function refreshState(preview = false) {
  try {
    const refreshed = await api.refreshTools({});
    state = { ...state, ...refreshed };
    renderAll({ preview });
  } catch (error) {
    toast(error.message, "error");
  }
}

function scheduleRefresh() {
  if (refreshTimer) return;
  refreshTimer = setTimeout(async () => {
    refreshTimer = null;
    await refreshState(false);
  }, 280);
}

async function startOrSteer() {
  const text = elements.prompt.value.trim();
  if (!text) {
    elements.prompt.focus();
    return toast("Write a prompt first", "error");
  }
  elements.send.disabled = true;
  try {
    if (state.activeJob) {
      await api.steer({ runId: state.activeJob.runId, text });
      elements.prompt.value = "";
      autoGrowPrompt();
      toast("Steering note sent", "success");
    } else {
      const cloudApproved = elements.cloudApproved.checked;
      if (cloudApproved) {
        const agreed = await askDialog({
          eyebrow: "Cloud approval",
          title: "Approve cloud execution for this job?",
          body: "Forge3D will still ask for provider or command approvals when a step requires them. This consent covers this single job.",
          confirmLabel: "Approve this job",
        });
        if (!agreed) return;
      }
      const result = await api.startRun({
        prompt: text,
        attachments,
        workflow: elements.workflow.value,
        quality: elements.quality.value,
        targetFormat: elements.target.value,
        tool: elements.tool.value,
        model: elements.model.value,
        effort: elements.effort.value,
        cloudApproved,
        outputSettings: {},
      });
      state = { ...state, ...result };
      selectedRunId = state.activeJob?.runId || state.runs[0]?.run_id;
      selectedArtifactPath = null;
      attachments = [];
      elements.prompt.value = "";
      elements.cloudApproved.checked = false;
      autoGrowPrompt();
      renderAttachments();
      renderAll();
    }
  } catch (error) {
    toast(error.message, "error");
  } finally {
    elements.send.disabled = false;
  }
}

async function cancelActive() {
  if (!state.activeJob) return toast("No run is active");
  try {
    state = { ...state, ...(await api.cancel({ runId: state.activeJob.runId })) };
    renderAll({ preview: false });
  } catch (error) {
    toast(error.message, "error");
  }
}

async function decideApproval(decision) {
  try {
    await api.answerApproval({ requestId: approval.requestId, decision });
    approval = null;
    renderApproval();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function repairPlugin() {
  const agreed = await askDialog({
    eyebrow: "Codex plugin",
    title: "Repair the Forge3D Codex plugin?",
    body: "The plugin is reinstalled from this application bundle. The current plugin directory is preserved as a timestamped backup.",
    confirmLabel: "Repair plugin",
  });
  if (!agreed) return;
  try {
    const result = await api.repairPlugin();
    state.skill = result.skill;
    renderDependencies();
    toast(`Forge3D plugin ${result.version} is ready`, "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function runAction(action) {
  const run = selectedRun();
  if (!run) return toast("Select a run first", "error");
  try {
    if (action === "continue") {
      const text = await askDialog({
        eyebrow: "Resume run",
        title: "Continue this run",
        body: "Codex resumes from the saved thread and the artifacts already on disk.",
        input: { value: "Continue from the saved state, inspect existing artifacts, and finish the run." },
        confirmLabel: "Resume",
      });
      if (text === null) return;
      state = { ...state, ...(await api.continueRun({ runId: run.run_id, text, model: elements.model.value, effort: elements.effort.value })) };
      renderAll({ preview: false });
    } else if (action === "duplicate") {
      const duplicate = await api.duplicate({ runId: run.run_id });
      selectedRunId = duplicate.run_id;
      await refreshState(true);
      toast("Run duplicated", "success");
    } else if (action === "archive") {
      const agreed = await askDialog({ eyebrow: "Archive", title: "Archive this run?", body: "It stays browsable and recoverable inside the archive.", confirmLabel: "Archive" });
      if (!agreed) return;
      await api.archive({ runId: run.run_id });
      await refreshState(true);
      toast("Run archived", "success");
    } else if (action === "trash") {
      const agreed = await askDialog({ eyebrow: "Delete", title: "Move this run to the Recycle Bin?", body: `The whole run directory for “${run.prompt || run.name}” is moved to the Windows Recycle Bin.`, confirmLabel: "Move to trash", danger: true });
      if (!agreed) return;
      await api.trash({ runId: run.run_id });
      await refreshState(true);
      toast("Run moved to the Recycle Bin", "success");
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

async function artifactAction(action) {
  const run = selectedRun();
  const artifact = selectedArtifact(run);
  if (!run || !artifact) return toast("Select an output first", "error");
  try {
    await api.artifactAction({ runId: run.run_id, path: artifact.path, action });
    toast(action === "copy" ? "Artifact path copied" : `${artifact.name}: ${action}`, "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

function resetForNewRun() {
  selectedRunId = null;
  selectedArtifactPath = null;
  elements.prompt.focus();
  renderAll();
}

/* ── events ─────────────────────────────────────────────────── */

function autoGrowPrompt() {
  elements.prompt.style.height = "20px";
  elements.prompt.style.height = `${Math.min(elements.prompt.scrollHeight, 116)}px`;
}

function toggleSettings(force) {
  const open = force ?? elements.settingsPopover.classList.contains("hidden");
  elements.settingsPopover.classList.toggle("hidden", !open);
  elements.settingsToggle.setAttribute("aria-expanded", String(open));
  if (open) elements.workflow.focus();
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.querySelector(".stage").requestFullscreen();
  } catch (error) {
    toast(error.message, "error");
  }
}

elements.prompt.addEventListener("input", autoGrowPrompt);
elements.prompt.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    startOrSteer();
  }
});
elements.send.addEventListener("click", startOrSteer);
elements.cancel.addEventListener("click", cancelActive);
elements.attach.addEventListener("click", async () => {
  try {
    const picked = await api.pickAttachments();
    attachments = [...new Set([...attachments, ...picked])].slice(0, 12);
    renderAttachments();
  } catch (error) {
    toast(error.message, "error");
  }
});

elements.settingsToggle.addEventListener("click", () => toggleSettings());
document.querySelector("#settings-close").addEventListener("click", () => toggleSettings(false));
document.addEventListener("pointerdown", (event) => {
  if (elements.settingsPopover.classList.contains("hidden")) return;
  if (elements.settingsPopover.contains(event.target) || elements.settingsToggle.contains(event.target)) return;
  toggleSettings(false);
});

document.querySelector("#new-run").addEventListener("click", () => { setPanel("library", true); resetForNewRun(); });
elements.runSearch.addEventListener("input", renderRuns);
document.querySelector("#inspector-close").addEventListener("click", () => setPanel("inspector", false));
elements.libraryToggle.addEventListener("click", () => setPanel("library", !panels.library));
elements.inspectorToggle.addEventListener("click", () => setPanel("inspector", !panels.inspector));
document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === button));
  renderInspector();
}));

document.querySelectorAll("[data-transform]").forEach((button) => button.addEventListener("click", () => setViewportTool("transform", button.dataset.transform)));
document.querySelectorAll("[data-shading]").forEach((button) => button.addEventListener("click", () => setViewportTool("shading", button.dataset.shading)));
document.querySelector('[data-toggle="grid"]').addEventListener("click", () => setViewportTool("grid", !viewportTools.grid));
document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => {
  const action = button.dataset.action;
  if (action === "frame") viewportApi ? viewportApi.frame() : toast("Load a 3D output to frame it");
  else if (action === "capture") captureViewport();
  else if (action === "fullscreen") toggleFullscreen();
}));

document.addEventListener("keydown", (event) => {
  const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
  if (event.key === "Escape") {
    closeMenu();
    toggleSettings(false);
    return;
  }
  if (!(event.ctrlKey || event.metaKey) || event.shiftKey || event.altKey) return;
  const key = event.key.toLowerCase();
  if (key === "k") { event.preventDefault(); elements.prompt.focus(); elements.prompt.select(); }
  else if (key === "b") { event.preventDefault(); setPanel("library", !panels.library); }
  else if (key === "i" && !typing) { event.preventDefault(); setPanel("inspector", !panels.inspector); }
});

addEventListener("resize", updateDockOffset);

function updateStatusTime() {
  elements.statusTime.textContent = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date());
}

/* ── boot ───────────────────────────────────────────────────── */

setPanel("library", panels.library);
setPanel("inspector", panels.inspector);
setViewportTool("transform", viewportTools.transform);
setViewportTool("shading", viewportTools.shading);
setViewportTool("grid", viewportTools.grid);
autoGrowPrompt();
updateStatusTime();
setInterval(updateStatusTime, 30000);
renderAll();

api.onState((next) => { state = { ...state, ...next }; renderAll({ preview: !state.activeJob }); });
api.onEvent(() => scheduleRefresh());
api.onApproval((request) => { approval = request; renderApproval(); });
api.onError((message) => toast(message, "error"));

try {
  state = await api.bootstrap();
  renderAll();
} catch (error) {
  state.appServerError = error.message;
  renderAll();
  toast(error.message, "error");
}
