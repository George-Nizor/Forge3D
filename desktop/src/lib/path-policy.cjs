"use strict";

const fs = require("node:fs");
const path = require("node:path");

function resolveContained(parent, candidate) {
  const root = path.resolve(parent);
  const target = path.resolve(root, candidate);
  const relative = path.relative(root, target);
  if (relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative))) {
    return target;
  }
  throw new Error(`Path escapes its allowed root: ${candidate}`);
}

function assertLeafName(value, label = "file") {
  if (typeof value !== "string" || !value || value !== path.basename(value) || value === "." || value === "..") {
    throw new Error(`Invalid ${label} name`);
  }
  return value;
}

function assertRegularFile(filePath) {
  const stats = fs.lstatSync(filePath);
  if (!stats.isFile() || stats.isSymbolicLink()) {
    throw new Error(`Expected a regular file: ${filePath}`);
  }
  return filePath;
}

function assertSafeRunId(value) {
  if (typeof value !== "string" || !/^[0-9a-f-]{36}$/i.test(value)) {
    throw new Error("Invalid run id");
  }
  return value;
}

module.exports = { assertLeafName, assertRegularFile, assertSafeRunId, resolveContained };