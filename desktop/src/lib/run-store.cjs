"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { classify, scanArtifacts } = require("./artifacts.cjs");
const { assertLeafName, assertRegularFile, assertSafeRunId, resolveContained } = require("./path-policy.cjs");

const SCHEMA_VERSION = 2;
const READABLE_SCHEMAS = new Set([1, 2]);
const ACTIVE_STATUSES = new Set(["launching", "running", "cancelling"]);

function timestamp() {
  return new Date().toISOString();
}

function slugify(value) {
  const slug = String(value || "run").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return (slug || "run").slice(0, 64);
}

function sha256(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

const RENAME_RETRY_SIGNAL = new Int32Array(new SharedArrayBuffer(4));

function renameWithRetry(source, target) {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    try {
      fs.renameSync(source, target);
      return;
    } catch (error) {
      if (!["EPERM", "EACCES", "EBUSY"].includes(error.code) || attempt === 5) throw error;
      Atomics.wait(RENAME_RETRY_SIGNAL, 0, 0, 10 * (2 ** attempt));
    }
  }
}

function atomicWriteJson(filePath, value) {
  const temporary = `${filePath}.${process.pid}.${crypto.randomUUID()}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
  try {
    renameWithRetry(temporary, filePath);
  } catch (error) {
    fs.rmSync(temporary, { force: true });
    throw error;
  }
}

function uniqueLeaf(directory, requested) {
  const extension = path.extname(requested);
  const stem = path.basename(requested, extension);
  for (let version = 1; version < 10000; version += 1) {
    const name = version === 1 ? requested : `${stem}-v${String(version).padStart(3, "0")}${extension}`;
    const target = resolveContained(directory, name);
    if (!fs.existsSync(target)) return { name, target };
  }
  throw new Error(`Too many attachment versions for ${requested}`);
}

function validateManifest(data, manifestPath) {
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error(`Invalid run manifest: ${manifestPath}`);
  if (!READABLE_SCHEMAS.has(data.schema_version)) throw new Error(`Unsupported run schema ${data.schema_version}: ${manifestPath}`);
  assertSafeRunId(data.run_id);
  if (data.schema_version === 2 && !Array.isArray(data.artifacts)) throw new Error(`Run schema v2 requires artifacts: ${manifestPath}`);
  return data;
}

class RunStore {
  constructor(runsRoot) {
    this.root = path.resolve(runsRoot);
    this.archiveRoot = resolveContained(this.root, ".archive");
    fs.mkdirSync(this.root, { recursive: true });
    fs.mkdirSync(this.archiveRoot, { recursive: true });
  }

  _manifestPath(directory) {
    return resolveContained(directory, "run.json");
  }

  _directories(includeArchived = true) {
    const roots = [this.root, ...(includeArchived ? [this.archiveRoot] : [])];
    const result = [];
    for (const root of roots) {
      if (!fs.existsSync(root)) continue;
      for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
        if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
        const directory = resolveContained(root, entry.name);
        const manifest = this._manifestPath(directory);
        if (fs.existsSync(manifest)) result.push({ directory, archived: root === this.archiveRoot });
      }
    }
    return result;
  }

  _readDirectory(directory, archived = false) {
    const manifestPath = this._manifestPath(directory);
    const manifest = validateManifest(JSON.parse(fs.readFileSync(manifestPath, "utf8")), manifestPath);
    return { directory, archived, manifest: this._normalizeForClient(manifest, directory) };
  }

  _normalizeForClient(manifest, directory) {
    const normalized = structuredClone(manifest);
    if (normalized.schema_version === 1) {
      normalized.artifacts = [];
      for (const [name, raw] of Object.entries(normalized.outputs || {})) {
        const candidate = path.isAbsolute(raw) ? path.resolve(raw) : resolveContained(directory, raw);
        const relative = path.relative(directory, candidate);
        if (relative.startsWith("..") || path.isAbsolute(relative) || !fs.existsSync(candidate)) continue;
        normalized.artifacts.push({
          name,
          path: relative.split(path.sep).join("/"),
          workflow_route: normalized.command || "legacy",
          size_bytes: fs.statSync(candidate).size,
          ...classify(relative),
        });
      }
    }
    normalized.archived = false;
    return normalized;
  }

  list() {
    return this._directories(true)
      .map(({ directory, archived }) => {
        const item = this._readDirectory(directory, archived);
        item.manifest.archived = archived;
        return item.manifest;
      })
      .sort((left, right) => String(right.updated_at || right.created_at).localeCompare(String(left.updated_at || left.created_at)));
  }

  find(runId, includeArchived = true) {
    assertSafeRunId(runId);
    for (const item of this._directories(includeArchived)) {
      const loaded = this._readDirectory(item.directory, item.archived);
      if (loaded.manifest.run_id === runId) return loaded;
    }
    throw new Error(`Run not found: ${runId}`);
  }

  async create({ prompt, workflow = "auto", quality = "balanced", targetFormat = "glb", tool = "auto", outputSettings = {}, cloudApproved = false, attachments = [] }) {
    if (typeof prompt !== "string" || !prompt.trim()) throw new Error("A prompt is required");
    if (!Array.isArray(attachments) || attachments.length > 12) throw new Error("At most 12 attachments are allowed");
    const runId = crypto.randomUUID();
    const stamp = timestamp().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
    const directory = resolveContained(this.root, `${stamp}-${slugify(prompt)}-${runId.slice(0, 8)}`);
    fs.mkdirSync(directory);
    const attachmentRoot = resolveContained(directory, "attachments");
    fs.mkdirSync(attachmentRoot);
    const inputs = [];
    try {
      for (const sourceRaw of attachments) {
        if (typeof sourceRaw !== "string" || !path.isAbsolute(sourceRaw)) throw new Error("Attachment paths must be absolute");
        const source = assertRegularFile(path.resolve(sourceRaw));
        const requested = assertLeafName(path.basename(source), "attachment");
        const { name, target } = uniqueLeaf(attachmentRoot, requested);
        fs.copyFileSync(source, target, fs.constants.COPYFILE_EXCL);
        inputs.push({
          name,
          path: `attachments/${name}`,
          size_bytes: fs.statSync(target).size,
          sha256: sha256(target),
          media_type: classify(name).media_type,
        });
      }
      const now = timestamp();
      const manifest = {
        schema_version: SCHEMA_VERSION,
        run_id: runId,
        name: path.basename(directory),
        command: "prompt",
        workflow_route: workflow,
        status: "prepared",
        created_at: now,
        updated_at: now,
        completed_at: null,
        prompt: prompt.trim(),
        inputs,
        settings: { quality, target_format: targetFormat, tool, output: outputSettings, cloud_approved: Boolean(cloudApproved) },
        steps: [],
        outputs: {},
        artifacts: [],
        validation: {},
        tools: {},
        codex: { thread_id: null, turn_ids: [] },
        transcript: [],
        failure: null,
      };
      atomicWriteJson(this._manifestPath(directory), manifest);
      return manifest;
    } catch (error) {
      fs.rmSync(directory, { recursive: true, force: true });
      throw error;
    }
  }

  update(runId, mutator) {
    const loaded = this.find(runId, false);
    const manifest = JSON.parse(fs.readFileSync(this._manifestPath(loaded.directory), "utf8"));
    mutator(manifest, loaded.directory);
    manifest.updated_at = timestamp();
    atomicWriteJson(this._manifestPath(loaded.directory), manifest);
    return this._normalizeForClient(manifest, loaded.directory);
  }

  setStatus(runId, status, failure = null) {
    return this.update(runId, (manifest) => {
      manifest.status = status;
      manifest.failure = failure;
      if (["completed", "failed", "interrupted", "cancelled"].includes(status)) manifest.completed_at = timestamp();
    });
  }

  setCodex(runId, threadId, turnId = null) {
    return this.update(runId, (manifest) => {
      manifest.codex ||= { thread_id: null, turn_ids: [] };
      manifest.codex.thread_id = threadId;
      if (turnId && !manifest.codex.turn_ids.includes(turnId)) manifest.codex.turn_ids.push(turnId);
    });
  }

  appendEvents(runId, events) {
    if (!Array.isArray(events) || !events.length) return this.find(runId, false).manifest;
    const mergeable = new Set(["agent", "log", "delta", "app-server-stderr"]);
    return this.update(runId, (manifest) => {
      manifest.transcript ||= [];
      for (const event of events) {
        const next = { at: timestamp(), ...event };
        const previous = manifest.transcript.at(-1);
        const canMerge = previous
          && mergeable.has(next.kind)
          && previous.kind === next.kind
          && previous.method === next.method
          && typeof previous.text === "string"
          && typeof next.text === "string"
          && previous.text.length < 50000;
        if (canMerge) {
          previous.text = `${previous.text}${next.text}`.slice(-50000);
          previous.at = next.at;
        } else {
          manifest.transcript.push(next);
        }
      }
      if (manifest.transcript.length > 1200) manifest.transcript.splice(0, manifest.transcript.length - 1200);
    });
  }

  appendEvent(runId, event) {
    return this.appendEvents(runId, [event]);
  }

  refreshArtifacts(runId) {
    return this.update(runId, (manifest, directory) => {
      manifest.artifacts = scanArtifacts(directory, manifest.workflow_route || manifest.command || "prompt");
      manifest.outputs = Object.fromEntries(manifest.artifacts.map((item) => [item.name, item.path]));
    });
  }

  recoverInterrupted() {
    const recovered = [];
    for (const manifest of this.list()) {
      if (manifest.archived || !ACTIVE_STATUSES.has(manifest.status)) continue;
      this.setStatus(manifest.run_id, "interrupted", "Forge3D recovered this job after the desktop process stopped unexpectedly.");
      recovered.push(this.refreshArtifacts(manifest.run_id));
    }
    return recovered;
  }

  duplicate(runId) {
    const loaded = this.find(runId, false);
    const manifest = loaded.manifest;
    const attachments = (manifest.inputs || []).map((item) => resolveContained(loaded.directory, item.path));
    return this.create({
      prompt: manifest.prompt,
      workflow: manifest.workflow_route,
      quality: manifest.settings?.quality,
      targetFormat: manifest.settings?.target_format,
      tool: manifest.settings?.tool,
      outputSettings: manifest.settings?.output,
      cloudApproved: false,
      attachments,
    });
  }

  archive(runId) {
    const loaded = this.find(runId, false);
    let target = resolveContained(this.archiveRoot, path.basename(loaded.directory));
    if (fs.existsSync(target)) target = resolveContained(this.archiveRoot, `${path.basename(loaded.directory)}-${Date.now()}`);
    fs.renameSync(loaded.directory, target);
    return this._readDirectory(target, true).manifest;
  }

  resolveArtifact(runId, relativePath) {
    const loaded = this.find(runId, true);
    if (typeof relativePath !== "string" || path.isAbsolute(relativePath)) throw new Error("Artifact paths must be relative");
    const absolute = resolveContained(loaded.directory, relativePath);
    const stat = fs.lstatSync(absolute);
    if (stat.isSymbolicLink() || !stat.isFile()) throw new Error("Artifact is not a regular file");
    return absolute;
  }

  runDirectory(runId) {
    return this.find(runId, true).directory;
  }
}

module.exports = { READABLE_SCHEMAS, RunStore, atomicWriteJson, validateManifest };