const {
  createCipheriv,
  createDecipheriv,
  randomBytes,
  scryptSync,
} = require("crypto");

const FORMAT = "jp.nattuhan.practicelab.cloud-connection";
const VERSION = 1;
const AAD = Buffer.from(`${FORMAT}:v${VERSION}`, "utf8");
const MAX_FILE_BYTES = 64 * 1024;
const SCRYPT_OPTIONS = Object.freeze({ N: 65536, r: 8, p: 1, maxmem: 128 * 1024 * 1024 });
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;

function generateTransferCode() {
  return randomBytes(16).toString("hex").toUpperCase().match(/.{1,4}/g).join("-");
}

function normalizeTransferCode(value) {
  const normalized = String(value || "").replace(/[\s-]/g, "").toUpperCase();
  if (!/^[0-9A-F]{32}$/.test(normalized)) throw new Error("復号コードの形式が正しくありません");
  return normalized;
}

function cleanString(value, name, maxLength, { required = false } = {}) {
  const text = String(value || "").trim();
  if ((required && !text) || text.length > maxLength || CONTROL_CHARACTERS.test(text)) {
    throw new Error(`${name}が正しくありません`);
  }
  return text;
}

function cleanHttpsUrl(value, name, { required = false } = {}) {
  const text = cleanString(value, name, 2048, { required });
  if (!text) return "";
  let url;
  try {
    url = new URL(text);
  } catch {
    throw new Error(`${name}が正しくありません`);
  }
  if (url.protocol !== "https:" || url.username || url.password) throw new Error(`${name}はHTTPS URLにしてください`);
  return text.replace(/\/$/, "");
}

function sanitizeCloudConnection(input = {}) {
  const bucket = cleanString(input.bucket, "R2バケット名", 64, { required: true });
  if (/[\\/]/.test(bucket)) throw new Error("R2バケット名が正しくありません");
  const accountId = cleanString(input.accountId, "CloudflareアカウントID", 64);
  if (accountId && !/^[0-9a-f]{32}$/i.test(accountId)) throw new Error("CloudflareアカウントIDが正しくありません");
  const endpointUrl = cleanHttpsUrl(input.endpointUrl, "S3互換エンドポイント");
  if (!accountId && !endpointUrl) throw new Error("CloudflareアカウントIDまたはエンドポイントが必要です");
  const prefix = cleanString(input.prefix || "sessions", "保存先プレフィックス", 128, { required: true })
    .replace(/^\/+|\/+$/g, "");
  if (!prefix || prefix.split("/").some(part => !part || part === "." || part === "..") || prefix.includes("\\")) {
    throw new Error("保存先プレフィックスが正しくありません");
  }
  return {
    enabled: true,
    bucket,
    accountId,
    endpointUrl,
    publicBaseUrl: cleanHttpsUrl(input.publicBaseUrl, "公開URL"),
    prefix,
    accessKeyId: cleanString(input.accessKeyId, "アクセスキーID", 256, { required: true }),
    secretAccessKey: cleanString(input.secretAccessKey, "シークレットアクセスキー", 1024, { required: true }),
  };
}

function createConnectionFile(cloud, code = generateTransferCode()) {
  const normalizedCode = normalizeTransferCode(code);
  const payload = sanitizeCloudConnection(cloud);
  const salt = randomBytes(16);
  const iv = randomBytes(12);
  const key = scryptSync(normalizedCode, salt, 32, SCRYPT_OPTIONS);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  cipher.setAAD(AAD);
  const ciphertext = Buffer.concat([
    cipher.update(JSON.stringify(payload), "utf8"),
    cipher.final(),
  ]);
  const document = {
    format: FORMAT,
    version: VERSION,
    kdf: {
      name: "scrypt",
      salt: salt.toString("base64"),
      N: SCRYPT_OPTIONS.N,
      r: SCRYPT_OPTIONS.r,
      p: SCRYPT_OPTIONS.p,
    },
    cipher: {
      name: "aes-256-gcm",
      iv: iv.toString("base64"),
      tag: cipher.getAuthTag().toString("base64"),
    },
    ciphertext: ciphertext.toString("base64"),
  };
  return { code, contents: `${JSON.stringify(document, null, 2)}\n` };
}

function decodeBase64(value, name, expectedBytes = null) {
  if (typeof value !== "string" || !/^[A-Za-z0-9+/]*={0,2}$/.test(value)) throw new Error(`${name}が正しくありません`);
  const buffer = Buffer.from(value, "base64");
  if (expectedBytes !== null && buffer.length !== expectedBytes) throw new Error(`${name}が正しくありません`);
  return buffer;
}

function openConnectionFile(contents, code) {
  if (typeof contents !== "string" || Buffer.byteLength(contents, "utf8") > MAX_FILE_BYTES) {
    throw new Error("接続ファイルが大きすぎます");
  }
  let document;
  try {
    document = JSON.parse(contents);
  } catch {
    throw new Error("接続ファイルの形式が正しくありません");
  }
  if (
    !document || document.format !== FORMAT || document.version !== VERSION
    || document.kdf?.name !== "scrypt" || document.cipher?.name !== "aes-256-gcm"
    || document.kdf.N !== SCRYPT_OPTIONS.N || document.kdf.r !== SCRYPT_OPTIONS.r || document.kdf.p !== SCRYPT_OPTIONS.p
  ) {
    throw new Error("対応していない接続ファイルです");
  }
  const normalizedCode = normalizeTransferCode(code);
  const salt = decodeBase64(document.kdf.salt, "ソルト", 16);
  const iv = decodeBase64(document.cipher.iv, "初期化ベクトル", 12);
  const tag = decodeBase64(document.cipher.tag, "認証タグ", 16);
  const ciphertext = decodeBase64(document.ciphertext, "暗号文");
  if (!ciphertext.length || ciphertext.length > MAX_FILE_BYTES) throw new Error("暗号文が正しくありません");
  try {
    const key = scryptSync(normalizedCode, salt, 32, SCRYPT_OPTIONS);
    const decipher = createDecipheriv("aes-256-gcm", key, iv);
    decipher.setAAD(AAD);
    decipher.setAuthTag(tag);
    const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");
    return sanitizeCloudConnection(JSON.parse(plaintext));
  } catch (error) {
    if (/が正しくありません|HTTPS URL|必要です/.test(error.message)) throw error;
    throw new Error("復号コードが違うか、接続ファイルが改ざんされています");
  }
}

module.exports = {
  FORMAT,
  MAX_FILE_BYTES,
  createConnectionFile,
  generateTransferCode,
  normalizeTransferCode,
  openConnectionFile,
  sanitizeCloudConnection,
};
