# Review ODD artifacts without leaving gentle-shell

`odd-view` adds `/odd-review` to gentle-shell. The command opens a read-only browser for every regular file under the current project's `odd/` directory: choose a file on the left and read its formatted content on the right.

## Quick path

### Try this checkout

```bash
gentle-shell --extension ./extensions/odd-review.ts
```

Inside gentle-shell, run:

```text
/odd-review
```

### Install permanently

The public npm package is the simplest path for a new user:

```bash
gentle-shell install npm:@oniricosistemas/odd-view
```

A released GitHub tag installs the same immutable version without using the npm registry. Replace `${VERSION}` with a published version such as `0.1.0`:

```bash
gentle-shell install git:github.com/oniricosistemas/odd-view@v${VERSION}
```

Restart or reload gentle-shell, then run `/odd-review` from any project that contains an `odd/` directory. A custom installer is unnecessary: `gentle-shell install` writes the package into the resolved Gentle Shell home and keeps it separate from vanilla Pi by default.

Manage the installed package through the same home:

```bash
gentle-shell list
gentle-shell update npm:@oniricosistemas/odd-view
gentle-shell remove npm:@oniricosistemas/odd-view
```

## Controls

| Action | Keyboard | Mouse in fullscreen mode |
| --- | --- | --- |
| Switch pane | `Tab` or `Shift+Tab` | Click the pane |
| Select a file | `↑`, `↓`, `Page Up`, `Page Down`, `Home`, `End` | Click or use the wheel over the file list |
| Open the preview pane | `Enter` or `→` | Click the preview pane |
| Scroll the preview | `↑`, `↓`, `Page Up`, `Page Down`, `Space`, `Home`, `End` | Use the wheel over the preview |
| Return to files | `←` | Click the file list |
| Close | `Esc` or `Ctrl+C` | — |

Mouse input depends on Pi fullscreen mode. Every action remains available from the keyboard.

## What the browser reads

- Files are discovered recursively below `odd/` and sorted by repository-relative path.
- Markdown files receive the active Pi Markdown theme; other text files use a plain preview.
- Previews are capped at 512 KiB. Binary files show an explanatory placeholder.
- Symlinks, directories, special files, path escapes, and files replaced during opening are rejected.
- The extension never edits project artifacts.

On narrow terminals, `/odd-review` shows one pane at a time. Use `Tab` to switch between the file list and preview.

## Engram project identity

This repository pins its Engram project name in `.engram/config.json`:

```json
{
  "project": "odd-view"
}
```

Cloud credentials and server configuration stay outside the repository. Maintainers can inspect replication without exposing credentials:

```bash
engram sync --status --cloud --project odd-view
```

Enrollment and synchronization are explicit administrative actions; `/odd-review` never triggers either one.

## Development

The implementation keeps filesystem validation and browser state outside the Pi entry point so they can be tested deterministically.

```bash
npm test
npm run check
```

| Path | Responsibility |
| --- | --- |
| `extensions/odd-review.ts` | Pi package entry point and host adapters |
| `src/command.js` | `/odd-review` registration and TUI lifecycle |
| `src/files.js` | Read-only discovery and bounded preview loading |
| `src/browser.js` | Responsive layout, rendering, keyboard, and mouse behavior |
| `test/odd-review.test.js` | Public behavior and safety regression coverage |
| `odd/tasks/odd-review.md` | ODD specification, task state, and evidence log |

Maintainers should follow [`RELEASING.md`](./RELEASING.md) so the npm version and GitHub tag stay identical.
