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

test("approved UI B keeps the viewport-first alignment composition", () => {
  // Instrumenta/docs/design-references/forge3d-ui-claude-alignment-reference.png
  assert.match(renderer, /class="topbar"/);
  assert.match(renderer, /class="omnibox"/);
  assert.match(renderer, /class="run-button"/);
  assert.match(renderer, /class="stage"/);
  assert.match(renderer, /id="preview" class="viewport"/);
  assert.match(renderer, /class="toolrail"/);
  assert.match(renderer, /class="panel library"/);
  assert.match(renderer, /class="panel inspector"/);
  assert.match(renderer, /class="edge-tab"/);
  assert.match(renderer, /class="dock"/);
  assert.match(renderer, /id="pipeline"/);
  assert.match(renderer, /id="filmstrip"/);
  assert.match(renderer, /class="statusbar"/);
  assert.match(renderer, /const glyphs = \{/);
  assert.doesNotMatch(renderer, /class="app-bar"|class="pane library"|class="pane inspector"|class="production-rail"/);
  assert.match(styles, /--topbar-h: 72px/);
  assert.match(styles, /grid-template-rows: var\(--topbar-h\) minmax\(0, 1fr\) var\(--dock-h\) var\(--status-h\)/);
});

test("the pipeline dock reports the four production stages", () => {
  for (const label of ["Plan", "Build", "Check", "Output"]) {
    assert.match(renderer, new RegExp(`label: "${label}"`));
  }
  assert.match(renderer, /function pipelineStages\(/);
});

test("the Windows caption is replaced by the in-app bar without weakening isolation", () => {
  const main = fs.readFileSync(path.join(desktopRoot, "src", "main.cjs"), "utf8");
  assert.match(main, /process\.platform !== "win32"/);
  assert.match(main, /titleBarStyle: "hidden"/);
  assert.match(main, /titleBarOverlay: \{/);
  assert.match(styles, /-webkit-app-region: drag/);
  assert.match(styles, /-webkit-app-region: no-drag/);
});
