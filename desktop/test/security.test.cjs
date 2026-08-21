"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const main = fs.readFileSync(path.join(__dirname, "..", "src", "main.cjs"), "utf8");
const preload = fs.readFileSync(path.join(__dirname, "..", "src", "preload.cjs"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");

test("Electron renderer is isolated and permissions default to deny", () => {
  assert.match(main, /contextIsolation:\s*true/);
  assert.match(main, /sandbox:\s*true/);
  assert.match(main, /nodeIntegration:\s*false/);
  assert.match(main, /corsEnabled:\s*true/);
  assert.match(main, /setPermissionRequestHandler\([^\n]+callback\(false\)/);
  assert.match(main, /setWindowOpenHandler\(\(\) => \(\{ action: "deny" \}\)\)/);
});

test("preload exposes narrow named operations without raw ipcRenderer", () => {
  assert.match(preload, /contextBridge\.exposeInMainWorld\("forge3d"/);
  assert.doesNotMatch(preload, /exposeInMainWorld\([^]*ipcRenderer\s*[,}]/);
  assert.doesNotMatch(preload, /\b(readFile|writeFile|rename|rm|unlink)\s*:/);
});

test("CSP rejects remote scripts and allows only the contained artifact scheme", () => {
  assert.match(html, /script-src 'self'/);
  assert.match(html, /object-src 'none'/);
  assert.match(html, /forge3d-artifact:/);
  assert.doesNotMatch(html, /https:/);
});

test("the WebAssembly grant stays narrow enough for the bundled splat renderer only", () => {
  // Assert the policy itself, not the surrounding markup, so comments cannot mask a widened grant.
  const policy = html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/)[1];
  // Spark compiles its inlined WASM from a data: URL, which needs both grants below.
  assert.match(policy, /script-src 'self' 'wasm-unsafe-eval'/);
  assert.match(policy, /connect-src 'self' data:/);
  // The narrow WASM grant must never become a general eval grant, and nothing may go remote.
  assert.doesNotMatch(policy, /'unsafe-eval'/);
  assert.doesNotMatch(policy, /script-src[^;]*(http:|https:|\*)/);
  assert.doesNotMatch(policy, /connect-src[^;]*(https:|http:\/\/(?!127\.0\.0\.1))/);
});