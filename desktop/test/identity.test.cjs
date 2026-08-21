const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const desktopRoot = path.resolve(__dirname, "..");
const renderer = fs.readFileSync(path.join(desktopRoot, "src", "renderer", "main.js"), "utf8");
const styles = fs.readFileSync(path.join(desktopRoot, "src", "renderer", "style.css"), "utf8");
const icon = fs.readFileSync(path.join(desktopRoot, "assets", "icon.svg"), "utf8");
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));

test("Topology Loop is the canonical desktop identity", () => {
  assert.match(icon, /Forge3D topology loop/);
  assert.doesNotMatch(icon, /cube|anvil|hammer/i);
  assert.match(renderer, /class="brand-symbol"/);
  assert.doesNotMatch(renderer, /Codex-driven asset studio|class="brand-mark">F3/);
  assert.equal(packageJson.dependencies["@fontsource/space-grotesk"], "5.3.0");
  assert.match(styles, /--display: "Space Grotesk"/);
});

test("Spatial Canvas keeps history and inspection out of permanent columns", () => {
  assert.match(renderer, /class="spatial-workspace"/);
  assert.match(renderer, /class="production-rail"/);
  assert.match(renderer, /class="drawer library"/);
  assert.match(renderer, /class="drawer inspector"/);
  assert.match(renderer, /LOCAL TOOLCHAIN READY/);
  assert.doesNotMatch(renderer, /tool\("Codex"|class="workspace"|class="composer panel"/);
  assert.match(styles, /\.drawer\.open/);
  assert.match(styles, /grid-template-columns: repeat\(4/);
});
