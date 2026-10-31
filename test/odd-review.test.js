import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, symlink, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// Dynamic imports keep each requested rule visible as its own RED result.
const files = () => import('../src/files.js');
const view = () => import('../src/browser.js');
async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'odd-view-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, 'odd', 'tasks'), { recursive: true });
  return root;
}
function harness(paths = ['odd/a.md', 'odd/b.md'], options = {}) {
  let closes = 0, renders = 0;
  const markdownInputs = [];
  const runtime = {
    matchesKey: (data, key) => data === key,
    truncateToWidth: (text, width, _ellipsis, pad) => text.slice(0, width).padEnd(pad ? width : 0),
    Markdown: class {
      constructor(text) { markdownInputs.push(text); this.text = text; }
      render(width) { return this.text.split('\n').flatMap(line => line.match(new RegExp(`.{1,${width}}`, 'gu')) || ['']); }
      invalidate() {}
    },
    Text: class {
      constructor(text) { this.text = text; }
      render(width) { return this.text.split('\n').flatMap(line => line.match(new RegExp(`.{1,${width}}`, 'gu')) || ['']); }
      invalidate() {}
    },
    getMarkdownTheme: () => ({}),
  };
  const theme = { fg: (_token, text) => text, bg: (_token, text) => text, bold: text => text };
  return {
    async create() {
      const { createBrowser } = await view();
      return createBrowser({ paths, read: async path => `${path}\n${Array.from({ length: 80 }, (_, i) => `line ${i}`).join('\n')}`, tui: { terminal: { rows: 18 }, requestRender() { renders++; } }, theme, done() { closes++; }, runtime, ...options });
    },
    markdownInputs,
    get closes() { return closes; }, get renders() { return renders; },
  };
}
const text = (component, width = 100) => component.render(width).join('\n');
const mouse = (type, x, y, wheelDelta) => ({ type, x, y, button: 'left', wheelDelta });

test('S2: registers odd-review, opens an overlay only in TUI mode', async () => {
  const { registerOddReview } = await import('../src/command.js');
  let command, calls = 0;
  registerOddReview({ registerCommand(name, definition) { assert.equal(name, 'odd-review'); command = definition; } }, () => ({}));
  assert.match(command.description, /read-only/i);
  for (const mode of ['rpc', 'json', 'print']) {
    const notices = [];
    await command.handler('', { mode, hasUI: mode === 'rpc', ui: { custom() { calls++; }, notify: (...args) => notices.push(args) } });
    assert.deepEqual(notices, mode === 'rpc' ? [['ODD Review requires interactive TUI mode.', 'warning']] : []);
  }
  assert.equal(calls, 0);
  await command.handler('', { mode: 'tui', cwd: '/not-read-by-mock', ui: { custom(factory, options) { calls++; assert.equal(options.overlay, true); assert.equal(options.overlayOptions.width, '100%'); } } });
  assert.equal(calls, 1);
});

test('S3: recursively discovers only regular ODD files in stable relative order, without writes', async t => {
  const root = await fixture(t);
  await writeFile(join(root, 'odd', 'z.txt'), 'Z');
  await writeFile(join(root, 'odd', 'tasks', 'a.md'), '# A');
  await writeFile(join(root, 'outside.md'), 'outside');
  const before = await readdir(root, { recursive: true });
  const { discoverFiles, readPreview } = await files();
  assert.deepEqual(await discoverFiles(root), { paths: ['odd/tasks/a.md', 'odd/z.txt'], errors: [] });
  assert.deepEqual(await readPreview(root, 'odd/tasks/a.md'), { content: '# A' });
  assert.deepEqual(await readdir(root, { recursive: true }), before);
  assert.equal(await readFile(join(root, 'odd', 'tasks', 'a.md'), 'utf8'), '# A');
});

test('S3: rejects escapes and symlink roots, directories and files (including replaced selections)', async t => {
  const root = await fixture(t);
  await writeFile(join(root, 'outside.md'), 'not previewable');
  await symlink(join(root, 'outside.md'), join(root, 'odd', 'link.md'));
  await symlink(root, join(root, 'odd', 'loop'));
  const { discoverFiles, readPreview } = await files();
  assert.deepEqual((await discoverFiles(root)).paths, []);
  for (const path of ['../outside.md', 'odd/../outside.md', join(root, 'outside.md'), 'odd/link.md', 'odd/loop/outside.md', 'odd/tasks']) {
    const result = await readPreview(root, path);
    assert.equal(result.content, undefined);
    assert.match(result.error, /^Cannot preview /);
  }
  await symlink(join(root, 'odd'), join(root, 'alias'));
  await mkdir(join(root, 'other'));
  await symlink(join(root, 'odd'), join(root, 'other', 'odd'));
  const result = await discoverFiles(join(root, 'other'));
  assert.deepEqual(result.paths, []);
  assert.match(result.errors.join(), /symlink/i);
  assert.equal(await readFile(join(root, 'outside.md'), 'utf8'), 'not previewable');
});

test('S3/S4: keyboard and mouse select files and reset the preview scroll', async () => {
  const h = harness(); const c = await h.create();
  assert.match(text(c), />   a.md/);
  c.handleInput('down'); await c.whenIdle();
  assert.match(text(c), />   b.md/);
  assert.match(text(c), /odd\/b.md/);
  c.handleInput('tab'); c.handleInput('down');
  c.handleMouse(mouse('click', 3, 4)); await c.whenIdle();
  assert.match(text(c), />   a.md/);
  assert.match(text(c), /line 0/);
  assert.ok(h.renders > 0);
});

test('S4: preview uses themed Markdown, plain content, and strips terminal control input', async () => {
  const h = harness(['odd/a.md', 'odd/b.txt'], { read: async path => path.endsWith('.md') ? '# Title\n**bold**\n\u001b[31mred\u0007' : 'plain <content>' });
  const c = await h.create();
  text(c);
  assert.deepEqual(h.markdownInputs, ['# Title\n**bold**\n[31mred']);
  c.handleInput('down'); await c.whenIdle();
  assert.match(text(c), /plain <content>/);
  assert.equal(h.markdownInputs.length, 1);
});

test('S4: preview keyboard and wheel scroll independently without changing selection', async () => {
  const h = harness(); const c = await h.create();
  text(c); c.handleInput('tab'); c.handleInput('pagedown');
  assert.doesNotMatch(text(c), /line 0\n/);
  assert.match(text(c), />   a.md/);
  c.handleInput('home'); assert.match(text(c), /line 0/);
  c.handleInput('tab'); c.handleMouse(mouse('wheel', 60, 4, 5));
  assert.doesNotMatch(text(c), /line 0\n/);
  assert.match(text(c), />   a.md/);
  c.handleInput('end'); assert.match(text(c), /line 79/);
});

test('S2-S4: clear empty, discovery error, preview error and empty-file states', async t => {
  const root = await fixture(t);
  const { discoverFiles } = await files();
  assert.deepEqual(await discoverFiles(join(root, 'missing')), { paths: [], errors: [] });
  assert.match(text(await harness([], { errors: [] }).create()), /No files found in odd\//);
  assert.match(text(await harness([], { errors: ['Cannot read odd/: EACCES'] }).create()), /Cannot read odd\/: EACCES/);
  assert.match(text(await harness(['odd/a.md'], { read: async () => { throw new Error('ENOENT'); } }).create()), /Cannot preview odd\/a.md: ENOENT/);
  assert.match(text(await harness(['odd/a.md'], { read: async () => '' }).create()), /Empty file/);
});

test('S2-S4: responsive fallback keeps both panes accessible via Tab and fits short terminals', async () => {
  const h = harness(); const c = await h.create();
  for (const width of [1, 8, 30, 59, 60, 100]) {
    const lines = c.render(width);
    assert.ok(lines.every(line => line.length <= width));
    assert.ok(lines.length <= 18);
  }
  assert.match(text(c, 30), />   a.md/);
  c.handleInput('tab');
  assert.match(text(c, 30), /line 0/);
  c.handleInput('tab'); assert.match(text(c, 30), />   a.md/);
});

test('S2: Escape and Ctrl+C close once and ignore late preview results', async () => {
  for (const key of ['escape', 'ctrl+c']) {
    let resolve;
    const h = harness(undefined, { read: path => path.endsWith('a.md') ? 'first' : new Promise(done => { resolve = done; }) });
    const c = await h.create();
    c.handleInput('down');
    await Promise.resolve();
    c.handleInput(key); c.handleInput(key);
    const renders = h.renders;
    resolve('late content'); await c.whenIdle();
    assert.equal(h.closes, 1);
    assert.equal(h.renders, renders);
  }
});

test('S7: fullscreen browser is a self-contained framed modal with tree navigation', async () => {
  const h = harness(['odd/tasks/odd-review.md', 'odd/notes.md']);
  const c = await h.create();
  const lines = c.render(100);

  assert.equal(lines.length, 18);
  assert.match(lines[0], /^╭.*ODD Review.*\[Tab Switch\].*\[Esc Close\].*╮$/);
  assert.match(lines[1], /^│.*Artifacts.*│.*Preview.*│$/);
  assert.match(lines[2], /^├.*┼.*┤$/);
  assert.match(lines.at(-2), /^│.*Tab.*navigate.*wheel.*scroll.*│$/);
  assert.match(lines.at(-1), /^╰.*╯$/);
  assert.match(lines.join('\n'), /odd\//);
  assert.match(lines.join('\n'), /tasks\//);
  assert.match(lines.join('\n'), /odd-review\.md/);
  assert.ok(lines.every(line => line.length === 100));
});

test('S7/S2: compact browser fits every terminal width', async () => {
  const c = await harness().create();
  for (let width = 1; width <= 100; width++) {
    for (const line of c.render(width)) {
      assert.ok(line.length <= width, `rendered ${line.length} columns at terminal width ${width}`);
    }
  }
});

test('S3/S4/S7: filesystem artifact names cannot inject terminal controls', async t => {
  const root = await fixture(t);
  const name = 'odd/a\u001b[31m.md';
  await writeFile(join(root, name), '# Safe');
  const before = await readFile(join(root, name));
  const { discoverFiles, readPreview } = await files();
  const { paths } = await discoverFiles(root);
  assert.deepEqual(paths, [name]);

  const c = await harness(paths, {
    read: async path => {
      const result = await readPreview(root, path);
      if (result.error) throw new Error(result.error);
      return result.content;
    },
  }).create();

  assert.doesNotMatch(text(c), /[\x00-\x08\x0b-\x1f\x7f-\x9f]/);
  assert.deepEqual(await readFile(join(root, name)), before);
});

test('S3/S4/S7: scrolled tree clicks and pane wheels retain routing', async () => {
  const paths = Array.from({ length: 30 }, (_, i) => `odd/tasks/f${String(i).padStart(2, '0')}.md`);
  let selected;
  const c = await harness(paths, {
    read: async path => {
      selected = path;
      return Array.from({ length: 90 }, (_, i) => `CONTENT-${i}`).join('\n');
    },
  }).create();

  c.render(100);
  c.handleInput('end');
  await c.whenIdle();

  const row = c.render(100).findIndex(line => line.includes('f28.md'));
  assert.ok(row >= 3);
  c.handleMouse(mouse('click', 4, row));
  await c.whenIdle();
  assert.equal(selected, paths[28]);

  c.render(100);
  c.handleMouse(mouse('wheel', 4, 5, -2));
  await c.whenIdle();
  assert.equal(selected, paths[26]);

  c.render(100);
  c.handleMouse(mouse('wheel', 80, 5, 5));
  assert.match(text(c), /CONTENT-5/);
  assert.equal(selected, paths[26]);

  c.handleInput('home');
  assert.match(text(c), /CONTENT-0/);
});

test('MR1: top border and help badges are mouse-reactive', async () => {
  const h = harness(); const c = await h.create();
  const lines = c.render(100);
  const click = (text, line, row) => {
    const x = line.indexOf(text);
    assert.ok(x >= 0, `${text} is rendered`);
    c.handleMouse(mouse('click', x + 1, row));
  };

  click('[Tab Switch]', lines[0], 0);
  assert.match(text(c), /◆ Preview/);
  click('[Tab Switch]', c.render(100)[0], 0);
  assert.match(text(c), /◆ Artifacts/);

  const helpRow = lines.length - 2;
  click('Tab switch', lines[helpRow], helpRow);
  assert.match(text(c), /◆ Preview/);
  click('Esc close', c.render(100)[helpRow], helpRow);
  assert.equal(h.closes, 1);
});

test('MR2: the top close badge closes exactly once', async () => {
  const h = harness(); const c = await h.create();
  const line = c.render(100)[0];
  const x = line.indexOf('[Esc Close]') + 2;
  c.handleMouse(mouse('click', x, 0));
  c.handleMouse(mouse('click', x, 0));
  assert.equal(h.closes, 1);
});

test('MR3: clicking a directory collapses and expands it, keeping selection visible', async () => {
  const h = harness(['odd/tasks/a.md', 'odd/notes.md']); const c = await h.create();
  let lines = c.render(100);
  const dirRow = lines => lines.findIndex((line, index) => index >= 3 && line.includes('▾ tasks/'));
  const row = dirRow(lines);
  assert.ok(row >= 3);
  const x = lines[row].indexOf('tasks/') + 1;

  c.handleMouse(mouse('click', x, row)); await c.whenIdle();
  let collapsed = c.render(100);
  assert.match(collapsed[row], /▸/);
  assert.doesNotMatch(collapsed.join('\n'), /a\.md/);
  assert.match(collapsed.join('\n'), />   notes\.md/);

  c.handleMouse(mouse('click', x, row)); await c.whenIdle();
  lines = c.render(100);
  assert.match(lines[row], /▾ tasks\//);
  assert.match(lines.join('\n'), /a\.md/);
});

test('MR4: keyboard navigation skips files hidden by a collapsed directory', async () => {
  const h = harness(['odd/tasks/a.md', 'odd/tasks/b.md', 'odd/z.md']); const c = await h.create();
  const lines = c.render(100);
  const row = lines.findIndex((line, index) => index >= 3 && line.includes('▾ tasks/'));
  assert.ok(row >= 3);
  c.handleMouse(mouse('click', lines[row].indexOf('tasks/') + 1, row));
  await c.whenIdle();
  assert.match(text(c), />   z\.md/);
  c.handleInput('up');
  assert.match(text(c), />   z\.md/);
});

test('MR5: Home and End target the first and last visible file', async () => {
  const h = harness(['odd/tasks/a.md', 'odd/tasks/b.md', 'odd/z.md']); const c = await h.create();
  const lines = c.render(100);
  const row = lines.findIndex((line, index) => index >= 3 && line.includes('▾ tasks/'));
  c.handleMouse(mouse('click', lines[row].indexOf('tasks/') + 1, row));
  await c.whenIdle();
  c.handleInput('home');
  assert.match(text(c), />   z\.md/);
  c.handleInput('end');
  assert.match(text(c), />   z\.md/);
});
