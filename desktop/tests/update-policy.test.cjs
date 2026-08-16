const test = require("node:test");
const assert = require("node:assert/strict");
const { RELEASES_LATEST_URL, getUpdateMode } = require("../update-policy.cjs");

test("未署名Mac版は手動更新、Windows版は自動更新を使う", () => {
  assert.equal(getUpdateMode({ packaged: true, platform: "darwin" }), "manual");
  assert.equal(getUpdateMode({ packaged: true, platform: "win32" }), "automatic");
  assert.equal(getUpdateMode({ packaged: false, platform: "darwin" }), "development");
  assert.match(RELEASES_LATEST_URL, /^https:\/\/github\.com\//);
});
