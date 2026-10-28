import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const readJson = async path => JSON.parse(await readFile(path, 'utf8'));

test('S5/S6: package is public, MIT licensed, minimal, and installable from npm or GitHub', async () => {
  const pkg = await readJson(new URL('../package.json', import.meta.url));

  assert.equal(pkg.name, '@oniricosistemas/odd-view');
  assert.equal(pkg.private, undefined);
  assert.equal(pkg.license, 'MIT');
  assert.equal(pkg.repository?.url, 'git+https://github.com/oniricosistemas/odd-view.git');
  assert.equal(pkg.homepage, 'https://github.com/oniricosistemas/odd-view#readme');
  assert.equal(pkg.bugs?.url, 'https://github.com/oniricosistemas/odd-view/issues');
  assert.deepEqual(pkg.files, ['extensions', 'src', 'README.md', 'LICENSE']);
  assert.deepEqual(pkg.publishConfig, { access: 'public', provenance: true });
  assert.equal(pkg.scripts?.prepack, 'npm run check');
  assert.equal(pkg.scripts?.['release:check'], 'npm run check && npm pack --dry-run');

  const readme = await readFile(new URL('../README.md', import.meta.url), 'utf8');
  assert.match(readme, /gentle-shell --extension \.\/extensions\/odd-review\.ts/);
  assert.match(readme, /gentle-shell install npm:@oniricosistemas\/odd-view/);
  assert.match(readme, /gentle-shell install git:github\.com\/oniricosistemas\/odd-view@v\$\{VERSION\}/);

  assert.match(await readFile(new URL('../LICENSE', import.meta.url), 'utf8'), /^MIT License/);
  assert.match(await readFile(new URL('../RELEASING.md', import.meta.url), 'utf8'), /npm publish --access public --provenance/);
});
