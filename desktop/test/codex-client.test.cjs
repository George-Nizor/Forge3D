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

test("thread and turn requests use the current interactive approval policy", async () => {
  const client = new CodexAppServerClient();
  const calls = [];
  client.request = async (method, params) => {
    calls.push({ method, params });
    return method === "thread/start"
      ? { thread: { id: "thr-1" } }
      : { turn: { id: "turn-1" } };
  };

  await client.startThread({ cwd: "C:\\runs\\bookshelf", model: "auto" });
  await client.startTurn({
    threadId: "thr-1",
    prompt: "Make a bookshelf",
    cwd: "C:\\runs\\bookshelf",
  });

  assert.equal(calls[0].params.approvalPolicy, "on-request");
  assert.equal(calls[1].params.approvalPolicy, "on-request");
  assert.doesNotMatch(JSON.stringify(calls), /unlessTrusted/);
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

test("answers MCP tool approval elicitations with the App Server wire schema", () => {
  const { client, writes } = connectedClient();
  client.ingestLine(JSON.stringify({
    id: 92,
    method: "mcpServer/elicitation/request",
    params: {
      threadId: "thr-1",
      turnId: "turn-1",
      serverName: "blender",
      request: {
        mode: "form",
        message: "Allow the blender MCP server to run tool get_scene_info?",
        requestedSchema: {},
        _meta: { codex_approval_kind: "mcp_tool_call", persist: ["session", "always"] },
      },
    },
  }));
  client.decide(92, "acceptForSession");
  assert.deepEqual(writes[0], {
    id: 92,
    result: { action: "accept", content: {}, _meta: { persist: "session" } },
  });
});

test("declines MCP tool approval elicitations with null content and metadata", () => {
  const { client, writes } = connectedClient();
  client.ingestLine(JSON.stringify({ id: 93, method: "mcpServer/elicitation/request", params: {} }));
  client.decide(93, "decline");
  assert.deepEqual(writes[0], {
    id: 93,
    result: { action: "decline", content: null, _meta: null },
  });
});

test("rejects unsupported server requests with a JSON-RPC method error", () => {
  const { client, writes } = connectedClient();
  client.ingestLine(JSON.stringify({ id: 94, method: "tool/requestUserInput", params: {} }));
  client.reject(94);
  assert.deepEqual(writes[0], {
    id: 94,
    error: { code: -32601, message: "Unsupported App Server request" },
  });
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