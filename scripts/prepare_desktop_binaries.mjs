import { chmodSync, copyFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ffmpegPath from "ffmpeg-static";
import ffprobe from "ffprobe-static";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const binDir = path.join(repositoryRoot, "desktop", "bin");
const executableSuffix = process.platform === "win32" ? ".exe" : "";

mkdirSync(binDir, { recursive: true });
const binaries = [
  [process.execPath, `node${executableSuffix}`],
  [ffmpegPath, `ffmpeg${executableSuffix}`],
  [ffprobe.path, `ffprobe${executableSuffix}`],
];

for (const [source, name] of binaries) {
  const destination = path.join(binDir, name);
  copyFileSync(source, destination);
  if (process.platform !== "win32") chmodSync(destination, 0o755);
}

process.stdout.write("Prepared bundled Node.js, FFmpeg, and FFprobe.\n");
