import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const brandImage = 'https://raw.githubusercontent.com/Gentleman-Programming/gentle-ai/main/docs/assets/brand/built-with-gentle-ai.png';

test('S8: README explains odd-view installation and ends with the Gentle AI brand', async () => {
  const readme = await readFile(new URL('../README.md', import.meta.url), 'utf8');

  assert.match(readme, /Si no quieres salir de la terminal para explorar los archivos que crea ODD, tenemos la solución/i);
  assert.match(readme, /gentle-shell --extension \.\/extensions\/odd-review\.ts/);
  assert.match(readme, /gentle-shell install npm:odd-view/);
  assert.match(readme, /gentle-shell install git:github\.com\/oniricosistemas\/odd-view@v\$\{VERSION\}/);
  assert.match(readme, /\/odd-review/);
  assert.match(readme, /## creado con:/);
  assert.match(readme, new RegExp(`<img[^>]+src="${brandImage.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"[^>]+width="(?:2[0-9]{2}|300)"`));
  assert.match(readme.trim(), /<\/p>$/);
});
