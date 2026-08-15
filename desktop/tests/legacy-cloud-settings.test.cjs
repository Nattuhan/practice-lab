const assert = require("node:assert/strict");
const test = require("node:test");
const {
  cloudSettingsFromLegacyEnv,
  parseEnv,
  stripLegacyR2Settings,
} = require("../legacy-cloud-settings.cjs");

test("旧envのR2設定をデスクトップ設定へ変換する", () => {
  const values = parseEnv(`
R2_ENABLED=1
R2_BUCKET="practice-lab"
R2_ENDPOINT_URL=https://account.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=access-key
R2_SECRET_ACCESS_KEY='secret-key'
R2_PUBLIC_BASE_URL=https://assets.example.com/
R2_PREFIX=/sessions/
`);
  assert.deepEqual(cloudSettingsFromLegacyEnv(values), {
    enabled: true,
    bucket: "practice-lab",
    accountId: "",
    endpointUrl: "https://account.r2.cloudflarestorage.com",
    publicBaseUrl: "https://assets.example.com",
    prefix: "sessions",
    accessKeyId: "access-key",
    secretAccessKey: "secret-key",
  });
});

test("必須項目が欠けた旧設定は移行しない", () => {
  assert.equal(cloudSettingsFromLegacyEnv(parseEnv("R2_ENABLED=1\nR2_BUCKET=test\n")), null);
});

test("R2項目だけを除去して無関係な旧設定を残す", () => {
  const cleaned = stripLegacyR2Settings("# keep\nOTHER_SETTING=yes\nR2_ACCESS_KEY_ID=id\nR2_SECRET_ACCESS_KEY=secret\n");
  assert.equal(cleaned, "# keep\nOTHER_SETTING=yes\n");
  assert.equal(stripLegacyR2Settings("R2_ENABLED=1\nR2_SECRET_ACCESS_KEY=secret\n"), "");
});
