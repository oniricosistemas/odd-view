import { discoverFiles, readPreview } from './files.js';
import { createBrowser } from './browser.js';

export function registerOddReview(pi, runtime) {
  pi.registerCommand('odd-review', {
    description: 'Browse project odd/ artifacts in a read-only overlay (Tab: pane, arrows: navigate, Esc: close)',
    handler: async (_args, ctx) => {
      if (ctx.mode !== 'tui') {
        if (ctx.hasUI) ctx.ui.notify('ODD Review requires interactive TUI mode.', 'warning');
        return;
      }
      await ctx.ui.custom(async (tui, theme, _keys, done) => {
        const result = await discoverFiles(ctx.cwd);
        return createBrowser({
          ...result, tui, theme, done, runtime,
          read: async path => {
            const result = await readPreview(ctx.cwd, path);
            if (result.error) throw new Error(result.error.replace(`Cannot preview ${path}: `, ''));
            return result.content;
          },
        });
      }, { overlay: true, overlayOptions: { anchor: 'center', width: '100%', maxHeight: '100%' } });
    },
  });
}
