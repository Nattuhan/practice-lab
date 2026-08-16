const RELEASES_LATEST_URL = "https://github.com/Nattuhan/practice-lab/releases/latest";

function getUpdateMode({ packaged, platform }) {
  if (!packaged) return "development";
  if (platform === "darwin") return "manual";
  return "automatic";
}

module.exports = { RELEASES_LATEST_URL, getUpdateMode };
