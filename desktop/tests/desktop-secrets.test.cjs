const assert = require("node:assert/strict");
const test = require("node:test");

const { createDesktopSecretsStore } = require("../desktop-secrets.cjs");

test("R2秘密鍵は同じ起動中に一度だけ復号する", () => {
  let decryptCalls = 0;
  const fs = {
    existsSync: () => true,
    readFileSync: () => Buffer.from("encrypted"),
  };
  const safeStorage = {
    isEncryptionAvailable: () => true,
    decryptString: () => {
      decryptCalls += 1;
      return JSON.stringify({ r2SecretAccessKey: "secret" });
    },
  };
  const store = createDesktopSecretsStore({ safeStorage, fs, filePath: () => "secrets.bin" });

  assert.equal(store.read().r2SecretAccessKey, "secret");
  assert.equal(store.read().r2SecretAccessKey, "secret");
  assert.equal(decryptCalls, 1);
});

test("R2秘密鍵を更新すると復号せず新しい値を再利用する", () => {
  let written = null;
  const fs = {
    existsSync: () => true,
    writeFileSync: (_file, value) => { written = value; },
  };
  const safeStorage = {
    isEncryptionAvailable: () => true,
    encryptString: value => Buffer.from(value),
    decryptString: () => { throw new Error("復号は不要"); },
  };
  const store = createDesktopSecretsStore({ safeStorage, fs, filePath: () => "secrets.bin" });

  store.write({ r2SecretAccessKey: "next" });
  assert.equal(JSON.parse(written.toString()).r2SecretAccessKey, "next");
  assert.equal(store.read().r2SecretAccessKey, "next");
});

test("保存済み判定ではR2秘密鍵を復号しない", () => {
  let decryptCalls = 0;
  const fs = {
    existsSync: () => true,
  };
  const safeStorage = {
    isEncryptionAvailable: () => true,
    decryptString: () => {
      decryptCalls += 1;
      return JSON.stringify({ r2SecretAccessKey: "secret" });
    },
  };
  const store = createDesktopSecretsStore({ safeStorage, fs, filePath: () => "secrets.bin" });

  assert.equal(store.hasStored(), true);
  assert.equal(decryptCalls, 0);
});
