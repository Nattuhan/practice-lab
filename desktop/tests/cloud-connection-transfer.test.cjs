const assert = require("node:assert/strict");
const test = require("node:test");

const {
  MAX_FILE_BYTES,
  createConnectionFile,
  openConnectionFile,
} = require("../cloud-connection-transfer.cjs");

const cloud = {
  enabled: true,
  bucket: "practice-lab",
  accountId: "",
  endpointUrl: "https://account.r2.cloudflarestorage.com",
  publicBaseUrl: "https://assets.example.com",
  prefix: "sessions",
  accessKeyId: "access-key",
  secretAccessKey: "secret-key",
};

test("R2接続情報を暗号化ファイルへ書き出して復号できる", () => {
  const code = "0123-4567-89AB-CDEF-0123-4567-89AB-CDEF";
  const exported = createConnectionFile(cloud, code);
  const document = JSON.parse(exported.contents);

  assert.equal(exported.code, code);
  assert.equal(exported.contents.includes(cloud.secretAccessKey), false);
  assert.equal(document.cipher.name, "aes-256-gcm");
  assert.deepEqual(openConnectionFile(exported.contents, code), cloud);
});

test("誤ったコードと改ざんされた暗号文を拒否する", () => {
  const code = "0123-4567-89AB-CDEF-0123-4567-89AB-CDEF";
  const exported = createConnectionFile(cloud, code);
  assert.throws(
    () => openConnectionFile(exported.contents, "FFFF-FFFF-FFFF-FFFF-FFFF-FFFF-FFFF-FFFF"),
    /改ざん/,
  );

  const document = JSON.parse(exported.contents);
  const ciphertext = Buffer.from(document.ciphertext, "base64");
  ciphertext[0] ^= 1;
  document.ciphertext = ciphertext.toString("base64");
  assert.throws(() => openConnectionFile(JSON.stringify(document), code), /改ざん/);
});

test("危険なURL・プレフィックスと巨大ファイルを拒否する", () => {
  assert.throws(
    () => createConnectionFile({ ...cloud, endpointUrl: "http://example.com" }),
    /HTTPS/,
  );
  assert.throws(
    () => createConnectionFile({ ...cloud, prefix: "sessions/../secret" }),
    /プレフィックス/,
  );
  assert.throws(
    () => openConnectionFile("x".repeat(MAX_FILE_BYTES + 1), "0123-4567-89AB-CDEF-0123-4567-89AB-CDEF"),
    /大きすぎます/,
  );
});
