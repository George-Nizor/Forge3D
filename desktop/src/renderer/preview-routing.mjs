const SPLAT_EXTENSIONS = new Map([
  [".splat", 0],
  [".sog", 1],
  [".spz", 1],
  [".ksplat", 2],
  [".ply", 3],
]);

const ROLE_PRIORITY = new Map([
  ["model", 0],
  ["gaussian-splat", 1],
  ["primary-image", 2],
  ["animation", 3],
  ["image-sequence", 4],
  ["image", 5],
  ["validation", 6],
  ["text", 7],
  ["metadata", 8],
]);

function extension(artifact) {
  const match = String(artifact?.path || "").toLowerCase().match(/\.[^.\\/]+$/);
  return match?.[0] || "";
}

function versionNumber(artifact) {
  const matches = [...String(artifact?.path || "").matchAll(/(?:^|[\\/_-])v(\d{1,6})(?=[\\/_.-]|$)/gi)];
  return matches.reduce((highest, match) => Math.max(highest, Number(match[1]) || 0), 0);
}

function isSplatTarget(run) {
  const target = String(run?.settings?.target_format || "").toLowerCase();
  const route = String(run?.workflow_route || run?.command || "").toLowerCase();
  return ["splat", "sog", "spz", "ksplat", "ply"].includes(target) || route.includes("splat");
}

function splatPriority(artifact) {
  if (artifact?.preview_role !== "gaussian-splat") return Number.POSITIVE_INFINITY;
  return SPLAT_EXTENSIONS.get(extension(artifact)) ?? 10;
}

function compareArtifacts(run, selectedPath, left, right) {
  if (left.path === selectedPath) return -1;
  if (right.path === selectedPath) return 1;
  if (isSplatTarget(run)) {
    const leftSplatPriority = splatPriority(left);
    const rightSplatPriority = splatPriority(right);
    const splatDifference = leftSplatPriority - rightSplatPriority;
    if (Number.isFinite(splatDifference) && splatDifference !== 0) return splatDifference;
    if (Number.isFinite(leftSplatPriority) !== Number.isFinite(rightSplatPriority)) {
      return Number.isFinite(leftSplatPriority) ? -1 : 1;
    }
  }
  const roleDifference = (ROLE_PRIORITY.get(left.preview_role) ?? 99) - (ROLE_PRIORITY.get(right.preview_role) ?? 99);
  if (roleDifference !== 0) return roleDifference;
  const versionDifference = versionNumber(right) - versionNumber(left);
  if (versionDifference !== 0) return versionDifference;
  return String(left.path).localeCompare(String(right.path));
}

export function selectedArtifactForRun(run, selectedPath = null) {
  const artifacts = run?.artifacts || [];
  const explicit = artifacts.find((artifact) => artifact.path === selectedPath);
  if (explicit) return explicit;
  if (isSplatTarget(run)) {
    const splats = artifacts.filter((artifact) => artifact.preview_role === "gaussian-splat");
    if (splats.length) return [...splats].sort((left, right) => compareArtifacts(run, null, left, right))[0];
  }
  return artifacts.find((artifact) => artifact.preview_role === "primary-image")
    || artifacts.find((artifact) => ["animation", "image-sequence", "model", "gaussian-splat", "image"].includes(artifact.preview_role))
    || artifacts[0]
    || null;
}

export function filmstripArtifacts(run, selectedPath = null, limit = 16) {
  const selected = selectedArtifactForRun(run, selectedPath);
  return [...(run?.artifacts || [])]
    .sort((left, right) => compareArtifacts(run, selected?.path || null, left, right))
    .slice(0, limit);
}

export { isSplatTarget };
