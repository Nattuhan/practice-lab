const packageJson = require("../package.json");

module.exports = {
  ...packageJson.build,
  appId: "jp.nattuhan.practicelab.dev",
  productName: "PracticeLab Dev",
  directories: {
    ...packageJson.build.directories,
    output: "desktop/dist/dev-installer",
  },
  mac: {
    ...packageJson.build.mac,
    target: [{ target: "dir", arch: ["arm64"] }],
    artifactName: "PracticeLab-Dev-${version}-${arch}.${ext}",
  },
};
