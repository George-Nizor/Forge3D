import "./style.css";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
import brandMark from "./forge3d-mark.png";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";

const api = window.forge3d;
const app = document.querySelector("#app");
let state = { runs: [], tools: {}, models: [], skill: null, activeJob: null };
let selectedRunId = null;
let selectedArtifactPath = null;
let attachments = [];
let approval = null;
let previewDispose = () => {};
let refreshTimer = null;

const glyphs = {
  add: '<path d="M12 5v14M5 12h14"/>',
  attach: '<path d="m21.4 11.6-8.9 8.9a6 6 0 0 1-8.5-8.5l9.6-9.6a4 4 0 0 1 5.7 5.7L9.7 17.7a2 2 0 0 1-2.8-2.8l8.9-8.9"/>',
  box: '<path d="m21 8-9-5-9 5 9 5 9-5Z"/><path d="m3 8 9 5 9-5M3 8v8l9 5 9-5V8M12 13v8"/>',
  camera: '<path d="M14.5 4 16 7h4a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h4l1.5-3h5Z"/><circle cx="12" cy="13" r="3"/>',
  checklist: '<path d="m4 6 2 2 3-4M11 6h9M4 13l2 2 3-4M11 13h9M4 20l2 2 3-4M11 20h9"/>',
  chevron: '<path d="m8 10 4 4 4-4"/>',
  cube: '<path d="m21 8-9-5-9 5 9 5 9-5Z"/><path d="m3 8 9 5 9-5M3 8v8l9 5 9-5V8M12 13v8"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M12 18v-6M9 15h6"/>',
  filter: '<path d="M4 5h16l-6 7v5l-4 2v-7Z"/>',
  fit: '<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>',
  folder: '<path d="M3 6h7l2 2h9v11H3Z"/>',
  fullscreen: '<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/>',
  grid: '<path d="M4 4h16v16H4zM4 10h16M4 16h16M10 4v16M16 4v16"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
  logs: '<path d="M4 4h16v16H4zM8 9l3 3-3 3M13 15h3"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  move: '<path d="M12 2v20M2 12h20M12 2l-3 3M12 2l3 3M22 12l-3-3M22 12l-3 3M12 22l-3-3M12 22l3-3M2 12l3-3M2 12l3 3"/>',
  nodes: '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="19" r="2"/><path d="M7 7.2 10.8 17M17 7.2 13.2 17M7 6h10"/>',
  orbit: '<circle cx="12" cy="12" r="3"/><path d="M3.5 12c0-4.7 3.8-8.5 8.5-8.5 2.2 0 4.2.8 5.7 2.2M20.5 12c0 4.7-3.8 8.5-8.5 8.5-2.2 0-4.2-.8-5.7-2.2M17 2v4h4M7 22v-4H3"/>',
  play: '<path d="m8 5 11 7-11 7Z"/>',
  pointer: '<path d="m5 3 13 9-6 2-3 6Z"/>',
  rotate: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
  save: '<path d="M4 3h14l2 2v16H4Z"/><path d="M8 3v6h8V3M8 21v-8h8v8"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
  sliders: '<path d="M4 6h7M15 6h5M4 12h3M11 12h9M4 18h9M17 18h3"/><circle cx="13" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="15" cy="18" r="2"/>',
  stop: '<rect x="6" y="6" width="12" height="12"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6"/>',
};
function glyph(name, className = "") {
  return `<svg class="ui-icon ${className}" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${glyphs[name]}</svg>`;
}

app.innerHTML = `
  <header class="app-bar">
    <div class="brand" aria-label="Forge3D"><img src="${brandMark}" alt="" /><strong>Forge3D</strong></div>
    <nav class="global-tools" aria-label="Application actions">
      <button id="toolbar-new" class="tool-button" title="New run" aria-label="New run">${glyph("file")}</button>
      <button id="toolbar-reveal" class="tool-button" title="Reveal selected output" aria-label="Reveal selected output">${glyph("folder")}</button>
      <button class="tool-button" title="Runs save automatically" aria-label="Runs save automatically" disabled>${glyph("save")}</button>
      <span class="tool-separator"></span>
      <button id="toolbar-start" class="tool-button" title="Run prompt" aria-label="Run prompt">${glyph("play")}</button>
      <button id="toolbar-stop" class="tool-button" title="Stop active run" aria-label="Stop active run">${glyph("stop")}</button>
      <button id="toolbar-trash" class="tool-button" title="Move selected run to trash" aria-label="Move selected run to trash">${glyph("trash")}</button>
      <span class="tool-separator"></span>
      <button id="toolbar-steps" class="tool-button" title="Show workflow steps" aria-label="Show workflow steps">${glyph("nodes")}</button>
      <button id="toolbar-logs" class="tool-button" title="Show Codex logs" aria-label="Show Codex logs">${glyph("logs")}</button>
    </nav>
    <div class="app-bar-spacer"></div>
    <div id="agent-state" class="agent-state"></div>
    <button id="toolbar-settings" class="tool-button" title="Run settings" aria-label="Run settings">${glyph("settings")}</button>
  </header>

  <main class="workbench">
    <aside id="library" class="pane library" aria-hidden="false">
      <header class="pane-title"><strong>RUNS</strong><span><button class="bare-icon" title="Filter runs" aria-label="Filter runs">${glyph("filter")}</button><button class="bare-icon" title="Run list options" aria-label="Run list options">${glyph("list")}</button></span></header>
      <button id="new-run" class="new-run">${glyph("add")}<span>New Run</span></button>
      <label class="run-search-wrap">${glyph("search")}<input id="run-search" class="search" type="search" placeholder="Search runs" /></label>
      <div id="run-list" class="run-list"></div>
    </aside>

    <section class="viewport-column">
      <header class="viewport-title"><strong>VIEWPORT</strong></header>
      <nav class="viewport-tools" aria-label="Viewport tools">
        <div class="viewport-tool-group">
          <button class="viewport-button active" title="Select" aria-label="Select">${glyph("pointer")}</button>
          <button class="viewport-button" title="Move" aria-label="Move">${glyph("move")}</button>
          <button class="viewport-button" title="Orbit" aria-label="Orbit">${glyph("orbit")}</button>
          <button class="viewport-button" title="Frame selected" aria-label="Frame selected">${glyph("fit")}</button>
          <button class="viewport-button" title="Toggle grid" aria-label="Toggle grid">${glyph("grid")}</button>
        </div>
        <span class="viewport-separator"></span>
        <div class="viewport-tool-group">
          <button class="viewport-button" title="Material preview" aria-label="Material preview"><i class="shade-dot matte"></i></button>
          <button class="viewport-button active" title="Rendered preview" aria-label="Rendered preview"><i class="shade-dot rendered"></i></button>
          <button class="viewport-button" title="Wireframe" aria-label="Wireframe">${glyph("cube")}</button>
        </div>
        <div class="viewport-tool-spacer"></div>
        <div class="viewport-tool-group">
          <button class="viewport-button" title="Capture viewport" aria-label="Capture viewport">${glyph("camera")}</button>
          <button id="viewport-fullscreen" class="viewport-button" title="Fullscreen viewport" aria-label="Fullscreen viewport">${glyph("fullscreen")}</button>
          <button class="viewport-button" title="Viewport settings" aria-label="Viewport settings">${glyph("settings")}</button>
        </div>
      </nav>
      <div class="viewport-stage">
        <div id="run-heading" class="run-heading"></div>
        <div id="preview" class="preview"></div>
        <div id="artifact-toolbar" class="artifact-toolbar"></div>
      </div>
      <section class="composer">
        <div id="attachments" class="attachment-row"></div>
        <div class="composer-row">
          <button id="attach" class="composer-icon" title="Attach source files" aria-label="Attach source files">${glyph("attach")}</button>
          <details id="advanced">
            <summary class="composer-icon" title="Advanced controls" aria-label="Advanced controls">${glyph("sliders")}</summary>
            <div class="advanced-grid">
              <label>Workflow<select id="workflow"><option value="auto">Auto route</option><option value="authored-blender">Authored Blender</option><option value="image-to-mesh">Image to mesh</option><option value="gaussian-splat">Gaussian splat</option><option value="process">Process existing</option><option value="rig">Rig</option><option value="animate">Animate</option><option value="retarget">Retarget</option><option value="validate">Validate</option></select></label>
              <label>Quality<select id="quality"><option value="balanced">Balanced</option><option value="draft">Draft</option><option value="production">Production</option></select></label>
              <label>Target<select id="target"><option value="glb">GLB</option><option value="blend">BLEND</option><option value="splat">SPLAT/PLY</option><option value="gif">GIF / sequence</option></select></label>
              <label>Tool / model<select id="tool"><option value="auto">Auto</option><option value="blender">Blender</option><option value="triposplat">TripoSplat</option><option value="spar3d">SPAR3D</option><option value="tripo-cloud">Tripo cloud</option></select></label>
              <label>Codex model<select id="model"><option value="auto">Codex default</option></select></label>
              <label>Reasoning<select id="effort"><option value="auto">Model default</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="xhigh">Extra high</option></select></label>
              <label class="cloud-consent"><input id="cloud-approved" type="checkbox" /> Allow cloud execution or file upload for this job only</label>
            </div>
          </details>
          <textarea id="prompt" rows="2" aria-label="Forge3D prompt" placeholder="Describe what you want to create or change…"></textarea>
          <button id="cancel" class="run-cancel hidden" title="Cancel run" aria-label="Cancel run">${glyph("stop")}</button>
          <button id="send" class="run-button">${glyph("play")}<span>Run</span></button>
          <button class="run-menu" title="Run options" aria-label="Run options">${glyph("chevron")}</button>
        </div>
      </section>
    </section>

    <aside id="inspector" class="pane inspector" aria-hidden="false">
      <div class="tabs" role="tablist">
        <button class="tab active" data-tab="steps">Steps</button>
        <button class="tab" data-tab="artifacts">Artifacts</button>
        <button class="tab" data-tab="validation">Validation</button>
        <button class="tab" data-tab="logs">Logs</button>
      </div>
      <div id="inspector-content" class="inspector-content"></div>
    </aside>
  </main>

  <footer class="status-bar">
    <div id="dependency-strip" class="dependency-strip"></div>
    <div class="status-spacer"></div>
    <time id="status-time"></time>
    <button class="bare-icon status-message" title="Messages" aria-label="Messages">${glyph("logs")}</button>
  </footer>

  <button id="runs-toggle" class="hidden" aria-controls="library"></button>
  <button id="inspector-toggle" class="hidden" aria-controls="inspector"></button>
  <div id="production-track" hidden></div><div id="artifact-strip" hidden></div><span id="rail-context" hidden></span>
  <div id="approval-layer"></div>
  <div id="toast-layer" aria-live="polite"></div>
`;
const elements = Object.fromEntries([
  "dependency-strip", "agent-state", "run-list", "run-search", "run-heading", "preview", "artifact-toolbar",
  "inspector-content", "attachments", "prompt", "workflow", "quality", "target", "tool", "model", "effort",
  "cloud-approved", "send", "cancel", "approval-layer", "toast-layer", "production-track", "artifact-strip", "rail-context",
].map((id) => [id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), document.querySelector(`#${id}`)]));

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

function selectedRun() {
  return state.runs.find((run) => run.run_id === selectedRunId) || null;
}

function selectedArtifact(run = selectedRun()) {
  if (!run) return null;
  return run.artifacts?.find((artifact) => artifact.path === selectedArtifactPath)
    || run.artifacts?.find((artifact) => artifact.preview_role === "primary-image")
    || run.artifacts?.find((artifact) => ["animation", "image-sequence", "model", "gaussian-splat", "image"].includes(artifact.preview_role))
    || run.artifacts?.[0]
    || null;
}

function emptyPreview() {
  return `<div class="viewport-empty" aria-label="Empty 3D viewport">
    <span class="viewport-cross"></span>
    <span class="axis-widget"><i class="axis-y">Y</i><i class="axis-x">X</i><i class="axis-z">Z</i></span>
  </div>`;
}

function statusLabel(status) {
  return String(status || "unknown").replaceAll("_", " ");
}

function toast(message, kind = "info") {
  const item = document.createElement("div");
  item.className = `toast ${kind}`;
  item.textContent = message;
  elements.toastLayer.append(item);
  setTimeout(() => item.remove(), 4500);
}

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
  const overallLabel = failed ? "Toolchain offline" : missing.length ? "Toolchain attention" : checking ? "Checking toolchain" : "Toolchain ready";
  elements.dependencyStrip.innerHTML = `<span class="status-item ${overall}"><i></i>${overallLabel}</span><span class="status-divider"></span>${tools.map(([name, value]) => `<span class="status-item ${value ? "ready" : value === undefined ? "checking" : "offline"}"><i></i>${name}${name === "Blender" && value ? " 4.5" : name === "Godot" && value ? " 4.4" : ""}</span>`).join("")}`;
  const skill = state.skill;
  const needsRepair = skill && skill.state !== "ready";
  const message = failed ? state.appServerError : needsRepair ? (skill.state === "version-mismatch" ? `Plugin ${skill.installedVersion} → ${skill.bundledVersion}` : "Plugin repair available") : "";
  elements.agentState.classList.toggle("hidden", !message);
  elements.agentState.innerHTML = message ? `${escapeHtml(message)}${needsRepair ? ' <button id="repair-skill" class="link-button">Repair</button>' : ""}` : "";
  document.querySelector("#repair-skill")?.addEventListener("click", repairPlugin);
}

function renderModelOptions() {
  const current = elements.model.value;
  elements.model.innerHTML = '<option value="auto">Codex default</option>' + (state.models || []).map((model) => `<option value="${escapeHtml(model.id || model.model)}">${escapeHtml(model.displayName || model.id || model.model)}</option>`).join("");
  if ([...elements.model.options].some((option) => option.value === current)) elements.model.value = current;
}

function renderRuns() {
  const query = elements.runSearch.value.trim().toLowerCase();
  const runs = state.runs.filter((run) => [run.prompt, run.workflow_route, run.status, run.name].some((value) => String(value || "").toLowerCase().includes(query)));
  const groups = new Map();
  const today = new Date();
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  for (const run of runs) {
    const date = new Date(run.updated_at || run.created_at || Date.now());
    const sameDay = (left, right) => left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth() && left.getDate() === right.getDate();
    const label = sameDay(date, today) ? "Today" : sameDay(date, yesterday) ? "Yesterday" : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: date.getFullYear() === today.getFullYear() ? undefined : "numeric" }).format(date);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push({ run, date });
  }
  elements.runList.innerHTML = groups.size ? [...groups.entries()].map(([label, entries]) => `<section class="run-group"><h3>${escapeHtml(label)}</h3>${entries.map(({ run, date }) => `<button class="run-card ${run.run_id === selectedRunId ? "selected" : ""}" data-run-id="${run.run_id}"><span class="run-glyph">${glyph("cube")}</span><strong>${escapeHtml(run.prompt || run.name)}</strong><time>${escapeHtml(new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date))}</time></button>`).join("")}</section>`).join("") : '<div class="empty-list">No runs</div>';
  elements.runList.querySelectorAll("[data-run-id]").forEach((button) => button.addEventListener("click", () => selectRun(button.dataset.runId)));
}

function renderRunHeading() {
  elements.runHeading.innerHTML = "";
}

function renderArtifactToolbar() {
  const run = selectedRun();
  const artifact = selectedArtifact(run);
  if (!run || !artifact) {
    elements.artifactToolbar.innerHTML = "";
    return;
  }
  elements.artifactToolbar.innerHTML = `
    <div><strong>${escapeHtml(artifact.name)}</strong><small>${escapeHtml(artifact.media_type)} · ${escapeHtml(formatBytes(artifact.size_bytes))}</small></div>
    <div class="toolbar-actions">
      <button data-artifact-action="reveal">Reveal</button><button data-artifact-action="copy">Copy path</button><button data-artifact-action="open">Open</button>
      ${[".blend", ".glb", ".gltf", ".fbx", ".obj"].some((extension) => artifact.path.toLowerCase().endsWith(extension)) ? '<button data-artifact-action="blender">Blender</button>' : ""}
      ${[".glb", ".gltf", ".splat", ".ply", ".sog"].some((extension) => artifact.path.toLowerCase().endsWith(extension)) ? '<button data-artifact-action="godot">Godot review</button>' : ""}
    </div>`;
  elements.artifactToolbar.querySelectorAll("[data-artifact-action]").forEach((button) => button.addEventListener("click", () => artifactAction(button.dataset.artifactAction)));
}

function disposeThree(scene, renderer, animationId, observer) {
  cancelAnimationFrame(animationId.value);
  observer.disconnect();
  scene.traverse((object) => {
    object.geometry?.dispose?.();
    const materials = Array.isArray(object.material) ? object.material : object.material ? [object.material] : [];
    for (const material of materials) {
      for (const value of Object.values(material)) if (value?.isTexture) value.dispose();
      material.dispose?.();
    }
    if (object instanceof SplatMesh) object.dispose();
  });
  renderer.dispose();
}

function threeBase(container, withSpark = false) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b1118);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 1000);
  camera.position.set(2.5, 1.8, 3.2);
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  container.append(renderer.domElement);
  if (withSpark) scene.add(new SparkRenderer({ renderer }));
  else {
    scene.add(new THREE.HemisphereLight(0xd7e1ea, 0x081018, 2.2));
    const key = new THREE.DirectionalLight(0xffa35c, 3.4);
    key.position.set(3, 6, 4);
    scene.add(key, new THREE.GridHelper(12, 24, 0x28404f, 0x15232e));
  }
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  const resize = () => {
    const { width, height } = container.getBoundingClientRect();
    renderer.setSize(Math.max(width, 1), Math.max(height, 1), false);
    camera.aspect = Math.max(width, 1) / Math.max(height, 1);
    camera.updateProjectionMatrix();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(container);
  resize();
  return { scene, camera, renderer, controls, observer };
}

function frameObject(object, camera, controls) {
  const box = new THREE.Box3().setFromObject(object);
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
    status.textContent = gltf.animations.length ? `${gltf.animations.length} animation clip${gltf.animations.length === 1 ? "" : "s"} · first clip playing` : "Drag to orbit · scroll to zoom";
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
    status.textContent = `${splat.numSplats.toLocaleString()} splats · drag to orbit`;
  } catch (error) {
    status.textContent = `Could not load splat: ${error.message}`;
  }
  return () => disposeThree(base.scene, base.renderer, animationId, base.observer);
}

async function renderPreview() {
  previewDispose();
  previewDispose = () => {};
  const run = selectedRun();
  const artifact = selectedArtifact(run);
  if (!run || !artifact) {
    elements.preview.innerHTML = emptyPreview();
    return;
  }
  selectedArtifactPath = artifact.path;
  elements.preview.innerHTML = "";
  const role = artifact.preview_role;
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
  } else if (role === "model") previewDispose = await renderModel(elements.preview, run, artifact);
  else if (role === "gaussian-splat") previewDispose = await renderSplat(elements.preview, run, artifact);
  else if (["validation", "text"].includes(role)) {
    const pre = document.createElement("pre");
    pre.className = "text-preview";
    pre.textContent = "Loading…";
    elements.preview.append(pre);
    try {
      const response = await fetch(artifactUrl(run.run_id, artifact.path));
      const text = await response.text();
      if (artifact.media_type === "application/json") pre.textContent = JSON.stringify(JSON.parse(text), null, 2);
      else pre.textContent = text;
    } catch (error) {
      pre.textContent = `Could not load ${artifact.name}: ${error.message}`;
    }
  } else {
    elements.preview.innerHTML = `<div class="empty-state"><span>□</span><h2>${escapeHtml(artifact.name)}</h2><p>${escapeHtml(artifact.media_type)} · ${escapeHtml(formatBytes(artifact.size_bytes))}</p><p>This file has no embedded preview. Use Open or Reveal below.</p></div>`;
  }
  renderArtifactToolbar();
}

function activeTab() {
  return document.querySelector(".tab.active")?.dataset.tab || "steps";
}

function renderInspector() {
  const run = selectedRun();
  const tab = activeTab();
  if (!run) {
    elements.inspectorContent.innerHTML = `<div class="inspector-empty">${glyph("checklist")}<span>Select a run to inspect its steps.</span></div>`;
    return;
  }
  if (tab === "steps") {
    elements.inspectorContent.innerHTML = run.steps?.length ? `<ol class="step-list">${run.steps.map((step) => `<li><i class="step-state ${escapeHtml(step.status)}"></i><div><strong>${escapeHtml(step.name)}</strong><small>${escapeHtml(statusLabel(step.status))}</small></div></li>`).join("")}</ol>` : `<div class="inspector-empty">${glyph("nodes")}<span>Steps appear when the run starts.</span></div>`;
  } else if (tab === "artifacts") {
    elements.inspectorContent.innerHTML = run.artifacts?.length ? `<div class="artifact-list">${run.artifacts.map((artifact) => `<button class="artifact-card ${artifact.path === selectedArtifactPath ? "selected" : ""}" data-artifact-path="${escapeHtml(artifact.path)}"><span class="artifact-icon">${artifact.preview_role === "model" ? "3D" : artifact.preview_role === "gaussian-splat" ? "✦" : artifact.preview_role.includes("image") || artifact.preview_role === "animation" ? "▧" : "≡"}</span><span><strong>${escapeHtml(artifact.name)}</strong><small>${escapeHtml(artifact.preview_role)} · ${escapeHtml(formatBytes(artifact.size_bytes))}</small></span></button>`).join("")}</div>` : '<div class="empty-list">Artifacts are discovered inside this run only.</div>';
    elements.inspectorContent.querySelectorAll("[data-artifact-path]").forEach((button) => button.addEventListener("click", () => { selectedArtifactPath = button.dataset.artifactPath; renderInspector(); renderProductionRail(); renderPreview(); }));
  } else if (tab === "validation") {
    const validation = run.validation && Object.keys(run.validation).length ? run.validation : null;
    const reports = (run.artifacts || []).filter((artifact) => artifact.preview_role === "validation");
    elements.inspectorContent.innerHTML = `${validation ? `<pre class="mini-log">${escapeHtml(JSON.stringify(validation, null, 2))}</pre>` : '<div class="empty-list">No inline validation result yet.</div>'}${reports.map((report) => `<button class="report-link" data-artifact-path="${escapeHtml(report.path)}">${escapeHtml(report.name)}</button>`).join("")}`;
    elements.inspectorContent.querySelectorAll("[data-artifact-path]").forEach((button) => button.addEventListener("click", () => { selectedArtifactPath = button.dataset.artifactPath; renderProductionRail(); renderPreview(); }));
  } else {
    const entries = run.transcript || [];
    elements.inspectorContent.innerHTML = entries.length ? `<div class="log-list">${entries.slice(-500).map((entry) => `<article class="log-entry ${escapeHtml(entry.kind)}"><small>${escapeHtml(entry.kind)} · ${escapeHtml(formatDate(entry.at))}</small><pre>${escapeHtml(entry.text || entry.method || JSON.stringify(entry.params || {}))}</pre></article>`).join("")}</div>` : '<div class="empty-list">Codex transcript and tool logs will stream here.</div>';
    elements.inspectorContent.scrollTop = elements.inspectorContent.scrollHeight;
  }
}

function artifactGlyph(artifact) {
  if (artifact.preview_role === "model") return "3D";
  if (artifact.preview_role === "gaussian-splat") return "✦";
  if (artifact.preview_role === "validation") return "✓";
  if (String(artifact.preview_role).includes("image") || artifact.preview_role === "animation") return "▧";
  return "≡";
}

function renderProductionRail() {
  // UI A routes artifacts through the inspector and viewport toolbar only.
}

function renderAttachments() {
  elements.attachments.innerHTML = attachments.map((item, index) => `<span class="attachment-chip">${escapeHtml(basename(item))}<button data-remove-attachment="${index}" aria-label="Remove attachment">×</button></span>`).join("");
  elements.attachments.querySelectorAll("[data-remove-attachment]").forEach((button) => button.addEventListener("click", () => { attachments.splice(Number(button.dataset.removeAttachment), 1); renderAttachments(); }));
}

function renderComposer() {
  const active = state.activeJob;
  elements.send.innerHTML = active ? `${glyph("nodes")}<span>Steer</span>` : `${glyph("play")}<span>Run</span>`;
  elements.cancel.classList.toggle("hidden", !active);
  elements.cloudApproved.disabled = Boolean(active);
}

function renderApproval() {
  if (!approval) {
    elements.approvalLayer.innerHTML = "";
    return;
  }
  const params = approval.params || {};
  const network = params.networkApprovalContext;
  const title = network ? `Network access to ${network.host || "external host"}` : approval.method.includes("fileChange") ? "Approve file changes" : "Approve command";
  const detail = network ? `${network.protocol || "network"} access${network.port ? ` on port ${network.port}` : ""}` : params.command || params.reason || JSON.stringify(params, null, 2);
  elements.approvalLayer.innerHTML = `<div class="modal-backdrop"><section class="approval-modal"><small>CODEX APPROVAL</small><h2>${escapeHtml(title)}</h2><p>${escapeHtml(params.reason || "Forge3D needs your decision before continuing.")}</p><pre>${escapeHtml(detail)}</pre><div class="approval-actions"><button data-decision="cancel" class="ghost">Cancel job action</button><button data-decision="decline" class="secondary">Deny</button><button data-decision="acceptForSession" class="secondary">Approve for session</button><button data-decision="accept" class="primary">Approve once</button></div></section></div>`;
  elements.approvalLayer.querySelectorAll("[data-decision]").forEach((button) => button.addEventListener("click", () => decideApproval(button.dataset.decision)));
}

function renderAll({ preview = true } = {}) {
  if (!selectedRunId && state.runs.length) selectedRunId = state.runs[0].run_id;
  if (selectedRunId && !state.runs.some((run) => run.run_id === selectedRunId)) selectedRunId = state.runs[0]?.run_id || null;
  renderDependencies();
  renderModelOptions();
  renderRuns();
  renderRunHeading();
  renderInspector();
  renderProductionRail();
  renderComposer();
  renderApproval();
  if (preview) renderPreview();
}

function selectRun(runId) {
  selectedRunId = runId;
  selectedArtifactPath = null;
  setDrawer("library", false);
  renderAll();
}

async function refreshState(preview = false) {
  try {
    const refreshed = await api.refreshTools();
    state = { ...state, ...refreshed };
    renderAll({ preview });
  } catch (error) {
    toast(error.message, "error");
  }
}

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => refreshState(false), 350);
}

async function startOrSteer() {
  const text = elements.prompt.value.trim();
  if (!text) return toast("Write a prompt first", "error");
  elements.send.disabled = true;
  try {
    if (state.activeJob) {
      await api.steer({ runId: state.activeJob.runId, text });
      elements.prompt.value = "";
      toast("Steering note sent");
    } else {
      const cloudApproved = elements.cloudApproved.checked;
      if (cloudApproved && !confirm("Approve cloud execution or file upload for this single job? Forge3D will still show provider or command approvals when required.")) return;
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
  if (!state.activeJob) return;
  try {
    state = { ...state, ...(await api.cancel({ runId: state.activeJob.runId })) };
    renderAll({ preview: false });
  } catch (error) { toast(error.message, "error"); }
}

async function decideApproval(decision) {
  try {
    await api.answerApproval({ requestId: approval.requestId, decision });
    approval = null;
    renderApproval();
  } catch (error) { toast(error.message, "error"); }
}

async function repairPlugin() {
  if (!confirm("Repair the personal Forge3D Codex plugin from this application bundle? The current plugin directory will be preserved as a timestamped backup.")) return;
  try {
    const result = await api.repairPlugin();
    state.skill = result.skill;
    renderDependencies();
    toast(`Forge3D plugin ${result.version} is ready`);
  } catch (error) { toast(error.message, "error"); }
}

async function runAction(action) {
  const run = selectedRun();
  if (!run) return;
  try {
    if (action === "continue") {
      const text = prompt("Steer the recovered run, or leave the default continuation request:", "Continue from the saved state, inspect existing artifacts, and finish the run.");
      if (text === null) return;
      state = { ...state, ...(await api.continueRun({ runId: run.run_id, text, model: elements.model.value, effort: elements.effort.value })) };
    } else if (action === "duplicate") {
      const duplicate = await api.duplicate({ runId: run.run_id });
      selectedRunId = duplicate.run_id;
      await refreshState(true);
    } else if (action === "archive") {
      if (!confirm("Archive this run? It remains browsable and recoverable.")) return;
      await api.archive({ runId: run.run_id });
      await refreshState(true);
    } else if (action === "trash") {
      if (!confirm("Move this run directory to the Windows Recycle Bin?")) return;
      await api.trash({ runId: run.run_id });
      await refreshState(true);
    }
  } catch (error) { toast(error.message, "error"); }
}

async function artifactAction(action) {
  const run = selectedRun();
  const artifact = selectedArtifact(run);
  if (!run || !artifact) return;
  try {
    await api.artifactAction({ runId: run.run_id, path: artifact.path, action });
    toast(action === "copy" ? "Artifact path copied" : `${artifact.name}: ${action}`);
  } catch (error) { toast(error.message, "error"); }
}

function setDrawer() {
  document.querySelector("#library")?.setAttribute("aria-hidden", "false");
  document.querySelector("#inspector")?.setAttribute("aria-hidden", "false");
}

function activateInspectorTab(name) {
  const target = document.querySelector(`.tab[data-tab="${name}"]`);
  if (!target) return;
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === target));
  renderInspector();
}

function resetForNewRun() {
  selectedRunId = null;
  selectedArtifactPath = null;
  elements.prompt.focus();
  renderRuns();
  renderRunHeading();
  renderInspector();
  renderProductionRail();
  renderPreview();
}

document.querySelector("#toolbar-new").addEventListener("click", resetForNewRun);
document.querySelector("#toolbar-reveal").addEventListener("click", () => selectedArtifact() ? artifactAction("reveal") : toast("Select an output first"));
document.querySelector("#toolbar-start").addEventListener("click", startOrSteer);
document.querySelector("#toolbar-stop").addEventListener("click", cancelActive);
document.querySelector("#toolbar-trash").addEventListener("click", () => selectedRun() ? runAction("trash") : toast("Select a run first"));
document.querySelector("#toolbar-steps").addEventListener("click", () => activateInspectorTab("steps"));
document.querySelector("#toolbar-logs").addEventListener("click", () => activateInspectorTab("logs"));
document.querySelector("#toolbar-settings").addEventListener("click", () => document.querySelector("#advanced").toggleAttribute("open"));
document.querySelector("#viewport-fullscreen").addEventListener("click", async () => {
  try { if (document.fullscreenElement) await document.exitFullscreen(); else await document.querySelector(".viewport-stage").requestFullscreen(); }
  catch (error) { toast(error.message, "error"); }
});
document.querySelectorAll(".viewport-button").forEach((button) => button.addEventListener("click", () => {
  if (button.id === "viewport-fullscreen") return;
  const group = button.closest(".viewport-tool-group");
  group?.querySelectorAll(".viewport-button").forEach((item) => item.classList.toggle("active", item === button));
}));

function updateStatusTime() {
  const target = document.querySelector("#status-time");
  if (target) target.textContent = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date());
}
updateStatusTime();
setInterval(updateStatusTime, 30000);
document.querySelector("#attach").addEventListener("click", async () => {
  try {
    const picked = await api.pickAttachments();
    attachments = [...new Set([...attachments, ...picked])].slice(0, 12);
    renderAttachments();
  } catch (error) { toast(error.message, "error"); }
});
document.querySelector("#new-run").addEventListener("click", resetForNewRun);

document.querySelector("#runs-toggle").addEventListener("click", () => setDrawer("library", !document.querySelector("#library").classList.contains("open")));
document.querySelector("#inspector-toggle").addEventListener("click", () => setDrawer("inspector", !document.querySelector("#inspector").classList.contains("open")));
document.querySelectorAll("[data-close-drawer]").forEach((button) => button.addEventListener("click", () => setDrawer(button.dataset.closeDrawer, false)));
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  setDrawer("library", false);
  setDrawer("inspector", false);
  document.querySelector("#advanced").removeAttribute("open");
});
elements.runSearch.addEventListener("input", renderRuns);
elements.send.addEventListener("click", startOrSteer);
elements.cancel.addEventListener("click", cancelActive);
elements.prompt.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") startOrSteer(); });
document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === button));
  renderInspector();
}));

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