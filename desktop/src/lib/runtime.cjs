"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { atomicWriteJson } = require("./run-store.cjs");
const { resolveContained } = require("./path-policy.cjs");

const BUNDLE_VERSION = "0.2.2";

function firstWhere(command) {
  const result = spawnSync("where.exe", [command], { windowsHide: true, encoding: "utf8" });
  if (result.status !== 0) return null;
  return result.stdout.split(/\r?\n/).map((item) => item.trim()).find(Boolean) || null;
}

function findCodexExecutable() {
  if (process.env.FORGE3D_CODEX_EXE && fs.existsSync(process.env.FORGE3D_CODEX_EXE)) return path.resolve(process.env.FORGE3D_CODEX_EXE);
  const fromPath = firstWhere("codex.exe") || firstWhere("codex");
  if (fromPath) return fromPath;
  const root = path.join(process.env.LOCALAPPDATA || "", "OpenAI", "Codex", "bin");
  if (!fs.existsSync(root)) throw new Error("Codex CLI was not found. Install or repair the Codex app, then retry.");
  const candidates = [];
  const visit = (directory, depth = 0) => {
    if (depth > 6) return;
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(target, depth + 1);
      else if (entry.isFile() && entry.name.toLowerCase() === "codex.exe") candidates.push({ target, modified: fs.statSync(target).mtimeMs });
    }
  };
  visit(root);
  candidates.sort((left, right) => right.modified - left.modified);
  if (!candidates.length) throw new Error("Codex CLI was not found under the Codex installation.");
  return candidates[0].target;
}

function ensureRuntimeState(localStateRoot, resourcesPath) {
  const root = path.resolve(localStateRoot);
  for (const name of ["cache", "config", "logs", "plugin"]) fs.mkdirSync(resolveContained(root, name), { recursive: true });
  const godotTarget = resolveContained(root, "godot");
  const marker = resolveContained(godotTarget, ".forge3d-template-version");
  const source = path.join(resourcesPath, "godot-template");
  if (fs.existsSync(source) && (!fs.existsSync(marker) || fs.readFileSync(marker, "utf8").trim() !== BUNDLE_VERSION)) {
    fs.mkdirSync(godotTarget, { recursive: true });
    fs.cpSync(source, godotTarget, { recursive: true, force: true, filter: (item) => !item.includes(`${path.sep}.godot${path.sep}`) });
    fs.writeFileSync(marker, `${BUNDLE_VERSION}\n`, "utf8");
  }
  return { root, godot: godotTarget, logs: resolveContained(root, "logs"), cache: resolveContained(root, "cache") };
}

function detectExternalTools(localStateRoot) {
  const blenderCandidates = [
    process.env.BLENDER_EXECUTABLE,
    firstWhere("blender.exe"),
    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe",
    "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe",
    "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Blender\\blender.exe",
  ].filter(Boolean);
  const godotCandidates = [process.env.GODOT_EXECUTABLE, firstWhere("godot.exe"), firstWhere("godot")].filter(Boolean);
  const existing = (items) => items.find((item) => fs.existsSync(item)) || null;
  return {
    codex: (() => { try { return findCodexExecutable(); } catch { return null; } })(),
    blender: existing(blenderCandidates),
    godot: existing(godotCandidates),
    wsl: firstWhere("wsl.exe"),
    uvx: firstWhere("uvx.exe") || firstWhere("uvx"),
    local_state: path.resolve(localStateRoot),
  };
}

function inspectForgeSkill(skill) {
  if (!skill?.path || !fs.existsSync(skill.path)) return { state: "missing", bundledVersion: BUNDLE_VERSION };
  const pluginRoot = path.resolve(path.dirname(skill.path), "..", "..");
  const manifestPath = path.join(pluginRoot, ".codex-plugin", "plugin.json");
  let installedVersion = null;
  try {
    installedVersion = JSON.parse(fs.readFileSync(manifestPath, "utf8")).version || null;
  } catch {
    return { state: "invalid", path: skill.path, bundledVersion: BUNDLE_VERSION, installedVersion: null };
  }
  return {
    state: installedVersion === BUNDLE_VERSION ? "ready" : "version-mismatch",
    path: skill.path,
    installedVersion,
    bundledVersion: BUNDLE_VERSION,
  };
}

function generatedMcpConfig(runtimeState) {
  const uvx = firstWhere("uvx.exe") || "uvx";
  return {
    mcpServers: {
      blender: {
        command: uvx,
        args: ["--python", "3.11", "--from", "blender-mcp==1.6.5", "blender-mcp"],
        env: { BLENDER_HOST: "127.0.0.1", BLENDER_PORT: "9876", DISABLE_TELEMETRY: "true" },
      },
      godot: {
        command: path.join(process.env.SystemRoot || "C:\\Windows", "System32", "cmd.exe"),
        args: ["/c", "npx", "-y", "@npgamedev/godot-mcp-server@1.0.0"],
        cwd: runtimeState.godot,
        env: { GODOT_MCP_CONFIG_VERSION: "1", GODOT_MCP_PROJECT_PATH: runtimeState.godot },
      },
    },
  };
}

function repairForgePlugin({ bundledPlugin, runtimeState, codexExecutable = findCodexExecutable() }) {
  const source = path.resolve(bundledPlugin);
  if (!fs.existsSync(path.join(source, ".codex-plugin", "plugin.json"))) throw new Error("The bundled Forge3D plugin is missing");
  const pluginParent = path.join(os.homedir(), "plugins");
  const target = path.join(pluginParent, "forge3d");
  fs.mkdirSync(pluginParent, { recursive: true });
  let backup = null;
  if (fs.existsSync(target)) {
    backup = path.join(pluginParent, `forge3d.backup-${new Date().toISOString().replace(/[:.]/g, "-")}`);
    fs.renameSync(target, backup);
  }
  try {
    fs.cpSync(source, target, { recursive: true, errorOnExist: true, force: false });
    atomicWriteJson(path.join(target, ".mcp.json"), generatedMcpConfig(runtimeState));
    const marketplacePath = path.join(os.homedir(), ".agents", "plugins", "marketplace.json");
    fs.mkdirSync(path.dirname(marketplacePath), { recursive: true });
    const marketplace = fs.existsSync(marketplacePath)
      ? JSON.parse(fs.readFileSync(marketplacePath, "utf8"))
      : { name: "personal", interface: { displayName: "Personal" }, plugins: [] };
    if (!Array.isArray(marketplace.plugins)) throw new Error("Personal marketplace has an invalid plugins list");
    marketplace.plugins = marketplace.plugins.filter((entry) => entry?.name !== "forge3d");
    marketplace.plugins.push({
      name: "forge3d",
      source: { source: "local", path: "./plugins/forge3d" },
      policy: { installation: "AVAILABLE", authentication: "ON_INSTALL" },
      category: "Productivity",
    });
    atomicWriteJson(marketplacePath, marketplace);
    const result = spawnSync(codexExecutable, ["plugin", "add", "forge3d@personal"], { windowsHide: true, encoding: "utf8" });
    if (result.status !== 0) throw new Error(result.stderr.trim() || "Codex could not enable forge3d@personal");
    return { target, backup, version: BUNDLE_VERSION };
  } catch (error) {
    if (fs.existsSync(target)) fs.rmSync(target, { recursive: true, force: true });
    if (backup && fs.existsSync(backup)) fs.renameSync(backup, target);
    throw error;
  }
}

module.exports = { BUNDLE_VERSION, detectExternalTools, ensureRuntimeState, findCodexExecutable, inspectForgeSkill, repairForgePlugin };