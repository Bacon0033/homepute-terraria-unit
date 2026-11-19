import { readFileSync, writeFileSync } from 'node:fs';

const templatePath = 'release/manifest.template.json';
const template = JSON.parse(readFileSync(templatePath, 'utf8'));
const published = JSON.parse(readFileSync('homepute.unit.json', 'utf8'));
if (template.unit.id !== published.unit.id) throw new Error('Marketplace unit identity changed');

function versionParts(version) {
  if (!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)) throw new Error('Expected a stable release version');
  return version.split('.').map(part => BigInt(part));
}
const next = versionParts(template.unit.version);
const current = versionParts(published.unit.version);
const difference = next.findIndex((part, i) => part !== current[i]);
if (difference < 0) {
  next[2]++;
  template.unit.version = next.join('.');
  writeFileSync(templatePath, JSON.stringify(template, null, 2) + '\n');
} else if (next[difference] < current[difference]) {
  throw new Error('The release template is older than the published marketplace version');
}
console.log('tag=' + template.unit.version);
