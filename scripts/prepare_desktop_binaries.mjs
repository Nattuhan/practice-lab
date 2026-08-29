import { chmodSync, copyFileSync, mkdirSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ffmpegPath from "ffmpeg-static";
import ffprobe from "@ffprobe-installer/ffprobe";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const binDir = path.join(repositoryRoot, "desktop", "bin");
const executableSuffix = process.platform === "win32" ? ".exe" : "";

mkdirSync(binDir, { recursive: true });
rmSync(path.join(binDir, `node${executableSuffix}`), { force: true });
const binaries = [
  [ffmpegPath, `ffmpeg${executableSuffix}`],
  [ffprobe.path, `ffprobe${executableSuffix}`],
];

for (const [source, name] of binaries) {
  const destination = path.join(binDir, name);
  copyFileSync(source, destination);
  if (process.platform !== "win32") chmodSync(destination, 0o755);
}

if (process.platform === "darwin") {
  for (const name of ["ffmpeg", "ffprobe"]) {
    const executable = path.join(binDir, name);
    const description = execFileSync("file", [executable], { encoding: "utf8" });
    if (!description.includes("arm64")) {
      throw new Error(`${name} is not an Apple Silicon executable: ${description.trim()}`);
    }
  }
}

process.stdout.write("Prepared bundled FFmpeg and FFprobe. Electron provides the JavaScript runtime.\n");
