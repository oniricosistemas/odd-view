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

test('S9: issue forms cover bugs and features with existing labels and manual approval policy', async () => {
  const bugForm = await readFile(new URL('../.github/ISSUE_TEMPLATE/bug_report.yml', import.meta.url), 'utf8');
  const featureForm = await readFile(new URL('../.github/ISSUE_TEMPLATE/feature_request.yml', import.meta.url), 'utf8');
  const issueConfig = await readFile(new URL('../.github/ISSUE_TEMPLATE/config.yml', import.meta.url), 'utf8');
  const contributing = await readFile(new URL('../CONTRIBUTING.md', import.meta.url), 'utf8');
  const labelManifest = await readFile(new URL('../.github/labels.yml', import.meta.url), 'utf8');

  assert.match(bugForm, /^name: Bug Report/m);
  assert.match(bugForm, /labels:\s*\["bug"\]/);
  assert.match(bugForm, /label: Steps to reproduce/);
  assert.match(bugForm, /label: Expected behavior/);
  assert.match(bugForm, /label: Actual behavior/);
  assert.match(featureForm, /^name: Feature Request/m);
  assert.match(featureForm, /labels:\s*\["enhancement"\]/);
  assert.match(featureForm, /label: Problem to solve/);
  assert.match(featureForm, /label: Proposed outcome/);
  assert.match(issueConfig, /blank_issues_enabled:\s*true/);
  assert.match(labelManifest, /name:\s*status\/approved/);
  assert.match(labelManifest, /name:\s*type:feature/);
  assert.match(labelManifest, /name:\s*type:bug/);
  assert.match(labelManifest, /never applied automatically/i);
  assert.match(contributing, /status\/approved/);
  assert.match(contributing, /manual/i);
  assert.match(contributing, /never.*automatic|not.*automatic/i);
  assert.doesNotMatch(bugForm + featureForm, /status\/approved|auto.?approv/i);
  const prTemplate = await readFile(new URL('../.github/PULL_REQUEST_TEMPLATE.md', import.meta.url), 'utf8');
  assert.match(prTemplate, /Linked issue/);
  assert.match(prTemplate, /Select exactly one type/);
  assert.match(prTemplate, /status\/approved/);
});
