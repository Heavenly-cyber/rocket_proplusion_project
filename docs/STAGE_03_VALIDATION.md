# Stage 03 validation boundaries

Prepared 2026-10-14. This file records authoring checks. Actual Pop!_OS/container evidence is created by the user-run patch in `docs/STAGE_03_VERIFICATION.json` and scoped `resutls/`/`logs/` folders.

## Authoring checks

The ZIP's guarded installation, preservation, reapply/recovery, and source-integrity checks are tested against disposable Git repositories. Production base matching remains the exact user-returned Stage 02 commit; fixture archives substitute only their disposable base metadata. Lifecycle orchestration tests use an explicitly labeled simulated Docker adapter to exercise success/error/interrupt cleanup and rejected isolation settings; these are not real Docker runs. Python syntax, project/config consistency, and pinned-source identities are checked before delivery.

Authoring results:

- 18 disposable-repository patch/checkpoint checks passed: exact base rejection, source-only save, reapply, preserved edits/notes, symlink/traversal/checksum rejection, branch/tag guards, respected hook failure, exact source recovery, new/tracked generated checkpoint recovery, and refusal of later unrelated commits.
- 10 simulated-adapter lifecycle checks passed: success, expected/unexpected failure, interrupt, rejected unsafe settings before start, foreign-resource preservation, and inspection failure distinguished from confirmed removal.
- Python syntax, a conservative import scan, exact direct dependency equality with Stage 02, fixed model metadata, source-file manifests, and ZIP payload integrity were checked.
- Authoring-side Ruff execution could not complete because its package download timed out. It is not marked passed. The real worker runs pinned Ruff/pytest during local setup and stops before the major tag if either fails.

## Local checks still required

This authoring environment has no Docker daemon or the capabilities needed to start one. It has not installed packages on your computer, built the selected containers, resolved the production transitive lock, downloaded/run the selected model, or authenticated/published to your GitHub account. No mocked model response or synthetic research score is substituted for those actions.

The patch performs the actual work on Pop!_OS, saves substage commits, and creates `v0.3.0` only after worker checks, build/source/library verification, checksum verification, real local model API readiness, and cleanup pass. Failures retain prior saves and remain in Stage 03. Authentication/publication may complete after the local tag; remote success is reported separately.
