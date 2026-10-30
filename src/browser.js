// State is unstyled; all theme-dependent output is rebuilt on invalidation.
const clean = text => String(text).replace(/[\x00-\x08\x0b-\x1f\x7f-\x9f]/g, '').replace(/\t/g, '    ');
const label = text => clean(text).replace(/\n/g, ' ');
const clamp = (value, max) => Math.max(0, Math.min(value, Math.max(0, max)));

export function browserLayout(width, rows, focus) {
  const height = Math.max(1, rows);
  const inner = Math.max(0, width - 2);
  const narrow = width < 60;
  const available = Math.max(0, inner - (narrow ? 0 : 1));
  const left = narrow ? (focus === 'files' ? inner : 0) : Math.max(22, Math.floor(available * 0.3));
  return {
    width,
    height,
    inner,
    body: Math.max(0, height - 5),
    narrow,
    left,
    right: narrow ? (focus === 'preview' ? inner : 0) : Math.max(0, available - left),
  };
}

function treeRows(paths) {
  const rows = [];
  const directories = new Set();
  paths.forEach((path, fileIndex) => {
    const parts = path.split('/');
    for (let depth = 0; depth < parts.length - 1; depth++) {
      const directory = parts.slice(0, depth + 1).join('/');
      if (!directories.has(directory)) {
        directories.add(directory);
        rows.push({ kind: 'directory', label: `${'  '.repeat(depth)}▾ ${label(parts[depth])}/` });
      }
    }
    rows.push({ kind: 'file', fileIndex, label: `${'  '.repeat(Math.max(0, parts.length - 1))}${label(parts.at(-1))}` });
  });
  return rows;
}

/** A fresh, read-only interaction. Runtime adapters are the host's shipped TUI components. */
export async function createBrowser({ paths, errors = [], read, tui, theme, done, runtime }) {
  const { Markdown, Text, getMarkdownTheme, truncateToWidth, matchesKey } = runtime;
  const tree = treeRows(paths);
  let selected = 0, listTop = 0, previewTop = 0, focus = 'files';
  let content = '', failure = '', loading = false, pending = Promise.resolve(), generation = 0, closed = false;
  let preview, layout, previewLines = [];
  const fit = (text, width) => width > 0 ? truncateToWidth(text, width, '', true) : '';
  const request = () => { if (!closed) tui.requestRender(); };
  const maxScroll = () => Math.max(0, previewLines.length - (layout?.body || 1));
  const selectedTreeRow = () => Math.max(0, tree.findIndex(row => row.fileIndex === selected));

  function load() {
    const version = ++generation;
    content = ''; failure = ''; preview = undefined; previewTop = 0;
    if (!paths.length) return;
    loading = true;
    const path = paths[selected];
    pending = Promise.resolve().then(() => read(path)).then(value => {
      if (closed || version !== generation) return;
      content = clean(value);
    }, error => {
      if (closed || version !== generation) return;
      failure = clean(`Cannot preview ${path}: ${error.message}`);
    }).then(() => {
      if (closed || version !== generation) return;
      loading = false; preview = undefined; request();
    });
  }
  function select(index) {
    const next = clamp(index, paths.length - 1);
    if (next !== selected) { selected = next; load(); }
    request();
  }
  function scroll(delta) { previewTop = clamp(previewTop + delta, maxScroll()); request(); }
  function close() { if (!closed) { closed = true; generation++; done(); } }

  const component = {
    // Useful for hosts/tests waiting for the current selection without polling state.
    whenIdle: () => pending,
    dispose() { closed = true; generation++; },
    invalidate() { preview = undefined; previewLines = []; },
    handleInput(data) {
      if (closed) return;
      const key = name => matchesKey(data, name);
      if (key('escape') || key('ctrl+c')) { close(); return; }
      if (key('tab') || key('shift+tab')) {
        focus = focus === 'files' ? 'preview' : 'files'; request(); return;
      }
      if (focus === 'files') {
        if (key('up')) select(selected - 1);
        else if (key('down')) select(selected + 1);
        else if (key('pageup')) select(selected - (layout?.body || 1));
        else if (key('pagedown')) select(selected + (layout?.body || 1));
        else if (key('home')) select(0);
        else if (key('end')) select(paths.length - 1);
        else if (key('return') || key('right')) { focus = 'preview'; request(); }
      } else {
        if (key('up')) scroll(-1);
        else if (key('down')) scroll(1);
        else if (key('pageup')) scroll(-(layout?.body || 1));
        else if (key('pagedown') || key('space')) scroll(layout?.body || 1);
        else if (key('home')) { previewTop = 0; request(); }
        else if (key('end')) { previewTop = maxScroll(); request(); }
        else if (key('left')) { focus = 'files'; request(); }
      }
    },
    handleMouse(event) {
      if (closed || !layout || event.y < 3 || event.y >= 3 + layout.body || event.x < 0 || event.x >= layout.width) return;
      const pane = layout.narrow ? focus : event.x <= layout.left ? 'files' : event.x >= layout.left + 2 ? 'preview' : null;
      if (!pane) return;
      if (event.type === 'wheel') {
        focus = pane;
        if (pane === 'files') select(selected + Math.trunc(event.wheelDelta || 0));
        else scroll(Math.trunc(event.wheelDelta || 0));
        return { handled: true, focus: true, render: true };
      }
      if (event.type === 'click' && event.button === 'left') {
        focus = pane;
        if (pane === 'files') {
          const row = tree[listTop + event.y - 3];
          if (row) {
            if (row.kind === 'directory') {
              const dirName = row.label.replace(/^[^▾]*▾ /, '').replace(/\/$/, '');
              const prefix = dirName + '/';
              const hasChildren = paths.some(p => p === dirName || p.startsWith(prefix));
              // Togglear: eliminar los hijos visibles del directorio en paths locales.
              const newPaths = hasChildren ? paths.filter(p => !(p.startsWith(prefix) && p !== dirName)) : paths;
            }
            if (row.kind === 'file') select(row.fileIndex);
          }
        }
        request();
        return { handled: true, focus: true, render: true };
      }
    },
    render(width) {
      if (width < 1) return [];
      layout = browserLayout(width, tui.terminal.rows, focus);
      const th = theme;
      if (width < 4) return [fit(focus === 'files' ? 'F' : 'P', width)];
      const topBorder = () => {
        if (width < 41) return th.fg('border', `╭${'─'.repeat(Math.max(0, width - 2))}╮`);
        const title = ' ODD Review ';
        const actions = '[Tab Switch] [Esc Close]';
        const fill = '─'.repeat(Math.max(1, layout.inner - title.length - actions.length - 2));
        return th.fg('border', '╭─') + th.fg('accent', th.bold(' ODD Review ')) + th.fg('border', fill)
          + th.fg('accent', '[Tab Switch] [Esc Close]') + th.fg('border', '─╮');
      };
      const paneHeader = (text, pane) => th.fg(focus === pane ? 'accent' : 'muted', `${focus === pane ? '◆' : '◇'} ${text}`);
      const warning = errors.length ? clean(errors.join('\n')) : '';
      const empty = warning || 'No files found in odd/';
      const emptyLines = empty.split('\n');
      const list = [];
      const activeRow = selectedTreeRow();
      listTop = clamp(listTop, tree.length - layout.body);
      if (activeRow < listTop) listTop = activeRow;
      if (activeRow >= listTop + layout.body) listTop = Math.max(0, activeRow - layout.body + 1);
      for (let row = 0; row < layout.body; row++) {
        const item = tree[listTop + row];
        let line = paths.length && item
          ? item.kind === 'directory'
            ? item.label
            : `${item.fileIndex === selected ? '> ' : '  '}${item.label}`
          : paths.length ? '' : emptyLines[row] || '';
        line = fit(line, layout.left);
        if (item?.kind === 'file' && item.fileIndex === selected) line = th.bg('selectedBg', th.fg('accent', line));
        else if (item?.kind === 'directory') line = th.fg('muted', line);
        else if (!paths.length) line = th.fg(warning ? 'error' : 'muted', line);
        list.push(line);
      }
      if (layout.right > 0) {
        if (!preview) {
          const message = failure || (!paths.length ? empty : loading ? 'Loading preview…' : content || 'Empty file');
          preview = !failure && content && /\.(md|markdown)$/i.test(paths[selected] || '')
            ? new Markdown(message, 0, 0, getMarkdownTheme())
            : new Text(message, 0, 0);
        }
        previewLines = preview.render(Math.max(1, layout.right));
        previewTop = clamp(previewTop, maxScroll());
      }
      const columns = (left, right) => layout.narrow
        ? th.fg('border', '│') + fit(focus === 'files' ? left : right, layout.inner) + th.fg('border', '│')
        : th.fg('border', '│') + fit(left, layout.left) + th.fg('border', '│') + fit(right, layout.right) + th.fg('border', '│');
      const divider = layout.narrow
        ? th.fg('border', `├${'─'.repeat(layout.inner)}┤`)
        : th.fg('border', `├${'─'.repeat(layout.left)}┼${'─'.repeat(layout.right)}┤`);
      const lines = [
        topBorder(),
        columns(paneHeader(`Artifacts · ${paths.length}`, 'files'), paneHeader(`Preview · ${label(paths[selected] || 'No selection')}`, 'preview')),
        divider,
      ];
      for (let row = 0; row < layout.body; row++) {
        let right = previewLines[previewTop + row] || '';
        if (failure) right = th.fg('error', right);
        lines.push(columns(list[row] || '', right));
      }
      const help = ` Tab switch · ↑↓ navigate · PgUp/PgDn scroll · click select · wheel scroll · Esc close${layout.narrow ? ' · compact' : ''}`;
      lines.push(th.fg('border', '│') + fit(th.fg('muted', help), layout.inner) + th.fg('border', '│'));
      lines.push(th.fg('border', `╰${'─'.repeat(layout.inner)}╯`));
      return lines.slice(0, layout.height);
    },
  };
  load();
  await pending;
  return component;
}
