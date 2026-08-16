const { spawnSync } = require("node:child_process");
const path = require("node:path");

module.exports = async function afterPack(context) {
  if (context.electronPlatformName !== "darwin") {
    return;
  }

  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  const result = spawnSync(
    "codesign",
    ["--force", "--deep", "--sign", "-", appPath],
    { encoding: "utf8" },
  );

  if (result.status !== 0) {
    const details = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
    throw new Error(`Failed to apply an ad-hoc signature to ${appPath}${details ? `:\n${details}` : ""}`);
  }
};
