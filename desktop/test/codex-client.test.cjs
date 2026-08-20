"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { CodexAppServerClient } = require("../src/lib/codex-client.cjs");

function connectedClient() {
  const writes = [];
  const client = new CodexAppServerClient();
  client.process = {
    stdin: {
      writable: true,
      write(line) { writes.push(JSON.parse(line)); },
    },
  };
  return { client, writes };
}

test("matches JSONL responses to requests", async () => {
  const { client, writes } = connectedClient();
  const pending = client.request("thread/start", { cwd: "C:\\run" });
  assert.equal(writes[0].method, "thread/start");
  client.ingestLine(JSON.stringify({ id: writes[0].id, result: { thread: { id: "thr-1" } } }));
  assert.equal((await pending).thread.id, "thr-1");
});

test("surfaces server approval requests and returns a scoped decision", () => {
  const { client, writes } = connectedClient();
  let received = null;
  client.on("request", (request) => { received = request; });
  client.ingestLine(JSON.stringify({
    id: 91,
    method: "item/commandExecution/requestApproval",
    params: { threadId: "thr-1", turnId: "turn-1", command: "blender --background" },
  }));
  assert.equal(received.id, 91);
  client.decide(91, "decline");
  assert.deepEqual(writes[0], { id: 91, result: { decision: "decline" } });
});

test("turn input invokes Forge3D skill, attaches local images, and disables network by default", async () => {
  const client = new CodexAppServerClient();
  let request = null;
  client.request = async (method, params) => {
    request = { method, params };
    return { turn: { id: "turn-1", status: "inProgress" } };
  };
  await client.startTurn({
    threadId: "thr-1",
    prompt: "Make a lantern",
    cwd: "C:\\runs\\lantern",
    skill: { path: "C:\\plugin\\skills\\forge3d\\SKILL.md" },
    images: ["C:\\runs\\lantern\\attachments\\reference.png"],
  });
  assert.equal(request.method, "turn/start");
  assert.equal(request.params.input[0].text, "$forge3d Make a lantern");
  assert.equal(request.params.input[1].type, "skill");
  assert.equal(request.params.input[2].type, "localImage");
  assert.equal(request.params.sandboxPolicy.networkAccess, false);
  assert.deepEqual(request.params.sandboxPolicy.writableRoots, ["C:\\runs\\lantern"]);
});

test("interrupt and steer use the active thread and turn", async () => {
  const client = new CodexAppServerClient();
  const calls = [];
  client.request = async (method, params) => { calls.push({ method, params }); return {}; };
  await client.steer("thr-1", "turn-1", "Use lower topology");
  await client.interrupt("thr-1", "turn-1");
  assert.equal(calls[0].method, "turn/steer");
  assert.equal(calls[0].params.expectedTurnId, "turn-1");
  assert.equal(calls[1].method, "turn/interrupt");
});