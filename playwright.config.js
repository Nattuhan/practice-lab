import { defineConfig } from "@playwright/test";
import path from "node:path";
import process from "node:process";

const python = process.env.PRACTICE_LAB_PYTHON || (
  process.platform === "win32"
    ? path.join(".venv", "Scripts", "python.exe")
    : path.join(".venv", "bin", "python")
);

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `"${python}" -m uvicorn main:app --host 127.0.0.1 --port 8765 --log-level warning --no-access-log`,
    url: "http://127.0.0.1:8765/healthz",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
