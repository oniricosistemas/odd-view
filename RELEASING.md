# Release odd-view to npm and GitHub

A release is one reviewed commit published through two package sources: a GitHub `vX.Y.Z` tag and the matching public npm version.

## Prerequisites

- Write access to `oniricosistemas/odd-view` on GitHub.
- An npm account allowed to create and publish the unscoped `odd-view` package.
- npm authentication configured locally or through an approved trusted-publishing workflow.
- A clean checkout of the default branch with its remote up to date.

## Release checklist

1. Choose the semantic version and run the complete package check:

   ```bash
   npm run release:check
   ```

2. Update `CHANGELOG.md` when the project starts maintaining one, then create the version commit and tag:

   ```bash
   npm version <patch|minor|major>
   ```

   `npm version` updates `package.json`, creates a version commit, and creates the matching `vX.Y.Z` tag. Do not create a second tag manually.

3. Inspect exactly what npm will receive:

   ```bash
   npm pack --dry-run
   git status --short
   git show --stat --oneline HEAD
   ```

4. Push the reviewed version commit and its tag:

   ```bash
   git push origin HEAD
   git push origin "v$(node -p "require('./package.json').version")"
   ```

5. Publish the same version to npm:

   ```bash
   npm publish --access public
   ```

   When publication moves to a supported trusted-publishing CI, add npm provenance there rather than claiming local provenance.

6. Verify both public installation paths in clean Gentle Shell homes, replacing `${VERSION}` with the released version:

   ```bash
   gentle-shell install npm:odd-view@${VERSION}
   gentle-shell install git:github.com/oniricosistemas/odd-view@v${VERSION}
   gentle-shell list
   ```

## Roll-forward policy

npm versions and Git tags are immutable release identities. If a release is wrong, do not rewrite its tag or reuse its version. Fix the issue, increment the patch version, and publish a new release.
