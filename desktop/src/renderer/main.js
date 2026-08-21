import "./style.css";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
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

app.innerHTML = `
  <header class="command-ribbon">
    <div class="brand" aria-label="Forge3D">
      <svg class="brand-symbol" viewBox="0 0 512 512" aria-hidden="true">
        <defs><linearGradient id="brand-copper" x1=".15" y1=".12" x2=".88" y2=".86"><stop stop-color="#ffd19c"/><stop offset=".42" stop-color="#e8893e"/><stop offset="1" stop-color="#8f371d"/></linearGradient></defs>
        <path d="M132 344C205 425 354 389 412 287c46-80-15-166-102-176-65-8-122 18-160 66l54 37c27-30 65-43 103-33 52 14 72 64 42 104-36 48-114 61-171 21Z" fill="url(#brand-copper)"/>
        <path d="M204 214c27-30 65-43 103-33 31 8 51 29 56 54-33-28-83-34-122-12-19 11-33 27-42 45l-47-20c10-13 28-27 52-34Z" fill="#ffe0b5" opacity=".28"/>
        <g fill="none" stroke="#ee9a55" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"><path d="m132 344-44-44-9-60 20-44 51-19"/><path d="m178 306-27-40 15-37 38-15"/><path d="m88 300 63-34m-72-26 87-11m-67-33 52 70m-52-70 105 18"/></g>
        <g fill="#ffd29f"><circle cx="132" cy="344" r="9"/><circle cx="88" cy="300" r="9"/><circle cx="79" cy="240" r="9"/><circle cx="99" cy="196" r="9"/><circle cx="150" cy="177" r="9"/><circle cx="151" cy="266" r="8"/><circle cx="166" cy="229" r="8"/><circle cx="204" cy="214" r="9"/></g>
      </svg>
      <strong>Forge3D</strong>
    </div>
    <div class="prompt-command">
      <div id="attachments" class="attachment-row"></div>
      <textarea id="prompt" rows="1" aria-label="Forge3D prompt" placeholder="Describe the object, scene, animation, or edit you want…"></textarea>
      <div class="prompt-actions">
        <button id="attach" class="command-button" title="Attach source files" aria-label="Attach source files">＋ <span>Attach</span></button>
        <details id="advanced">
          <summary class="command-button">Controls</summary>
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
        <button id="cancel" class="danger hidden">Cancel</button>
        <button id="send" class="primary">Forge <span>↗</span></button>
      </div>
    </div>
    <div class="ribbon-status">
      <div id="dependency-strip" class="toolchain-state">Checking local toolchain…</div>
      <div id="agent-state" class="agent-state"></div>
    </div>
  </header>
  <main class="spatial-workspace">
    <section class="stage">
      <div id="run-heading" class="run-heading"></div>
      <div id="preview" class="preview"></div>
      <div id="artifact-toolbar" class="artifact-toolbar"></div>
    </section>
    <button id="runs-toggle" class="edge-tab runs-tab" aria-expanded="false" aria-controls="library"><span>Runs</span></button>
    <aside id="library" class="drawer library" aria-hidden="true">
      <div class="drawer-heading"><div><small>RUN LIBRARY</small><h2>History</h2></div><div class="drawer-actions"><button id="new-run" class="icon-button" title="New run">＋</button><button class="icon-button drawer-close" data-close-drawer="library" aria-label="Close run history">×</button></div></div>
      <input id="run-search" class="search" type="search" placeholder="Search prompts, routes, status" />
      <div id="run-list" class="run-list"></div>
    </aside>
    <button id="inspector-toggle" class="edge-tab details-tab" aria-expanded="false" aria-controls="inspector"><span>Details</span></button>
    <aside id="inspector" class="drawer inspector" aria-hidden="true">
      <div class="drawer-heading compact"><div><small>RUN DETAILS</small><h2>Inspector</h2></div><button class="icon-button drawer-close" data-close-drawer="inspector" aria-label="Close inspector">×</button></div>
      <div class="tabs" role="tablist">
        <button class="tab active" data-tab="steps">Steps</button>
        <button class="tab" data-tab="artifacts">Artifacts</button>
        <button class="tab" data-tab="validation">Validation</button>
        <button class="tab" data-tab="logs">Logs</button>
      </div>
      <div id="inspector-content" class="inspector-content"></div>
    </aside>
  </main>
  <section class="production-rail">
    <div class="rail-heading"><span>PRODUCTION</span><small id="rail-context">Waiting for a brief</small></div>
    <div id="production-track" class="production-track"></div>
    <div class="artifact-shelf">
      <span class="shelf-label">OUTPUTS</span>
      <div id="artifact-strip" class="artifact-strip"></div>
    </div>
  </section>
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

function emptyPreview(title, detail) {
  return `<div class="empty-state">
    <svg class="empty-mark" viewBox="0 0 512 512" aria-hidden="true">
      <path d="M132 344C205 425 354 389 412 287c46-80-15-166-102-176-65-8-122 18-160 66l54 37c27-30 65-43 103-33 52 14 72 64 42 104-36 48-114 61-171 21Z"/>
      <g fill="none"><path d="m132 344-44-44-9-60 20-44 51-19"/><path d="m178 306-27-40 15-37 38-15"/><path d="m88 300 63-34m-72-26 87-11m-67-33 52 70m-52-70 105 18"/></g>
    </svg>
    <h2>${escapeHtml(title)}</h2>
    <p>${escapeHtml(detail)}</p>
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
  const label = failed ? "LOCAL AGENT OFFLINE" : missing.length ? "LOCAL TOOLCHAIN NEEDS ATTENTION" : checking ? "CHECKING LOCAL TOOLCHAIN" : "LOCAL TOOLCHAIN READY";
  const tone = failed ? "failed" : missing.length ? "warning" : checking ? "checking" : "ready";
  elements.dependencyStrip.className = `toolchain-state ${tone}`;
  elements.dependencyStrip.innerHTML = `<i></i><span>${escapeHtml(label)}</span>`;
  elements.dependencyStrip.title = missing.length ? `Unavailable: ${missing.join(", ")}` : label;

  const skill = state.skill;
  const needsRepair = skill && skill.state !== "ready";
  const message = failed
    ? state.appServerError
    : needsRepair
      ? (skill.state === "version-mismatch" ? `Plugin ${skill.installedVersion} → ${skill.bundledVersion}` : "Plugin repair available")
      : "";
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
  elements.runList.innerHTML = runs.length ? runs.map((run) => `
    <button class="run-card ${run.run_id === selectedRunId ? "selected" : ""}" data-run-id="${run.run_id}">
      <span class="run-card-top"><strong>${escapeHtml(run.prompt || run.name)}</strong><i class="run-status ${escapeHtml(run.status)}"></i></span>
      <span class="run-meta"><em>${escapeHtml(run.workflow_route || run.command)}</em><span>${escapeHtml(statusLabel(run.status))}</span></span>
      <small>${escapeHtml(formatDate(run.updated_at || run.created_at))}${run.archived ? " · archived" : ""}</small>
    </button>`).join("") : '<div class="empty-list">No matching runs</div>';
  elements.runList.querySelectorAll("[data-run-id]").forEach((button) => button.addEventListener("click", () => selectRun(button.dataset.runId)));
}

function renderRunHeading() {
  const run = selectedRun();
  if (!run) {
    elements.runHeading.innerHTML = '<div class="stage-context"><small>SPATIAL CANVAS</small><h1>Ready for a new asset</h1></div>';
    return;
  }
  const canContinue = !run.archived && !["running", "launching", "cancelling"].includes(run.status) && !state.activeJob;
  elements.runHeading.innerHTML = `
    <div class="stage-context"><small>${escapeHtml(run.workflow_route || run.command)} · ${escapeHtml(statusLabel(run.status))}</small><h1>${escapeHtml(run.prompt || run.name)}</h1></div>
    <div class="run-actions">
      ${canContinue ? '<button data-run-action="continue" class="secondary">Continue</button>' : ""}
      <button data-run-action="duplicate" class="secondary">Duplicate</button>
      ${run.archived ? "" : '<button data-run-action="archive" class="secondary">Archive</button>'}
      <button data-run-action="trash" class="ghost danger-text">Trash</button>
    </div>`;
  elements.runHeading.querySelectorAll("[data-run-action]").forEach((button) => button.addEventListener("click", () => runAction(button.dataset.runAction)));
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
  scene.background = new THREE.Color(0x11100f);
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
    scene.add(new THREE.HemisphereLight(0xf2ddc7, 0x241710, 2.2));
    const key = new THREE.DirectionalLight(0xffc38c, 3.4);
    key.position.set(3, 6, 4);
    scene.add(key, new THREE.GridHelper(12, 24, 0x5a3c2b, 0x241d19));
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
    elements.preview.innerHTML = emptyPreview("Shape the next thing", "Write a prompt above or choose an output from a previous run.");
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
    elements.inspectorContent.innerHTML = '<div class="empty-list">Select a run to inspect its work.</div>';
    return;
  }
  if (tab === "steps") {
    elements.inspectorContent.innerHTML = run.steps?.length ? `<ol class="step-list">${run.steps.map((step) => `<li><i class="step-state ${escapeHtml(step.status)}"></i><div><strong>${escapeHtml(step.name)}</strong><small>${escapeHtml(statusLabel(step.status))}</small></div></li>`).join("")}</ol>` : '<div class="empty-list">Workflow steps will stream here.</div>';
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
  const run = selectedRun();
  const artifacts = run?.artifacts || [];
  const validation = run?.validation && Object.keys(run.validation).length;
  const complete = run?.status === "completed";
  const activeIndex = !run ? 0 : complete ? 3 : validation ? 3 : artifacts.length ? 2 : 1;
  const stages = [
    ["PLAN", run ? (run.workflow_route || run.command || "Auto route") : "Waiting for a brief"],
    ["BUILD", run ? (run.steps?.length ? `${run.steps.length} workflow steps` : statusLabel(run.status)) : "Tool route follows the prompt"],
    ["CHECK", validation ? "Validation available" : run ? "Validation pending" : "Geometry and target checks"],
    ["OUTPUT", artifacts.length ? `${artifacts.length} artifact${artifacts.length === 1 ? "" : "s"}` : "No output yet"],
  ];
  elements.railContext.textContent = run ? statusLabel(run.status) : "Waiting for a brief";
  elements.productionTrack.innerHTML = stages.map(([label, note], index) => {
    const stageState = complete || index < activeIndex ? "complete" : index === activeIndex ? (run?.status === "failed" ? "failed" : "active") : "pending";
    return `<div class="production-node ${stageState}"><i><span>${String(index + 1).padStart(2, "0")}</span></i><div><strong>${label}</strong><small>${escapeHtml(note)}</small></div></div>`;
  }).join("");
  elements.artifactStrip.innerHTML = artifacts.length ? artifacts.map((artifact) => {
    const imageRole = ["primary-image", "image", "animation"].includes(artifact.preview_role);
    const visual = imageRole
      ? `<img src="${artifactUrl(run.run_id, artifact.path)}" alt="" loading="lazy" />`
      : `<span class="artifact-glyph">${artifactGlyph(artifact)}</span>`;
    return `<button class="rail-artifact ${artifact.path === selectedArtifact(run)?.path ? "selected" : ""}" data-rail-artifact="${escapeHtml(artifact.path)}" title="${escapeHtml(artifact.name)}">${visual}<span>${escapeHtml(artifact.name)}</span></button>`;
  }).join("") : '<div class="empty-shelf">Artifacts arrive here as the run works.</div>';
  elements.artifactStrip.querySelectorAll("[data-rail-artifact]").forEach((button) => button.addEventListener("click", () => {
    selectedArtifactPath = button.dataset.railArtifact;
    renderProductionRail();
    renderInspector();
    renderPreview();
  }));
}

function renderAttachments() {
  elements.attachments.innerHTML = attachments.map((item, index) => `<span class="attachment-chip">${escapeHtml(basename(item))}<button data-remove-attachment="${index}" aria-label="Remove attachment">×</button></span>`).join("");
  elements.attachments.querySelectorAll("[data-remove-attachment]").forEach((button) => button.addEventListener("click", () => { attachments.splice(Number(button.dataset.removeAttachment), 1); renderAttachments(); }));
}

function renderComposer() {
  const active = state.activeJob;
  elements.send.innerHTML = active ? 'Steer <span>↗</span>' : 'Forge <span>↗</span>';
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

function setDrawer(name, open) {
  const drawer = document.querySelector(`#${name}`);
  const toggle = document.querySelector(name === "library" ? "#runs-toggle" : "#inspector-toggle");
  if (open) setDrawer(name === "library" ? "inspector" : "library", false);
  drawer.classList.toggle("open", open);
  drawer.setAttribute("aria-hidden", String(!open));
  toggle.classList.toggle("open", open);
  toggle.setAttribute("aria-expanded", String(open));
}

document.querySelector("#attach").addEventListener("click", async () => {
  try {
    const picked = await api.pickAttachments();
    attachments = [...new Set([...attachments, ...picked])].slice(0, 12);
    renderAttachments();
  } catch (error) { toast(error.message, "error"); }
});
document.querySelector("#new-run").addEventListener("click", () => {
  selectedRunId = null;
  selectedArtifactPath = null;
  setDrawer("library", false);
  elements.prompt.focus();
  renderRuns();
  renderRunHeading();
  renderInspector();
  renderProductionRail();
  renderPreview();
});
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