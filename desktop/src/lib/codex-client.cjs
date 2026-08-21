"use strict";

const { EventEmitter } = require("node:events");
const { spawn } = require("node:child_process");
const readline = require("node:readline");

class CodexAppServerClient extends EventEmitter {
  constructor({ command = "codex", args = ["app-server"], cwd, env = process.env, spawnProcess = spawn } = {}) {
    super();
    this.command = command;
    this.args = args;
    this.cwd = cwd;
    this.env = env;
    this.spawnProcess = spawnProcess;
    this.process = null;
    this.reader = null;
    this.pending = new Map();
    this.serverRequests = new Map();
    this.nextId = 1;
    this.started = false;
    this.stderr = "";
  }

  async start() {
    if (this.started) return;
    if (this.process) throw new Error("Codex App Server is already starting");
    this.process = this.spawnProcess(this.command, this.args, {
      cwd: this.cwd,
      env: this.env,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.process.once("error", (error) => this._failAll(error));
    this.process.once("exit", (code, signal) => {
      const detail = this.stderr.trim().slice(-2000);
      this._failAll(new Error(`Codex App Server exited (${code ?? signal ?? "unknown"})${detail ? `: ${detail}` : ""}`));
      this.emit("exit", { code, signal, detail });
      this.started = false;
      this.process = null;
    });
    this.process.stderr.on("data", (chunk) => {
      this.stderr = `${this.stderr}${chunk.toString("utf8")}`.slice(-8000);
      this.emit("stderr", chunk.toString("utf8"));
    });
    this.reader = readline.createInterface({ input: this.process.stdout });
    this.reader.on("line", (line) => this.ingestLine(line));

    await this.request("initialize", {
      clientInfo: { name: "forge3d_desktop", title: "Forge3D", version: "0.2.1" },
    });
    this.notify("initialized", {});
    this.started = true;
  }

  _write(message) {
    if (!this.process?.stdin?.writable) throw new Error("Codex App Server is not connected");
    this.process.stdin.write(`${JSON.stringify(message)}\n`);
  }

  request(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { method, resolve, reject });
      try {
        this._write({ method, id, params });
      } catch (error) {
        this.pending.delete(id);
        reject(error);
      }
    });
  }

  notify(method, params = {}) {
    this._write({ method, params });
  }

  ingestLine(line) {
    if (!line.trim()) return;
    let message;
    try {
      message = JSON.parse(line);
    } catch (error) {
      this.emit("protocolError", new Error(`Invalid App Server JSONL: ${error.message}`));
      return;
    }
    if (Object.hasOwn(message, "id") && message.method) {
      this.serverRequests.set(message.id, message);
      this.emit("request", message);
      return;
    }
    if (Object.hasOwn(message, "id")) {
      const pending = this.pending.get(message.id);
      if (!pending) {
        this.emit("protocolError", new Error(`Unexpected App Server response id ${message.id}`));
        return;
      }
      this.pending.delete(message.id);
      if (message.error) pending.reject(new Error(message.error.message || JSON.stringify(message.error)));
      else pending.resolve(message.result);
      return;
    }
    if (message.method) this.emit("notification", message);
  }

  respond(requestId, result) {
    if (!this.serverRequests.has(requestId)) throw new Error(`Unknown App Server request ${requestId}`);
    this.serverRequests.delete(requestId);
    this._write({ id: requestId, result });
  }

  async listSkills(cwd, forceReload = false) {
    const result = await this.request("skills/list", { cwds: [cwd], forceReload });
    return result?.data?.flatMap((entry) => entry.skills || []) || [];
  }

  async startThread({ cwd, model }) {
    const params = { cwd, approvalPolicy: "unlessTrusted" };
    if (model && model !== "auto") params.model = model;
    const result = await this.request("thread/start", params);
    return result.thread;
  }

  async resumeThread(threadId) {
    const result = await this.request("thread/resume", { threadId });
    return result.thread;
  }

  async startTurn({ threadId, prompt, cwd, skill, images = [], model, effort, allowNetwork = false }) {
    const input = [{ type: "text", text: `$forge3d ${prompt}` }];
    if (skill?.path) input.push({ type: "skill", name: "forge3d", path: skill.path });
    for (const imagePath of images) input.push({ type: "localImage", path: imagePath });
    const params = {
      threadId,
      input,
      cwd,
      approvalPolicy: "unlessTrusted",
      sandboxPolicy: {
        type: "workspaceWrite",
        writableRoots: [cwd],
        networkAccess: Boolean(allowNetwork),
      },
    };
    if (model && model !== "auto") params.model = model;
    if (effort && effort !== "auto") params.effort = effort;
    const result = await this.request("turn/start", params);
    return result.turn;
  }

  steer(threadId, turnId, text) {
    return this.request("turn/steer", {
      threadId,
      expectedTurnId: turnId,
      input: [{ type: "text", text }],
    });
  }

  interrupt(threadId, turnId) {
    return this.request("turn/interrupt", { threadId, turnId });
  }

  decide(requestId, decision) {
    const allowed = new Set(["accept", "acceptForSession", "decline", "cancel"]);
    if (!allowed.has(decision)) throw new Error("Invalid approval decision");
    this.respond(requestId, { decision });
  }

  close() {
    this.reader?.close();
    if (this.process && !this.process.killed) this.process.kill();
    this._failAll(new Error("Codex App Server was closed"));
    this.started = false;
    this.process = null;
  }

  _failAll(error) {
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
  }
}

module.exports = { CodexAppServerClient };