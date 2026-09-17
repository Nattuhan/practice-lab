const { execFile } = require("node:child_process");
const { promisify } = require("node:util");
const run = promisify(execFile);
const unknown = () => ({ transport: "unknown", name: "" });

function parseMacAudioOutput(data) {
  const visit = items => {
    for (const item of items || []) {
      // A connected headset need not be the active output. Check the default
      // media output, not the separate system/alert output or device name.
      if (item.coreaudio_default_audio_output_device === "spaudio_yes") {
        const type = item.coreaudio_device_transport || "";
        return {
          name: String(item._name || ""),
          transport: type === "coreaudio_device_type_builtin" ? "builtin"
            : /^coreaudio_device_type_bluetooth(?:le)?$/.test(type) ? "bluetooth" : "other",
        };
      }
      const nested = visit(item._items);
      if (nested) return nested;
    }
    return null;
  };
  return visit(data?.SPAudioDataType) || unknown();
}

function createAudioOutputReader({ platform = process.platform, execute = run, now = Date.now } = {}) {
  let pending, cached = unknown(), checkedAt = -Infinity;
  return async () => {
    if (platform !== "darwin") return unknown();
    if (pending) return pending;
    if (now() - checkedAt < 1000) return cached;
    pending = (async () => {
      try {
        const { stdout } = await execute("/usr/sbin/system_profiler", ["SPAudioDataType", "-json"], {
          timeout: 4000, maxBuffer: 1024 * 1024,
        });
        cached = parseMacAudioOutput(JSON.parse(stdout));
      } catch {
        // Never keep a stale Bluetooth result after detection fails.
        cached = unknown();
      }
      checkedAt = now();
      return cached;
    })();
    try { return await pending; } finally { pending = null; }
  };
}

module.exports = { createAudioOutputReader, parseMacAudioOutput };
