const ANALYSIS_MODES = Object.freeze(["cpu", "nvidia"]);

function sanitizeAnalysisMode(value, platform = process.platform) {
  if (platform !== "win32") return "cpu";
  return ANALYSIS_MODES.includes(value) ? value : "cpu";
}

function analysisEnvironment(value, platform = process.platform) {
  const mode = sanitizeAnalysisMode(value, platform);
  if (platform === "win32" && mode === "nvidia") {
    return {
      mode,
      analyzerExecutor: "wsl",
      analyzerDevice: "cuda",
      stemDevice: "cuda",
    };
  }
  return {
    mode: "cpu",
    analyzerExecutor: "native",
    analyzerDevice: "cpu",
    stemDevice: "cpu",
  };
}

module.exports = { ANALYSIS_MODES, analysisEnvironment, sanitizeAnalysisMode };
