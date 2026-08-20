"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { RunStore, atomicWriteJson } = require("../src/lib/run-store.cjs");

function temporaryDirectory() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "forge3d-run-store-"));
}

test("creates contained schema-v2 runs and copies attachments", async (t) => {
  const root = temporaryDirectory();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const source = path.join(root, "reference.png");
  fs.writeFileSync(source, "image");
  const store = new RunStore(path.join(root, "runs"));
  const run = await store.create({ prompt: "Make a robot", attachments: [source] });
  assert.equal(run.schema_version, 2);
  assert.match(run.inputs[0].path, /^attachments\//);
  const copied = path.join(store.runDirectory(run.run_id), ...run.inputs[0].path.split("/"));
  assert.equal(fs.readFileSync(copied, "utf8"), "image");
  assert.notEqual(copied, source);
});

test("reads schema v1, recovers interrupted runs, and scans image sequences", async (t) => {
  const root = temporaryDirectory();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const store = new RunStore(path.join(root, "runs"));
  const run = await store.create({ prompt: "Turntable", workflow: "authored-blender" });
  const directory = store.runDirectory(run.run_id);
  const sequence = path.join(directory, "turntable");
  fs.mkdirSync(sequence);
  fs.writeFileSync(path.join(sequence, "frame-001.png"), "one");
  fs.writeFileSync(path.join(sequence, "frame-002.png"), "two");
  store.setStatus(run.run_id, "running");
  assert.equal(store.recoverInterrupted()[0].status, "interrupted");
  const refreshed = store.refreshArtifacts(run.run_id);
  assert.equal(refreshed.artifacts[0].preview_role, "image-sequence");
  assert.deepEqual(refreshed.artifacts[0].frames, ["turntable/frame-001.png", "turntable/frame-002.png"]);

  const legacyDirectory = path.join(store.root, "legacy");
  fs.mkdirSync(legacyDirectory);
  fs.writeFileSync(path.join(legacyDirectory, "preview.png"), "legacy");
  atomicWriteJson(path.join(legacyDirectory, "run.json"), {
    schema_version: 1,
    run_id: "2ac676af-46f1-4d5f-a479-9ba6549698c4",
    name: "legacy",
    command: "process",
    status: "completed",
    created_at: "2026-01-01T00:00:00Z",
    outputs: { preview: "preview.png" },
  });
  const loaded = store.find("2ac676af-46f1-4d5f-a479-9ba6549698c4").manifest;
  assert.equal(loaded.schema_version, 1);
  assert.equal(loaded.artifacts[0].preview_role, "primary-image");
});

test("duplicate creates a new version and archive stays browsable", async (t) => {
  const root = temporaryDirectory();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const store = new RunStore(path.join(root, "runs"));
  const original = await store.create({ prompt: "Stone arch" });
  const duplicate = await store.duplicate(original.run_id);
  assert.notEqual(duplicate.run_id, original.run_id);
  const archived = store.archive(original.run_id);
  assert.equal(archived.run_id, original.run_id);
  const row = store.list().find((item) => item.run_id === original.run_id);
  assert.equal(row.archived, true);
});

test("artifact resolution rejects traversal", async (t) => {
  const root = temporaryDirectory();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const store = new RunStore(path.join(root, "runs"));
  const run = await store.create({ prompt: "Contained" });
  assert.throws(() => store.resolveArtifact(run.run_id, "../outside.glb"), /escapes its allowed root/);
});