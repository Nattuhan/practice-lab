// A signed app can still be unable to update: directory-only builds skip
// electron-builder's DMG/ZIP publisher hook that normally writes this file.
const fs = require('node:fs');
const yaml = require('js-yaml');

function validateUpdateConfiguration(config) {
  if (!config || config.provider !== 'github' || config.owner !== 'Nattuhan' || config.repo !== 'practice-lab') {
    throw new Error('Update configuration must point to Nattuhan/practice-lab on GitHub');
  }
  if (config.updaterCacheDirName !== 'practice-lab-updater') {
    throw new Error('Update configuration has an unexpected updater cache directory');
  }
  if (config.host && config.host !== 'github.com') throw new Error('Unexpected update host');
  if (config.channel && config.channel !== 'latest') throw new Error('Unexpected update channel');
  return config;
}

function readUpdateConfiguration(file) {
  return validateUpdateConfiguration(yaml.load(fs.readFileSync(file, 'utf8')));
}

function writeUpdateConfiguration(file, publish, updaterCacheDirName) {
  // Only copy public feed fields. Publisher credentials must never enter an app.
  const config = validateUpdateConfiguration({
    provider: publish?.provider, owner: publish?.owner, repo: publish?.repo, updaterCacheDirName,
  });
  fs.writeFileSync(file, yaml.dump(config));
}

if (require.main === module) {
  try {
    if (process.argv[2] !== '--verify' || !process.argv[3]) throw new Error('Usage: macos-update-config.cjs --verify app-update.yml');
    readUpdateConfiguration(process.argv[3]);
    console.log('Update feed configuration verified');
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
module.exports = { validateUpdateConfiguration, readUpdateConfiguration, writeUpdateConfiguration };
