"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { automaticApproval, contained } = require("../src/lib/approval-policy.cjs");

const run = "C:\\Users\\George\\Documents\\Forge3D\\runs\\spoon";

test("path containment accepts the run and descendants only", () => {
  assert.equal(contained(run, run), true);
  assert.equal(contained(run, '.\\spoon.blend'), true);
  assert.equal(contained(run, `${run}\\spoon.blend`), true);
  assert.equal(contained(run, "C:\\Users\\George\\Documents\\outside.blend"), false);
});

test("contained local commands auto-approve without a user prompt", () => {
  const result = automaticApproval({
    method: "item/commandExecution/requestApproval",
    params: { cwd: run, command: ["blender.exe", "--background", "--python", ".\\build.py"] },
  }, run);
  assert.equal(result.decision, "acceptForSession");
});

test("network, upload, and outside-write requests remain interactive", () => {
  assert.equal(automaticApproval({
    method: "item/commandExecution/requestApproval",
    params: { cwd: run, command: "curl https://example.com/model", networkApprovalContext: {} },
  }, run), null);
  assert.equal(automaticApproval({
    method: "item/commandExecution/requestApproval",
    params: { cwd: run, command: "forge3d cloud-run --approve-upload" },
  }, run), null);
  assert.equal(automaticApproval({
    method: "item/commandExecution/requestApproval",
    params: { cwd: run, command: "tool", additionalPermissions: { fileSystem: { write: ["C:\\Windows\\Temp"] } } },
  }, run), null);
});

test("local Blender and Godot MCP tools auto-approve for the session", () => {
  for (const serverName of ["blender", "godot"]) {
    const result = automaticApproval({
      method: "mcpServer/elicitation/request",
      params: {
        serverName,
        request: {
          message: `Allow ${serverName} tool?`,
          _meta: { codex_approval_kind: "mcp_tool_call" },
        },
      },
    }, run);
    assert.equal(result.decision, "acceptForSession");
  }
});

test("unknown MCP and remote-intent MCP requests remain interactive", () => {
  assert.equal(automaticApproval({
    method: "mcpServer/elicitation/request",
    params: { serverName: "unknown", request: { _meta: { codex_approval_kind: "mcp_tool_call" } } },
  }, run), null);
  assert.equal(automaticApproval({
    method: "mcpServer/elicitation/request",
    params: {
      serverName: "blender",
      request: { message: "Upload to https://provider.example", _meta: { codex_approval_kind: "mcp_tool_call" } },
    },
  }, run), null);
});
