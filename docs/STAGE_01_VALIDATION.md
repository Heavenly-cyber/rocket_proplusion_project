# Stage 01 validation

Validation was performed in the preparation workspace on 14 October 2026. Pop!_OS installation is verified by the user's returned output, not assumed from these checks.

The installer was actually executed against disposable Git repositories. The following behaviours passed:

- Fresh documentation save, `main` branch, clean commit, annotated `v0.1.0` tag, and exact proposal bytes.
- Reapplication without duplicate commits/tags.
- Preservation of conflicting user edits and unrelated directory content.
- Missing Git identity stops before payload writes.
- Rejection of symbolic-link targets and a target nested inside another repository.
- Rejection of a modified payload when its manifest checksum no longer matches.
- Recovery from an interrupted initial save before the first commit.
- Recovery from an interruption after the documentation commit but before tag creation.

Python syntax, JSON parsing, Markdown relative links, eight Mermaid flowchart structures, and ZIP file integrity were checked. No LLM experiment, model download, research-package installation, remote repository creation, or Docker job was part of Stage 01.
