"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { spawn } = require("node:child_process");
const {
  app,
  BrowserWindow,
  clipboard,
  dialog,
  ipcMain,
  net,
  protocol,
  session,
  shell,
} = require("electron");

const TITLE_BAR_HEIGHT = 72;
const { CodexAppServerClient } = require("./lib/codex-client.cjs");
const { RunStore } = require("./lib/run-store.cjs");
const {
  BUNDLE_VERSION,
  detectExternalTools,
  ensureRuntimeState,
  findCodexExecutable,
  inspectForgeSkill,
  primeGodotProject,
  repairForgePlugin,
} = require("./lib/runtime.cjs");
const { resolveContained } = require("./lib/path-policy.cjs");
const { automaticApproval } = require("./lib/approval-policy.cjs");

protocol.registerSchemesAsPrivileged([
  {
    scheme: "forge3d-artifact",
    privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true },
  },
]);

let mainWindow = null;
let runStore = null;
let runtimeState = null;
let codexClient = null;
let currentSkill = null;
let activeJob = null;
let appServerError = null;
let detectedTools = null;
let runEventTimer = null;
let godotPrimePromise = Promise.resolve();
const pendingRunEvents = new Map();
const VISIBLE_ITEM_TYPES = new Set(["commandExecution", "mcpToolCall", "fileChange", "dynamicToolCall", "imageGeneration", "webSearch"]);
const APPROVAL_METHODS = new Set([
  "item/commandExecution/requestApproval",
  "item/fileChange/requestApproval",
  "mcpServer/elicitation/request",
]);

const repoRoot = path.resolve(__dirname, "..", "..");
const bundledPlugin = () => app.isPackaged
  ? path.join(process.resourcesPath, "forge3d-plugin")
  : path.join(repoRoot, "plugins", "forge3d");
const bundledToolkit = () => app.isPackaged
  ? path.join(process.resourcesPath, "forge3d-toolkit")
  : repoRoot;

function rendererUrlAllowed(url) {
  if (url.startsWith("file://")) return true;
  const dev = process.env.FORGE3D_DEV_SERVER_URL;
  return Boolean(dev && url.startsWith(dev));
}

function assertTrustedIpc(event) {
  const url = event.senderFrame?.url || event.sender?.getURL?.() || "";
  if (!rendererUrlAllowed(url)) throw new Error("Blocked IPC from an untrusted renderer");
}

function handle(channel, callback) {
  ipcMain.handle(channel, async (event, payload) => {
    assertTrustedIpc(event);
    return callback(payload, event);
  });
}

function send(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send(channel, payload);
}

function compact(value, depth = 0) {
  if (depth > 6) return "[nested data omitted]";
  if (typeof value === "string") return value.length > 20000 ? `${value.slice(0, 20000)}…` : value;
  if (Array.isArray(value)) return value.slice(0, 100).map((item) => compact(item, depth + 1));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).slice(0, 100).map(([key, item]) => [key, compact(item, depth + 1)]));
  }
  return value;
}

function externalTools(force = false) {
  if (force || !detectedTools) detectedTools = detectExternalTools(runtimeState.root);
  return detectedTools;
}

function currentState() {
  return {
    version: BUNDLE_VERSION,
    activeJob,
    appServerError,
    skill: currentSkill,
    tools: externalTools(),
    runs: runStore.list(),
  };
}

function sendState() {
  send("forge3d:state", currentState());
}

function queueRunEvent(runId, event) {
  const queued = pendingRunEvents.get(runId) || [];
  queued.push(event);
  pendingRunEvents.set(runId, queued);
  if (!runEventTimer) runEventTimer = setTimeout(flushRunEvents, 220);
}

function flushRunEvents() {
  if (runEventTimer) clearTimeout(runEventTimer);
  runEventTimer = null;
  let count = 0;
  for (const [runId, events] of pendingRunEvents) {
    pendingRunEvents.delete(runId);
    if (!events.length) continue;
    runStore.appendEvents(runId, events);
    count += events.length;
  }
  if (count) send("forge3d:event", { refresh: true, count });
}

function failActiveJob(error) {
  const message = `Forge3D could not process Codex activity: ${error.message}`;
  appServerError = message;
  send("forge3d:error", message);
  try { flushRunEvents(); } catch {}
  if (activeJob) {
    try { runStore.setStatus(activeJob.runId, "failed", message); } catch {}
    activeJob = null;
  }
  try { sendState(); } catch {}
}

async function ensureCodex() {
  if (codexClient?.started) return codexClient;
  const executable = findCodexExecutable();
  const binDirectory = app.isPackaged ? path.join(process.resourcesPath, "bin") : path.join(repoRoot, ".venv", "Scripts");
  const env = {
    ...process.env,
    PATH: `${binDirectory}${path.delimiter}${process.env.PATH || ""}`,
    FORGE3D_OUTPUT: runStore.root,
    FORGE3D_TOOLKIT_ROOT: bundledToolkit(),
    FORGE3D_PLUGIN_ROOT: bundledPlugin(),
    FORGE3D_STATE_ROOT: runtimeState.root,
  };
  codexClient = new CodexAppServerClient({ command: executable, cwd: runStore.root, env });
  codexClient.on("notification", (message) => {
    try { onCodexNotification(message); } catch (error) { failActiveJob(error); }
  });
  codexClient.on("request", (message) => {
    try { onCodexRequest(message); } catch (error) { failActiveJob(error); }
  });
  codexClient.on("protocolError", (error) => send("forge3d:error", error.message));
  codexClient.on("stderr", (text) => {
    if (activeJob) queueRunEvent(activeJob.runId, { kind: "app-server-stderr", text: String(text).slice(-4000) });
  });
  codexClient.on("exit", ({ detail }) => {
    try { flushRunEvents(); } catch {}
    appServerError = detail || "Codex App Server stopped unexpectedly";
    if (activeJob) {
      runStore.setStatus(activeJob.runId, "failed", appServerError);
      activeJob = null;
    }
    sendState();
  });
  try {
    await codexClient.start();
    appServerError = null;
  } catch (error) {
    appServerError = error.message;
    codexClient = null;
    throw error;
  }
  return codexClient;
}

async function refreshSkill(forceReload = false) {
  const client = await ensureCodex();
  const skills = await client.listSkills(runStore.root, forceReload);
  const installed = skills.find((skill) => skill.name === "forge3d" && skill.enabled !== false) || null;
  currentSkill = inspectForgeSkill(installed);
  if (!installed) {
    const fallback = path.join(bundledPlugin(), "skills", "forge3d", "SKILL.md");
    currentSkill = { ...currentSkill, path: fallback, state: "missing", usingBundledFallback: true };
  }
  return currentSkill;
}

function promptWithPolicy(manifest) {
  const attachments = (manifest.inputs || []).map((item) => item.path).join(", ") || "none";
  const cloud = manifest.settings?.cloud_approved
    ? `Cloud execution or upload is approved for this job only, and only for these copied run attachments: ${attachments}. Still request approval before any charged provider action.`
    : "Cloud execution and uploading user files are not approved for this job. Use local workflows only.";
  return [
    manifest.prompt,
    "Work only inside this Forge3D run directory. Never overwrite an existing artifact; create a numbered version.",
    cloud,
    `Workflow: ${manifest.workflow_route}; quality: ${manifest.settings?.quality}; target: ${manifest.settings?.target_format}; tool/model: ${manifest.settings?.tool}.`,
    "The desktop host has already completed startup diagnostics and selected the requested route. Start production immediately. Do not rerun forge3d doctor, inspect CLI help, reinstall or search for tools, inspect plugin source, or launch review applications unless the first concrete production command fails.",
    "Use the leanest complete route: one authored build pass and at most one targeted correction. For splat targets, generate one clean reference, run local TripoSplat once, preserve its PLY and SPLAT outputs, make only the minimum proxy needed for interaction, and do not investigate optional KIRI or Godot review integrations. Do not perform redundant screenshots, orbit renders, or validation passes.",
    "The Forge3D host exclusively owns run.json. Do not create, edit, replace, rename, or delete it. Write validation evidence to separate files and return artifact paths relative to this run directory.",
  ].join("\n\n");
}

async function beginRun(manifest, { model = "auto", effort = "auto", continuation = null } = {}) {
  if (activeJob) throw new Error("Forge3D already has an active job");
  const client = await ensureCodex();
  if (!currentSkill) await refreshSkill(false);
  const directory = runStore.runDirectory(manifest.run_id);
  runStore.setStatus(manifest.run_id, "launching");
  activeJob = { runId: manifest.run_id, threadId: null, turnId: null };
  sendState();
  try {
    let thread;
    if (manifest.codex?.thread_id) thread = await client.resumeThread(manifest.codex.thread_id);
    else thread = await client.startThread({ cwd: directory, model });
    const copiedImages = (manifest.inputs || [])
      .filter((item) => String(item.media_type || "").startsWith("image/"))
      .map((item) => resolveContained(directory, item.path));
    const turn = await client.startTurn({
      threadId: thread.id,
      prompt: continuation || promptWithPolicy(manifest),
      cwd: directory,
      skill: currentSkill,
      images: continuation ? [] : copiedImages,
      model,
      effort,
      allowNetwork: Boolean(manifest.settings?.cloud_approved),
    });
    activeJob = { runId: manifest.run_id, threadId: thread.id, turnId: turn.id };
    runStore.setCodex(manifest.run_id, thread.id, turn.id);
    runStore.setStatus(manifest.run_id, "running");
    runStore.appendEvent(manifest.run_id, { kind: "user", text: continuation || manifest.prompt });
    sendState();
    return currentState();
  } catch (error) {
    runStore.setStatus(manifest.run_id, "failed", error.message);
    activeJob = null;
    sendState();
    throw error;
  }
}

function onCodexRequest(message) {
  const params = message.params || {};
  const supported = APPROVAL_METHODS.has(message.method);
  if (!supported) {
    codexClient.reject(message.id, `Forge3D does not support App Server request ${message.method}`);
    if (activeJob) queueRunEvent(activeJob.runId, { kind: "error", method: message.method, text: "Unsupported App Server request was rejected safely." });
    return;
  }
  if (!activeJob || params.threadId !== activeJob.threadId || (params.turnId && params.turnId !== activeJob.turnId)) {
    codexClient.decide(message.id, "cancel");
    return;
  }
  const automatic = automaticApproval(message, runStore.runDirectory(activeJob.runId));
  if (automatic) {
    codexClient.decide(message.id, automatic.decision);
    queueRunEvent(activeJob.runId, {
      kind: "approval-decision",
      requestId: message.id,
      method: message.method,
      decision: automatic.decision,
      text: automatic.label,
    });
    return;
  }
  queueRunEvent(activeJob.runId, { kind: "approval-request", requestId: message.id, method: message.method, params: compact(params) });
  send("forge3d:approval", { requestId: message.id, method: message.method, params: compact(params) });
  sendState();
}

function describeItem(item) {
  if (Array.isArray(item.command)) return item.command.join(" ");
  if (typeof item.command === "string") return item.command;
  if (item.type === "mcpToolCall") return [item.server, item.tool].filter(Boolean).join(" · ") || "MCP tool";
  if (item.type === "fileChange") return `${item.changes?.length || 0} file change${item.changes?.length === 1 ? "" : "s"}`;
  return item.name || item.type || "Work";
}

function updateSteps(runId, method, params) {
  const item = params.item;
  if (!item?.id || !VISIBLE_ITEM_TYPES.has(item.type)) return false;
  runStore.update(runId, (manifest) => {
    manifest.steps ||= [];
    let step = manifest.steps.find((candidate) => candidate.item_id === item.id);
    if (!step) {
      step = { item_id: item.id, name: item.type || "work", status: "running", started_at: new Date().toISOString() };
      manifest.steps.push(step);
    }
    step.status = method === "item/completed" ? (item.status || "completed") : (item.status || "running");
    step.detail = describeItem(item).slice(0, 500);
    if (method === "item/completed") step.completed_at = new Date().toISOString();
  });
  return true;
}

function onCodexNotification(message) {
  if (!activeJob) return;
  const params = message.params || {};
  const scopedThread = params.threadId || params.thread?.id;
  if (scopedThread && scopedThread !== activeJob.threadId) return;

  const itemLifecycle = message.method === "item/started" || message.method === "item/completed";
  const visibleItem = itemLifecycle && updateSteps(activeJob.runId, message.method, params);
  const delta = params.delta;
  if (typeof delta === "string") {
    if (message.method.includes("agentMessage")) {
      queueRunEvent(activeJob.runId, { kind: "agent", method: message.method, text: delta.slice(0, 20000) });
    } else if (message.method.includes("outputDelta")) {
      queueRunEvent(activeJob.runId, { kind: "log", method: message.method, text: delta.slice(0, 20000) });
    }
  } else if (visibleItem) {
    queueRunEvent(activeJob.runId, { kind: "activity", method: message.method, text: describeItem(params.item) });
  } else if (message.method === "turn/started" || message.method === "turn/completed") {
    queueRunEvent(activeJob.runId, { kind: "event", method: message.method, text: message.method === "turn/started" ? "Codex turn started." : "Codex turn finished." });
  }

  if (message.method === "turn/completed") {
    flushRunEvents();
    const turn = params.turn || {};
    const rawStatus = turn.status || "failed";
    const status = rawStatus === "completed" ? "completed" : rawStatus === "interrupted" ? "interrupted" : "failed";
    const failure = turn.error?.message || (status === "failed" ? "The Codex turn failed" : null);
    runStore.setStatus(activeJob.runId, status, failure);
    runStore.refreshArtifacts(activeJob.runId);
    activeJob = null;
    sendState();
  }
}

// The renderer paints its own application bar, so on Windows the native caption is
// hidden and only the system window controls are drawn over the reserved inset.
function titleBarOptions() {
  if (process.platform !== "win32") return {};
  return {
    titleBarStyle: "hidden",
    titleBarOverlay: { color: "#0f1013", symbolColor: "#9aa1aa", height: TITLE_BAR_HEIGHT },
  };
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1540,
    height: 980,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#0a0a0c",
    title: "Forge3D",
    show: false,
    ...titleBarOptions(),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
      spellcheck: true,
    },
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!rendererUrlAllowed(url)) event.preventDefault();
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());
  const dev = process.env.FORGE3D_DEV_SERVER_URL;
  if (dev) mainWindow.loadURL(dev);
  else mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
}

function registerIpc() {
  handle("forge3d:bootstrap", async () => {
    try {
      await refreshSkill(false);
    } catch (error) {
      appServerError = error.message;
    }
    let models = [];
    if (codexClient?.started) {
      try {
        const result = await codexClient.request("model/list", { limit: 50, includeHidden: false });
        models = result?.data || [];
      } catch {}
    }
    return { ...currentState(), models };
  });

  handle("forge3d:pick-attachments", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "Add Forge3D attachments",
      properties: ["openFile", "multiSelections"],
      filters: [
        { name: "Forge3D inputs", extensions: ["png", "jpg", "jpeg", "webp", "gif", "glb", "gltf", "blend", "fbx", "obj", "ply", "splat", "sog", "spz", "ksplat", "json", "txt", "md"] },
        { name: "All files", extensions: ["*"] },
      ],
    });
    return result.canceled ? [] : result.filePaths.slice(0, 12);
  });

  handle("forge3d:start-run", async (payload = {}) => {
    const manifest = await runStore.create(payload);
    return beginRun(manifest, payload);
  });

  handle("forge3d:continue-run", async (payload = {}) => {
    const loaded = runStore.find(payload.runId, false).manifest;
    const text = typeof payload.text === "string" && payload.text.trim() ? payload.text.trim() : "Continue this Forge3D run from its saved state, verify existing artifacts, and finish the requested result.";
    return beginRun(loaded, { ...payload, continuation: text });
  });

  handle("forge3d:steer", async (payload = {}) => {
    if (!activeJob || payload.runId !== activeJob.runId) throw new Error("This run is not active");
    if (typeof payload.text !== "string" || !payload.text.trim()) throw new Error("Steering text is required");
    await codexClient.steer(activeJob.threadId, activeJob.turnId, payload.text.trim());
    runStore.appendEvent(activeJob.runId, { kind: "user-steer", text: payload.text.trim() });
    return currentState();
  });

  handle("forge3d:cancel", async (payload = {}) => {
    if (!activeJob || payload.runId !== activeJob.runId) throw new Error("This run is not active");
    runStore.setStatus(activeJob.runId, "cancelling");
    await codexClient.interrupt(activeJob.threadId, activeJob.turnId);
    sendState();
    return currentState();
  });

  handle("forge3d:approval", async (payload = {}) => {
    if (!activeJob) throw new Error("No active job is awaiting approval");
    codexClient.decide(payload.requestId, payload.decision);
    runStore.appendEvent(activeJob.runId, { kind: "approval-decision", requestId: payload.requestId, decision: payload.decision });
    return currentState();
  });

  handle("forge3d:duplicate", async (payload = {}) => runStore.duplicate(payload.runId));
  handle("forge3d:archive", async (payload = {}) => {
    if (activeJob?.runId === payload.runId) throw new Error("Cancel the active job before archiving it");
    return runStore.archive(payload.runId);
  });
  handle("forge3d:trash", async (payload = {}) => {
    if (activeJob?.runId === payload.runId) throw new Error("Cancel the active job before moving it to trash");
    const directory = runStore.runDirectory(payload.runId);
    await shell.trashItem(directory);
    sendState();
    return { recoverable: true };
  });

  handle("forge3d:artifact-action", async (payload = {}) => {
    const absolute = runStore.resolveArtifact(payload.runId, payload.path);
    if (payload.action === "reveal") shell.showItemInFolder(absolute);
    else if (payload.action === "copy") clipboard.writeText(absolute);
    else if (payload.action === "open") {
      const error = await shell.openPath(absolute);
      if (error) throw new Error(error);
    } else if (payload.action === "blender") {
      const blender = externalTools(true).blender;
      if (!blender) throw new Error("Blender was not detected");
      spawn(blender, [absolute], { detached: true, windowsHide: true, stdio: "ignore" }).unref();
    } else if (payload.action === "godot") {
      await godotPrimePromise;
      const godot = externalTools(true).godot;
      if (!godot) throw new Error("Godot was not detected");
      const reviewRoot = resolveContained(runtimeState.godot, "imports");
      const destinationRoot = resolveContained(reviewRoot, payload.runId);
      fs.mkdirSync(destinationRoot, { recursive: true });
      const destination = resolveContained(destinationRoot, path.basename(absolute));
      fs.copyFileSync(absolute, destination);
      spawn(godot, ["--editor", "--path", runtimeState.godot], { detached: true, windowsHide: true, stdio: "ignore" }).unref();
    } else throw new Error("Unsupported artifact action");
    return { path: absolute };
  });

  handle("forge3d:repair-plugin", async () => {
    const result = repairForgePlugin({ bundledPlugin: bundledPlugin(), runtimeState });
    await refreshSkill(true);
    sendState();
    return { ...result, skill: currentSkill };
  });
  handle("forge3d:refresh-tools", async (payload = {}) => {
    if (payload.force) externalTools(true);
    return currentState();
  });
}

app.whenReady().then(async () => {
  const runsRoot = path.join(app.getPath("documents"), "Forge3D", "runs");
  const localStateRoot = path.join(process.env.LOCALAPPDATA || app.getPath("appData"), "Instrumenta", "Forge3D");
  const resourceBase = app.isPackaged ? process.resourcesPath : path.join(repoRoot, "desktop");
  runtimeState = ensureRuntimeState(localStateRoot, resourceBase);
  if (!app.isPackaged && !fs.existsSync(path.join(runtimeState.godot, ".forge3d-template-version"))) {
    fs.cpSync(path.join(repoRoot, "godot"), runtimeState.godot, { recursive: true, force: true, filter: (item) => !item.includes(`${path.sep}.godot${path.sep}`) });
    fs.writeFileSync(path.join(runtimeState.godot, ".forge3d-template-version"), `${BUNDLE_VERSION}\n`, "utf8");
  }
  runStore = new RunStore(runsRoot);
  runStore.recoverInterrupted();

  protocol.handle("forge3d-artifact", (request) => {
    const url = new URL(request.url);
    const runId = url.hostname;
    const relative = decodeURIComponent(url.pathname.replace(/^\//, ""));
    const absolute = runStore.resolveArtifact(runId, relative);
    return net.fetch(pathToFileURL(absolute).toString());
  });
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  registerIpc();
  createWindow();
  const godot = externalTools(true).godot;
  if (godot) {
    godotPrimePromise = primeGodotProject(runtimeState, godot);
    godotPrimePromise.catch((error) => send("forge3d:error", `Godot project setup failed: ${error.message}`));
  }
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  try { flushRunEvents(); } catch {}
  codexClient?.close();
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});