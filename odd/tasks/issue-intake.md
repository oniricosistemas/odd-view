## Specs
S1: User requested: "el repo tiene disponible para crear las issue https://github.com/oniricosistemas/odd-view/issues crea lo que sea necesario en el repo, fijate si podemos guiarnos por como lo hacen otros proyectos".
S2: User selected Bug + Feature issue forms; keep blank issues enabled; add `status/approved`, applied only manually by a maintainer and never automatically.
S3: Forms use existing `bug` and `enhancement` labels and collect actionable reproduction/problem/outcome details without asking for private data.
S4: Pull requests reference issues, select exactly one `type:*` label, and state only checks actually run.

## Tasks
T1: Inspect target issue policy and public form conventions — commit: pending policy PR
T2: Add bug/feature YAML forms, issue config, label manifest, PR template and contributing guide — commit: pending policy PR
T3: Add structural tests and run npm checks — commit: pending policy PR
T4: Create declared GitHub labels and open a non-closing PR referencing issue #3 — commit: pending policy PR

## Log
L1: User request: "el repo tiene disponible para crear las issue https://github.com/oniricosistemas/odd-view/issues crea lo que sea necesario en el repo, fijate si podemos guiarnos por como lo hacen otros proyectos".
L2: User decisions: Bug + Feature forms; retain blank issues; add a manual `status/approved` label, never auto-applied.
