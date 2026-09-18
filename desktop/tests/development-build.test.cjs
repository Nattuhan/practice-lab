const test = require("node:test");
const assert = require("node:assert/strict");
const {
  hasNormalMacAppProcess,
  isSharedDataDevelopmentBuild,
  normalMacDataDirectory,
} = require("../development-build.cjs");

test("MacのPracticeLab Devだけを共有データ開発版として扱う", () => {
  assert.equal(isSharedDataDevelopmentBuild("PracticeLab Dev", "darwin", "/Applications/PracticeLab Dev.app/Contents/MacOS/PracticeLab Dev"), true);
  assert.equal(isSharedDataDevelopmentBuild("practice-lab", "darwin", "/Applications/PracticeLab Dev.app/Contents/MacOS/PracticeLab Dev"), true);
  assert.equal(isSharedDataDevelopmentBuild("PracticeLab", "darwin", "/Applications/PracticeLab.app/Contents/MacOS/PracticeLab"), false);
  assert.equal(isSharedDataDevelopmentBuild("PracticeLab Dev", "win32", "PracticeLab Dev.exe"), false);
  assert.equal(
    normalMacDataDirectory("/Users/test"),
    "/Users/test/Library/Application Support/practice-lab/data",
  );
});

test("通常版の本体プロセスだけを検知する", () => {
  const processes = [
    "  100 /Applications/PracticeLab Dev.app/Contents/MacOS/PracticeLab Dev",
    "  200 /Applications/PracticeLab.app/Contents/MacOS/PracticeLab",
    "  300 /Applications/PracticeLab.app/Contents/Frameworks/PracticeLab Helper.app/Contents/MacOS/PracticeLab Helper",
  ].join("\n");
  assert.equal(hasNormalMacAppProcess(processes, 100), true);
  assert.equal(hasNormalMacAppProcess(processes, 200), false);
  assert.equal(hasNormalMacAppProcess(processes.replace("  200 /Applications/PracticeLab.app/Contents/MacOS/PracticeLab\n", ""), 100), false);
});
