import { constants } from 'node:fs';
import { lstat, open, readdir, realpath } from 'node:fs/promises';
import { isAbsolute, join, sep } from 'node:path';

const MAX_PREVIEW_BYTES = 512 * 1024;
const reason = error => error.code || error.message;
const within = (root, path) => path.startsWith(root + sep);

// Revalidate every component on each operation: discovered names are not capabilities.
async function checkedPath(project, name, directory = false) {
  const parts = name.split('/');
  if (isAbsolute(name) || parts[0] !== 'odd' || parts.some(part => !part || part === '.' || part === '..' || part.includes('\\') || part.includes('\0'))) {
    throw new Error('Path must stay inside odd/');
  }
  const root = await realpath(project);
  let path = root;
  for (const [index, part] of parts.entries()) {
    path = join(path, part);
    const stat = await lstat(path);
    if (stat.isSymbolicLink()) throw new Error('Symlink traversal is not allowed');
    const last = index === parts.length - 1;
    if ((!last || directory) ? !stat.isDirectory() : !stat.isFile()) {
      throw new Error(last && !directory ? 'Not a regular file' : 'Not a directory');
    }
  }
  const canonical = await realpath(path);
  if (canonical !== path || !within(root, canonical)) throw new Error('Path escapes project odd/');
  return path;
}

/** Recursively list regular artifacts, using portable repository-relative paths. */
export async function discoverFiles(project) {
  const paths = [], errors = [];
  async function visit(name) {
    let path;
    try {
      path = await checkedPath(project, name, true);
      const entries = await readdir(path, { withFileTypes: true });
      for (const entry of entries) {
        const child = `${name}/${entry.name}`;
        if (entry.isDirectory()) await visit(child);
        else if (entry.isFile()) {
          try { await checkedPath(project, child); paths.push(child); }
          catch (error) { errors.push(`Cannot inspect ${child}: ${reason(error)}`); }
        }
        // Never follow symlinks or open special files (pipes, sockets, devices).
      }
    } catch (error) {
      if (name !== 'odd' || error.code !== 'ENOENT') errors.push(`Cannot read ${name}/: ${reason(error)}`);
    }
  }
  await visit('odd');
  return { paths: paths.sort(), errors: errors.sort() };
}

/** Read only a validated regular file; bound memory and never execute file content. */
export async function readPreview(project, name) {
  let handle;
  try {
    const path = await checkedPath(project, name);
    handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    const stat = await handle.stat();
    if (!stat.isFile()) throw new Error('Not a regular file');
    // Check again after open to catch ordinary rename/symlink replacement races.
    await checkedPath(project, name);
    const current = await lstat(path);
    if (stat.dev !== current.dev || stat.ino !== current.ino) throw new Error('File changed while opening');
    // On Linux, verify the opened descriptor itself, not only the pathname.
    if (process.platform === 'linux') {
      const openedPath = await realpath(`/proc/self/fd/${handle.fd}`);
      if (openedPath !== path) throw new Error('File changed while opening');
    }
    const buffer = Buffer.alloc(MAX_PREVIEW_BYTES + 1);
    let length = 0;
    while (length < buffer.length) {
      const { bytesRead } = await handle.read(buffer, length, buffer.length - length, length);
      if (!bytesRead) break;
      length += bytesRead;
    }
    const data = buffer.subarray(0, Math.min(length, MAX_PREVIEW_BYTES));
    if (data.includes(0)) return { content: 'Binary file — preview unavailable.' };
    return { content: data.toString('utf8') + (length > MAX_PREVIEW_BYTES ? '\n\n[Preview truncated at 512 KiB]' : '') };
  } catch (error) {
    return { error: `Cannot preview ${name}: ${reason(error)}` };
  } finally {
    await handle?.close();
  }
}
