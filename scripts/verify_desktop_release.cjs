#!/usr/bin/env node

const { execFileSync } = require("node:child_process");

function fail(message) {
  console.error(`Release verification failed: ${message}`);
  process.exit(1);
}

function run(command, args) {
  try {
    return execFileSync(command, args, { encoding: "utf8" }).trim();
  } catch (error) {
    const detail = error.stderr?.toString().trim() || error.message;
    fail(`${command} ${args.join(" ")}\n${detail}`);
  }
}

const version = process.argv[2]?.replace(/^v/, "");
const runId = process.argv[3];
if (!version || !runId) {
  fail("usage: node scripts/verify_desktop_release.cjs X.Y.Z RUN_ID");
}

const tag = `v${version}`;
const tagCommit = run("git", ["rev-list", "-n", "1", tag]);
const headCommit = run("git", ["rev-parse", "HEAD"]);
const originMain = run("git", ["rev-parse", "origin/main"]);
if (tagCommit !== headCommit || tagCommit !== originMain) {
  fail(`tag, HEAD, and origin/main differ (${tagCommit}, ${headCommit}, ${originMain})`);
}

const runInfo = JSON.parse(
  run("gh", ["run", "view", runId, "--json", "status,conclusion,headSha,jobs,url"]),
);
if (runInfo.status !== "completed" || runInfo.conclusion !== "success") {
  fail(`workflow ${runId} is ${runInfo.status}/${runInfo.conclusion || "pending"}`);
}
if (runInfo.headSha !== tagCommit) {
  fail(`workflow head ${runInfo.headSha} does not match ${tag} at ${tagCommit}`);
}

const requiredJobs = ["windows-nvidia", "macos-apple-silicon", "release-metadata"];
for (const jobName of requiredJobs) {
  const job = runInfo.jobs.find((candidate) => candidate.name === jobName);
  if (!job || job.status !== "completed" || job.conclusion !== "success") {
    fail(`required job ${jobName} did not succeed`);
  }
}

const release = JSON.parse(
  run("gh", [
    "release",
    "view",
    tag,
    "--json",
    "isDraft,isPrerelease,tagName,targetCommitish,url,assets",
  ]),
);
if (release.isDraft || release.isPrerelease) {
  fail(`${tag} is not a public stable release`);
}
if (release.tagName !== tag || release.targetCommitish !== tagCommit) {
  fail(`release target does not match ${tag} at ${tagCommit}`);
}

const requiredAssets = [
  `PracticeLab-Setup-${version}.exe`,
  `PracticeLab-Setup-${version}.exe.blockmap`,
  "latest.yml",
  `PracticeLab-${version}-arm64.dmg`,
  `PracticeLab-${version}-arm64.zip`,
  "latest-mac.yml",
  `PracticeLab-Windows-CPU-${version}.zip`,
  `PracticeLab-Analysis-macOS-arm64-${version}.zip`,
  `PracticeLab-Score-Windows-${version}.zip`,
  `PracticeLab-Score-macOS-arm64-${version}.zip`,
  `PracticeLab-Notarized-Mac-${version}.sha256`,
  "PracticeLab-SHA256SUMS.txt",
];
const assets = new Map(release.assets.map((asset) => [asset.name, asset]));
for (const assetName of requiredAssets) {
  const asset = assets.get(assetName);
  if (!asset || asset.state !== "uploaded" || asset.size <= 0) {
    fail(`required asset is missing or incomplete: ${assetName}`);
  }
}

const status = run("git", ["status", "--short"]);
if (status) fail("working tree is not clean");

console.log(`Verified ${tag} at ${tagCommit}`);
console.log(`Workflow: ${runInfo.url}`);
console.log(`Release: ${release.url}`);
console.log(`Assets: ${requiredAssets.length}/${requiredAssets.length}`);
