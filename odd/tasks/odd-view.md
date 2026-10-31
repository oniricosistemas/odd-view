# odd-view ODD tracking

Feature: establish structured GitHub issue intake and documented maintainer triage for odd-view.

## Specs
S1: Add distinct bug-report and feature-request forms while keeping blank issues enabled.
S2: Issue type labels describe the request; `status/approved` records an explicit maintainer decision and is never automated.
S3: PR contributors select exactly one `type:*` label, reference the related issue, and list checks actually run.

## Tasks
T1: Discover current repository labels, issues and public issue-form conventions — commit: pending policy PR
T2: Add forms, config, labels, PR template and contribution guidance — commit: pending policy PR
T3: Add structural tests and run package checks — commit: pending policy PR
T4: Create missing labels and open policy PR referencing issue #3 — commit: pending policy PR

## Log
L1: User request: "el repo tiene disponible para crear las issue https://github.com/oniricosistemas/odd-view/issues crea lo que sea necesario en el repo, fijate si podemos guiarnos por como lo hacen otros proyectos".
L2: User selected Bug + Feature forms, keeping blank issues enabled, and manual-only `status/approved`.
