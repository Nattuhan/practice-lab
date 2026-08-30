function createDesktopSecretsStore({ safeStorage, fs, filePath }) {
  let cachedSecrets = null;

  const read = () => {
    if (cachedSecrets !== null) return cachedSecrets;
    try {
      const file = filePath();
      if (!safeStorage.isEncryptionAvailable() || !fs.existsSync(file)) {
        cachedSecrets = {};
      } else {
        const parsed = JSON.parse(safeStorage.decryptString(fs.readFileSync(file)));
        cachedSecrets = parsed && typeof parsed === "object" ? parsed : {};
      }
    } catch {
      cachedSecrets = {};
    }
    return cachedSecrets;
  };

  const write = secrets => {
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error("このPCでは認証情報を安全に保存できません");
    }
    const nextSecrets = { ...secrets };
    fs.writeFileSync(filePath(), safeStorage.encryptString(JSON.stringify(nextSecrets)));
    cachedSecrets = nextSecrets;
  };

  const clear = () => {
    const file = filePath();
    if (fs.existsSync(file)) fs.rmSync(file);
    cachedSecrets = {};
  };

  return { read, write, clear };
}

module.exports = { createDesktopSecretsStore };
