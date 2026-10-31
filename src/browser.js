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

/** Tree rows in path order; a collapsed directory keeps its own row and hides its descendants. */
export function treeRows(paths, collapsed = new Set()) {
  const rows = [];
  const directories = new Set();
  paths.forEach((path, fileIndex) => {
    const parts = path.split('/');
    let hidden = false;
    for (let depth = 0; depth < parts.length - 1; depth++) {
      const directory = parts.slice(0, depth + 1).join('/');
      if (!directories.has(directory)) {
        directories.add(directory);
        const marker = collapsed.has(directory) ? '▸' : '▾';
        rows.push({ kind: 'directory', path: directory, depth, label: `${'  '.repeat(depth)}${marker} ${label(parts[depth])}/` });
      }
      if (collapsed.has(directory)) { hidden = true; break; }
    }
    if (!hidden) {
      const depth = Math.max(0, parts.length - 1);
      rows.push({ kind: 'file', fileIndex, depth, label: `${'  '.repeat(depth)}${label(parts.at(-1))}` });
    }
  });
  return rows;
}

/** A fresh, read-only interaction. Runtime adapters are the host's shipped TUI components. */
export async function createBrowser({ paths, errors = [], read, tui, theme, done, runtime }) {
  const { Markdown, Text, getMarkdownTheme, truncateToWidth, matchesKey } = runtime;
  let collapsed = new Set();
  let tree = treeRows(paths, collapsed);
  let selected = 0, listTop = 0, previewTop = 0, focus = 'files';
  let content = '', failure = '', loading = false, pending = Promise.resolve(), generation = 0, closed = false;
  let preview, layout, previewLines = [];
  // Hit regions published by the last render: top badges, pane headers and help-row keys.
  let regions = [], hoverRegion = null, hoverRow = null;
  const fit = (text, width) => width > 0 ? truncateToWidth(text, width, '', true) : '';
  const request = () => { if (!closed) tui.requestRender(); };
  const maxScroll = () => Math.max(0, previewLines.length - (layout?.body || 1));
  const page = () => layout?.body || 1;
  const selectedTreeRow = () => Math.max(0, tree.findIndex(row => row.fileIndex === selected));
  const visibleFiles = () => tree.filter(row => row.kind === 'file').map(row => row.fileIndex);

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
  /** Move to the next visible file in `direction`, skipping files a collapsed directory hides. */
  function step(direction) {
    const files = visibleFiles();
    if (!files.length) return;
    if (direction < 0) select([...files].reverse().find(index => index < selected) ?? files[0]);
    else select(files.find(index => index > selected) ?? files.at(-1));
  }
  function stepBy(count) {
    const direction = Math.sign(count);
    for (let move = 0; move < Math.abs(count); move++) step(direction);
  }
  /** Jump to the first or last file that is not hidden by a collapsed directory. */
  function edge(wantFirst) {
    const files = visibleFiles();
    if (files.length) select(wantFirst ? files[0] : files.at(-1));
    else request();
  }
  function keepSelectionVisible() {
    const files = visibleFiles();
    if (!files.length || files.includes(selected)) return;
    selected = files.find(index => index > selected) ?? files.at(-1);
    load();
  }
  function toggle(directory) {
    collapsed = new Set(collapsed);
    if (!collapsed.delete(directory)) collapsed.add(directory);
    tree = treeRows(paths, collapsed);
    keepSelectionVisible();
    listTop = clamp(listTop, Math.max(0, tree.length - page()));
    request();
  }
  function run(action) {
    if (action === 'close') { close(); return true; }
    if (action === 'tab') { focus = focus === 'files' ? 'preview' : 'files'; request(); return true; }
    if (action === 'files' || action === 'preview') { focus = action; request(); return true; }
    if (action === 'up') { focus === 'files' ? step(-1) : scroll(-1); return true; }
    if (action === 'down') { focus === 'files' ? step(1) : scroll(1); return true; }
    if (action === 'pageup') { focus === 'files' ? stepBy(-page()) : scroll(-page()); return true; }
    if (action === 'pagedown') { focus === 'files' ? stepBy(page()) : scroll(page()); return true; }
    return false;
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
        if (key('up')) step(-1);
        else if (key('down')) step(1);
        else if (key('pageup')) stepBy(-page());
        else if (key('pagedown')) stepBy(page());
        else if (key('home')) edge(true);
        else if (key('end')) edge(false);
        else if (key('return') || key('right')) { focus = 'preview'; request(); }
      } else {
        if (key('up')) scroll(-1);
        else if (key('down')) scroll(1);
        else if (key('pageup')) scroll(-page());
        else if (key('pagedown') || key('space')) scroll(page());
        else if (key('home')) { previewTop = 0; request(); }
        else if (key('end')) { previewTop = maxScroll(); request(); }
        else if (key('left')) { focus = 'files'; request(); }
      }
    },
    handleMouse(event) {
      if (closed || !layout || event.x < 0 || event.y < 0 || event.x >= layout.width || event.y >= layout.height) return;
      const region = regions.find(item => item.y === event.y && event.x >= item.x0 && event.x <= item.x1) || null;
      const inBody = event.y >= 3 && event.y < 3 + layout.body;
      const rowIndex = inBody ? listTop + event.y - 3 : null;
      const row = inBody ? tree[rowIndex] || null : null;
      if (event.type === 'move') {
        const nextRegion = region?.id ?? null;
        if (nextRegion !== hoverRegion || rowIndex !== hoverRow) {
          hoverRegion = nextRegion; hoverRow = rowIndex; request();
        }
        return { handled: false, render: false };
      }
      if (event.type === 'click' && event.button === 'left') {
        if (region && run(region.action)) return { handled: true, focus: true, render: true };
        const pane = layout.narrow ? focus : event.x <= layout.left ? 'files' : event.x >= layout.left + 2 ? 'preview' : null;
        if (!pane) return;
        focus = pane;
        if (pane === 'files' && row) {
          if (row.kind === 'directory') toggle(row.path);
          else select(row.fileIndex);
        }
        request();
        return { handled: true, focus: true, render: true };
      }
      if (event.type === 'wheel' && inBody) {
        const pane = layout.narrow ? focus : event.x <= layout.left ? 'files' : event.x >= layout.left + 2 ? 'preview' : null;
        if (!pane) return;
        focus = pane;
        if (pane === 'files') stepBy(Math.trunc(event.wheelDelta || 0));
        else scroll(Math.trunc(event.wheelDelta || 0));
        return { handled: true, focus: true, render: true };
      }
    },
    render(width) {
      if (width < 1) return [];
      layout = browserLayout(width, tui.terminal.rows, focus);
      const th = theme;
      const emphasis = text => typeof th.underline === 'function' ? th.underline(text) : th.bold(text);
      regions = [];
      if (width < 4) return [fit(focus === 'files' ? 'F' : 'P', width)];
      const topBorder = () => {
        if (width < 41) return th.fg('border', `╭${'─'.repeat(Math.max(0, width - 2))}╮`);
        const title = ' ODD Review ';
        const badges = [{ id: 'tab', text: '[Tab Switch]', action: 'tab' }, { id: 'close', text: '[Esc Close]', action: 'close' }];
        const actions = badges.map(badge => badge.text).join(' ');
        const fill = '─'.repeat(Math.max(1, layout.inner - title.length - actions.length - 2));
        let x = 2 + title.length + fill.length;
        for (const badge of badges) {
          regions.push({ id: badge.id, action: badge.action, y: 0, x0: x, x1: x + badge.text.length - 1 });
          x += badge.text.length + 1;
        }
        const styledBadges = badges.map(badge => {
          const styled = th.fg('accent', badge.text);
          return hoverRegion === badge.id ? emphasis(styled) : styled;
        }).join(' ');
        return th.fg('border', '╭─') + th.fg('accent', th.bold(title)) + th.fg('border', fill) + styledBadges + th.fg('border', '─╮');
      };
      const paneHeader = (text, pane, id) => {
        const styled = th.fg(focus === pane ? 'accent' : 'muted', `${focus === pane ? '◆' : '◇'} ${text}`);
        return hoverRegion === id ? emphasis(styled) : styled;
      };
      const warning = errors.length ? clean(errors.join('\n')) : '';
      const empty = warning || 'No files found in odd/';
      const emptyLines = empty.split('\n');
      const list = [];
      const activeRow = selectedTreeRow();
      listTop = clamp(listTop, tree.length - layout.body);
      if (activeRow < listTop) listTop = activeRow;
      if (activeRow >= listTop + layout.body) listTop = Math.max(0, activeRow - layout.body + 1);
      for (let row = 0; row < layout.body; row++) {
        const rowIndex = listTop + row;
        const item = tree[rowIndex];
        let line = paths.length && item
          ? item.kind === 'directory'
            ? item.label
            : `${item.fileIndex === selected ? '> ' : '  '}${item.label}`
          : paths.length ? '' : emptyLines[row] || '';
        line = fit(line, layout.left);
        const hovered = hoverRow === rowIndex && item;
        if (item?.kind === 'file' && item.fileIndex === selected) line = th.bg('selectedBg', th.fg('accent', line));
        else if (item?.kind === 'directory') line = hovered ? emphasis(th.fg('accent', line)) : th.fg('muted', line);
        else if (!paths.length) line = th.fg(warning ? 'error' : 'muted', line);
        else if (hovered) line = emphasis(th.fg('accent', line));
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
      const headerLeft = paneHeader(`Artifacts · ${paths.length}`, 'files', 'header-files');
      const headerRight = paneHeader(`Preview · ${label(paths[selected] || 'No selection')}`, 'preview', 'header-preview');
      if (layout.narrow) regions.push({ id: 'header', action: focus, y: 1, x0: 1, x1: Math.max(1, layout.inner) });
      else {
        regions.push({ id: 'header-files', action: 'files', y: 1, x0: 1, x1: Math.max(1, layout.left) });
        regions.push({ id: 'header-preview', action: 'preview', y: 1, x0: layout.left + 2, x1: layout.left + 1 + layout.right });
      }
      const columns = (left, right) => layout.narrow
        ? th.fg('border', '│') + fit(focus === 'files' ? left : right, layout.inner) + th.fg('border', '│')
        : th.fg('border', '│') + fit(left, layout.left) + th.fg('border', '│') + fit(right, layout.right) + th.fg('border', '│');
      const divider = layout.narrow
        ? th.fg('border', `├${'─'.repeat(layout.inner)}┤`)
        : th.fg('border', `├${'─'.repeat(layout.left)}┼${'─'.repeat(layout.right)}┤`);
      const lines = [
        topBorder(),
        columns(headerLeft, headerRight),
        divider,
      ];
      for (let row = 0; row < layout.body; row++) {
        let right = previewLines[previewTop + row] || '';
        if (failure) right = th.fg('error', right);
        lines.push(columns(list[row] || '', right));
      }
      const helpY = 3 + layout.body;
      const helpKeys = [
        { text: ' ', action: null },
        { text: 'Tab switch', action: 'tab' },
        { text: ' · ', action: null },
        { text: '↑', action: 'up' },
        { text: '↓', action: 'down' },
        { text: ' navigate · ', action: null },
        { text: 'PgUp', action: 'pageup' },
        { text: '/', action: null },
        { text: 'PgDn', action: 'pagedown' },
        { text: ' scroll · click select · wheel scroll · ', action: null },
        { text: 'Esc close', action: 'close' },
        ...(layout.narrow ? [{ text: ' · compact', action: null }] : []),
      ];
      let help = '', helpX = 1;
      for (const key of helpKeys) {
        const id = key.action ? `${key.action}-help` : null;
        if (id) regions.push({ id, action: key.action, y: helpY, x0: helpX, x1: helpX + key.text.length - 1 });
        const styled = th.fg(key.action ? 'accent' : 'muted', key.text);
        help += id && hoverRegion === id ? emphasis(styled) : styled;
        helpX += key.text.length;
      }
      lines.push(th.fg('border', '│') + fit(help, layout.inner) + th.fg('border', '│'));
      lines.push(th.fg('border', `╰${'─'.repeat(layout.inner)}╯`));
      return lines.slice(0, layout.height);
    },
  };
  load();
  await pending;
  return component;
}
