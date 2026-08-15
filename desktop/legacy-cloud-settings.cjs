const LEGACY_R2_KEYS = new Set([
  "R2_ENABLED",
  "R2_BUCKET",
  "CLOUDFLARE_ACCOUNT_ID",
  "R2_ENDPOINT_URL",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
  "R2_PUBLIC_BASE_URL",
  "R2_PREFIX",
  "R2_REQUIRED",
  "R2_CONFIGURE_CORS",
]);

function parseEnvValue(rawValue) {
  const value = String(rawValue || "").trim();
  if (value.length >= 2 && value[0] === value[value.length - 1] && ["\"", "'"].includes(value[0])) {
    return value.slice(1, -1);
  }
  return value;
}

function parseEnv(text) {
  const values = {};
  for (const rawLine of String(text || "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const separator = line.indexOf("=");
    const key = line.slice(0, separator).trim();
    if (!key) continue;
    values[key] = parseEnvValue(line.slice(separator + 1));
  }
  return values;
}

function truthy(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function cloudSettingsFromLegacyEnv(values) {
  if (!truthy(values.R2_ENABLED)) return null;
  const cloud = {
    enabled: true,
    bucket: String(values.R2_BUCKET || "").trim(),
    accountId: String(values.CLOUDFLARE_ACCOUNT_ID || "").trim(),
    endpointUrl: String(values.R2_ENDPOINT_URL || "").trim(),
    publicBaseUrl: String(values.R2_PUBLIC_BASE_URL || "").trim().replace(/\/$/, ""),
    prefix: String(values.R2_PREFIX || "sessions").trim().replace(/^\/+|\/+$/g, "") || "sessions",
    accessKeyId: String(values.R2_ACCESS_KEY_ID || "").trim(),
    secretAccessKey: String(values.R2_SECRET_ACCESS_KEY || ""),
  };
  if (!cloud.bucket || (!cloud.accountId && !cloud.endpointUrl) || !cloud.accessKeyId || !cloud.secretAccessKey) return null;
  return cloud;
}

function stripLegacyR2Settings(text) {
  const kept = String(text || "").split(/\r?\n/).filter(rawLine => {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) return true;
    const key = line.slice(0, line.indexOf("=")).trim();
    return !LEGACY_R2_KEYS.has(key);
  });
  while (kept.length && !kept[kept.length - 1].trim()) kept.pop();
  return kept.length ? `${kept.join("\n")}\n` : "";
}

module.exports = { cloudSettingsFromLegacyEnv, parseEnv, stripLegacyR2Settings };
