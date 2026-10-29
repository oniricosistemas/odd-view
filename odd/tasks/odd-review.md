# ODD Review browser
Build a Pi extension for browsing project ODD artifacts inside gentle-shell, and enroll the repository's canonical Engram project with the configured cloud.
The repository is an empty upstream, so the implementation includes the minimal package, tests, and usage documentation.

## Specs
1. **S1 — Repository and Engram:** “tengo el repo https://github.com/oniricosistemas/odd-view para que usemos con este proyecto, enrolalo para que sincronice engram con el cloud que tenemos.”
2. **S2 — Command entry point:** “querio crear un plugin/extension/comando que al correr /odd-review me abra un ventana dentro de gentle-shell”
3. **S3 — ODD file navigation:** “que a la izquierda muestre todos los archivos creados por ODD en el proyecto”
4. **S4 — Formatted preview:** “y que al hacer click en cada uno de ellos, muestre el contenido a la derecha, que sea ve con formato y lindo”
5. **S5 — Gentle Shell commands:** “para instalarlo en gentle-shell es gentle-shell --extension ./extensions/odd-review.ts”
6. **S6 — Public distribution:** “habría que crear un instalador npm o como seria para que un usuario nuevo lo instale?” Decision: “Ambos” (public npm package plus versioned GitHub tags), licensed under “MIT — recomendada”.
7. **S7 — Fullscreen visual redesign:** “ahi lo instale y se ve algo asi:\n/tmp/herdr-clipboard-images-1000/client-24-clipboard-1793231730596956464-0.png\npero no me termina de convencer como se ve, me gustaría algo como esto:\n/tmp/herdr-clipboard-images-1000/client-24-clipboard-1793231773189191355-0.png”

## Tasks
- [x] **T1** (S1) — Initialize the Pi package and enroll/sync the canonical `odd-view` Engram project. Route: inline. Commit: `3768990`.
- [x] **T2** (S2-S4) — Implement the tested `/odd-review` two-pane TUI extension with keyboard and mouse navigation. Route: delegated (`gentle-ai-worker`, context backstop). Commit: `ec60a98`.
- [x] **T3** (S1-S6) — Correct Gentle Shell usage documentation and verify the final install instructions. Route: inline. Commit: `4f1ee69`.
- [x] **T4** (S5-S6) — Prepare a public MIT-licensed npm package and reproducible GitHub-tag release flow without publishing. Route: inline. Commit: `4f1ee69`.
- [x] **T5** (S7) — Redesign `/odd-review` as a self-contained fullscreen framed browser matching the supplied reference. Route: inline. Commit: `1eef0e6`.

## Log
- **L1 — User request:** “Hola papurri, tengo el repo https://github.com/oniricosistemas/odd-view para que usemos con este proyecto, enrolalo para que sincronice engram con el cloud que tenemos. 
Bien te cuento locura lo que tengo ganas de hacer.... querio crear un plugin/extension/comando que al correr /odd-review me abra un ventana dentro de gentle-shell que a la izquierda muestre todos los archivos creados por ODD en el proyecto, y que al hacer click en cada uno de ellos, muestre el contenido a la derecha, que sea ve con formato y lindo”
- **L2 — Authorization:** User explicitly authorized writes under `/home/lmsastre/.engram/` and cloud synchronization for `odd-view`.
- **L3 — Repository evidence:** The GitHub remote exists but has no HEAD or branches; local development starts on `feat/odd-review` from an unborn repository.
- **L4 — Engram evidence:** `engram cloud enroll odd-view` succeeded. The first explicit cloud sync created chunk `a7eba65d`; status then reported 1 local chunk, 1 remote chunk, and 0 pending imports.
- **L5 — T2 verification:** The delegated writer covered S2-S4 with nine deterministic tests. Parent review reran `npm run check` and `node --test`; both passed all 9 tests. A first pseudo-terminal smoke harness exited 130 because it injected Ctrl+C immediately, so live command interaction remained explicitly assigned to T3.
- **L6 — T3 verification:** `npm pack --dry-run` included the extension and runtime modules in a 9-file package. A corrected PTY smoke separated text entry from the Return key and observed the live `ODD Review` overlay inside Pi 0.81.1. `git diff --check` passed. The first combined-input PTY attempt did not submit the command; this was a harness defect, not an extension failure. An earlier reported count of 10 accidentally included the dry-run command's temporary JSON output file.
- **L7 — Independent verification:** The high-risk filesystem verifier passed S2-S4, including isolated traversal, symlink, FIFO/socket, concurrent replacement, binary, size-boundary, real Pi 0.81.1/1.3.0, and mouse-selection probes. It could not contact the cloud under its no-network constraint, so S1 remained unverified by that worker; the parent separately ran `engram sync --import --cloud --project odd-view` and confirmed 2 local chunks, 2 remote chunks, and 0 pending imports.
- **L8 — User correction:** “para instalarlo en gentle-shell es gentle-shell --extension ./extensions/odd-review.ts\nhabría que crear un instalador npm o como seria para que un usuario nuevo lo instale?”
- **L9 — Distribution decision:** User selected “Ambos” for public npm and versioned GitHub installation, then selected “MIT — recomendada” as the public license.
- **L10 — Distribution TDD:** `node --test test/package.test.js` first failed because `package.json` still had `private: true`. After adding public metadata, MIT licensing, release documentation, and Gentle Shell commands, the focused test passed 1/1 and `npm run check` passed 10/10.
- **L11 — Distribution verification:** Independent verification passed S5-S6 for preparation without release. It confirmed the exact seven-file npm payload and isolated Gentle Shell installation; public installation remains intentionally unverified until publish. An initial parent assertion expected the package name in `gentle-shell list`, but local sources are displayed by relative path; diagnostic output confirmed the installation.
- **L12 — Visual correction:** “ahi lo instale y se ve algo asi:\n/tmp/herdr-clipboard-images-1000/client-24-clipboard-1793231730596956464-0.png\npero no me termina de convencer como se ve, me gustaría algo como esto:\n/tmp/herdr-clipboard-images-1000/client-24-clipboard-1793231773189191355-0.png” The user authorized read-only access to both supplied images.
- **L13 — Visual TDD:** The S7 focused test first failed against the unframed overlay. The implementation now renders a full-height top-left overlay with a complete border, title actions, pane headers, directory tree, content divider, and footer. The focused S7 test passed, the full suite passed 11/11, and a real `gentle-shell --extension ./extensions/odd-review.ts` PTY smoke observed `ODD Review`, `Artifacts`, `Preview`, `[Tab Switch]`, and `[Esc Close]`. An initial 15-second smoke submitted during startup and saw no overlay; the readiness-aware background smoke passed after 6 seconds.
