"use strict";

const path = require("node:path");

const LOCAL_MCP_SERVERS = new Set(["blender", "godot"]);
const REMOTE_INTENT = /(?:https?:\/\/|\bcurl(?:\.exe)?\b|\bwget(?:\.exe)?\b|invoke-webrequest|\bcloud-run\b|\bapprove-upload\b|\bupload(?:ing)?\b|\bprovider action\b)/i;

function pathModule(root, candidate) {
  return /^[a-z]:[\\/]/i.test(String(root)) || /^[a-z]:[\\/]/i.test(String(candidate)) ? path.win32 : path;
}

function contained(root, candidate) {
  if (!root || !candidate) return false;
  const platformPath = pathModule(root, candidate);
  const base = platformPath.resolve(root);
  const target = platformPath.isAbsolute(candidate) ? platformPath.resolve(candidate) : platformPath.resolve(base, candidate);
  const relative = platformPath.relative(base, target);
  return relative === "" || (!relative.startsWith("..") && !platformPath.isAbsolute(relative));
}

function textOf(value) {
  try { return JSON.stringify(value); } catch { return String(value || ""); }
}

function explicitWritePaths(params) {
  const permissions = params.additionalPermissions || params.additional_permissions || {};
  const fileSystem = permissions.fileSystem || permissions.filesystem || permissions.file_system || {};
  const values = fileSystem.write || fileSystem.writes || fileSystem.writePaths || fileSystem.write_paths || [];
  return Array.isArray(values) ? values.filter((value) => typeof value === "string") : [];
}

function requestsNetwork(params) {
  if (params.networkApprovalContext || params.network_approval_context) return true;
  const permissions = params.additionalPermissions || params.additional_permissions || {};
  const network = permissions.network;
  return network === true || network?.enabled === true;
}

function automaticApproval(message, runDirectory) {
  const params = message?.params || {};

  if (message?.method === "item/commandExecution/requestApproval") {
    if (requestsNetwork(params) || REMOTE_INTENT.test(textOf(params.command))) return null;
    if (params.cwd && !contained(runDirectory, params.cwd)) return null;
    if (explicitWritePaths(params).some((candidate) => !contained(runDirectory, candidate))) return null;
    return { decision: "acceptForSession", label: "Auto-approved contained local command." };
  }

  if (message?.method === "item/fileChange/requestApproval") {
    const changes = params.changes || params.fileChanges || params.file_changes || [];
    const paths = Array.isArray(changes)
      ? changes.flatMap((change) => [change?.path, change?.filePath, change?.file_path]).filter(Boolean)
      : [];
    if (paths.some((candidate) => !contained(runDirectory, candidate))) return null;
    return { decision: "acceptForSession", label: "Auto-approved contained run-file change." };
  }

  if (message?.method === "mcpServer/elicitation/request") {
    const serverName = String(params.serverName || params.server_name || "").toLowerCase();
    const request = params.request || {};
    if (!LOCAL_MCP_SERVERS.has(serverName)) return null;
    if (request?._meta?.codex_approval_kind !== "mcp_tool_call") return null;
    if (REMOTE_INTENT.test(textOf(request))) return null;
    return { decision: "acceptForSession", label: `Auto-approved local ${serverName} tool for this session.` };
  }

  return null;
}

module.exports = { automaticApproval, contained };
