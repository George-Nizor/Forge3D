const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const desktopRoot = path.resolve(__dirname, "..");
const renderer = fs.readFileSync(path.join(desktopRoot, "src", "renderer", "main.js"), "utf8");
const styles = fs.readFileSync(path.join(desktopRoot, "src", "renderer", "style.css"), "utf8");
const icon = fs.readFileSync(path.join(desktopRoot, "assets", "icon.png"));
const mark = fs.readFileSync(path.join(desktopRoot, "assets", "forge3d-mark.png"));
const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));

function pngDimensions(buffer) {
  assert.deepEqual([...buffer.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

test("approved Logo A is the canonical desktop identity", () => {
  assert.deepEqual(pngDimensions(icon), { width: 512, height: 512 });
  assert.equal(pngDimensions(mark).width, pngDimensions(mark).height);
  assert.match(renderer, /import brandMark from "\.\/forge3d-mark\.png"/);
  assert.match(renderer, /<img src="\$\{brandMark\}"/);
  assert.doesNotMatch(renderer, /brand-symbol|Codex-driven asset studio|class="brand-mark">F3/);
  assert.equal(packageJson.dependencies["@fontsource/space-grotesk"], "5.3.0");
  assert.match(styles, /--display: "Space Grotesk"/);
});

test("approved UI A keeps the run library and inspector as permanent workstation panes", () => {
  assert.match(renderer, /class="app-bar"/);
  assert.match(renderer, /class="pane library"/);
  assert.match(renderer, /class="viewport-tools"/);
  assert.match(renderer, /class="pane inspector"/);
  assert.match(renderer, /class="status-bar"/);
  assert.match(renderer, /const glyphs = \{/);
  assert.doesNotMatch(renderer, /class="production-rail"|class="drawer library"|class="drawer inspector"|class="edge-tab"/);
  assert.doesNotMatch(renderer, /SPATIAL CANVAS|PRODUCTION|Waiting for a brief|Shape the next thing/);
  assert.match(styles, /grid-template-columns: clamp\(218px, 16vw, 278px\)/);
  assert.match(styles, /grid-template-rows: 35px 39px minmax\(0,1fr\) 105px/);
});