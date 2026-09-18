const path = require("path");

const DEVELOPMENT_PRODUCT_NAME = "PracticeLab Dev";
const NORMAL_MAC_APP_EXECUTABLE = "/Applications/PracticeLab.app/Contents/MacOS/PracticeLab";

function isSharedDataDevelopmentBuild(appName, platform = process.platform, executablePath = process.execPath) {
  const executableName = path.basename(executablePath || "");
  return platform === "darwin" && (appName === DEVELOPMENT_PRODUCT_NAME || executableName === DEVELOPMENT_PRODUCT_NAME);
}

function normalMacDataDirectory(homeDirectory) {
  return path.join(homeDirectory, "Library", "Application Support", "practice-lab", "data");
}

function hasNormalMacAppProcess(processList, currentPid = process.pid) {
  return String(processList || "").split("\n").some(line => {
    const match = line.trim().match(/^(\d+)\s+(.+)$/);
    if (!match || Number(match[1]) === Number(currentPid)) return false;
    const command = match[2];
    return command === NORMAL_MAC_APP_EXECUTABLE || command.startsWith(`${NORMAL_MAC_APP_EXECUTABLE} `);
  });
}

module.exports = {
  DEVELOPMENT_PRODUCT_NAME,
  hasNormalMacAppProcess,
  isSharedDataDevelopmentBuild,
  normalMacDataDirectory,
};
