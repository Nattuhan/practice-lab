const test = require("node:test");
const assert = require("node:assert/strict");

const { analysisEnvironment, sanitizeAnalysisMode } = require("../analysis-settings.cjs");

test("Windows defaults to CPU analysis", () => {
  assert.equal(sanitizeAnalysisMode(undefined, "win32"), "cpu");
  assert.deepEqual(analysisEnvironment(undefined, "win32"), {
    mode: "cpu",
    analyzerExecutor: "native",
    analyzerDevice: "cpu",
    stemDevice: "cpu",
  });
});

test("Windows can explicitly select the NVIDIA WSL runtime", () => {
  assert.deepEqual(analysisEnvironment("nvidia", "win32"), {
    mode: "nvidia",
    analyzerExecutor: "wsl",
    analyzerDevice: "cuda",
    stemDevice: "cuda",
  });
});

test("non-Windows platforms never retain NVIDIA mode", () => {
  assert.equal(sanitizeAnalysisMode("nvidia", "darwin"), "cpu");
  assert.equal(analysisEnvironment("nvidia", "darwin").mode, "cpu");
});
