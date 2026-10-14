# Stage 01: save the proposal and return the system summary

This checkpoint saves documentation before selecting the environment. It is not a model run or a Docker implementation. Host-side file installation, Git metadata, and prerequisite inspection are bootstrap operations; later scientific processing runs in temporary containers.

## Apply the ZIP

Download `rocket-project-stage-01.zip` to your normal `Downloads` folder, keeping this filename. Then run:

```bash
python3 "$HOME/Downloads/rocket-project-stage-01.zip"
```

Python runs the ZIP's embedded installer directly, so manual extraction and `unzip` are unnecessary. Do not use `sudo`. It requires Python 3.8+ and Git.

The installer:

1. Verifies every payload file's SHA-256 and rejects unsafe paths.
2. Checks the target for conflicting files, an unrelated repository, or existing modifications.
3. Requires an existing Git author name/email, or explicitly supplied local identity arguments.
4. Saves the docs, inspection script, ignores, and output-folder placeholders to `~/git_work/rocket_proplusion_project/`.
5. Initialises a new `main` branch, commits the explicit payload files, and creates annotated tag `v0.1.0`.
6. Checks that the worktree is clean and generated log/result paths are ignored.
7. Writes a read-only environment summary under `logs/system/` and prints it.

No packages, model weights, GitHub repositories, or containers are created. Reapplying the same patch is safe: identical files are preserved and no duplicate commit/tag is added. Conflicting content is not overwritten.

## If Git identity is missing

The installer stops before writing payload files. It prints an example with two arguments. Supply your chosen author name and a verified commit email, or copy the private commit email shown in your GitHub email settings:

```bash
python3 "$HOME/Downloads/rocket-project-stage-01.zip" \
  --git-name 'YOUR AUTHOR NAME' \
  --git-email 'YOUR VERIFIED GITHUB COMMIT EMAIL'
```

The supplied identity is written to this repository's local Git configuration only. It does not change global settings. Do not copy the placeholder words literally. Git commit identity is separate from GitHub login; the actual GitHub account will be verified later.

If your download was renamed with a `(1)` suffix, use that actual path. A non-default path for a deliberate test is supported with `--target`; the normal command uses the requested directory.

## Expected completion

Output includes:

```text
STAGE_01_SAVED
Project: .../git_work/rocket_proplusion_project
Commit: <actual local commit>
Tag: v0.1.0
Working tree: clean
SYSTEM_REPORT_BEGIN
...
SYSTEM_REPORT_END
NEXT_STAGE_PENDING: return this output before Stage 02
```

If the system report fails after the commit, the proposal is still saved; the output distinguishes that case. Return the failure output so we can repair the same checkpoint.

Paste the completion/system-summary output into the conversation. Package selection uses that real state rather than assumptions from a different machine. The report prints OS version, CPU architecture, RAM, free space, prerequisite versions, Docker reachability, and optional NVIDIA model/VRAM/driver information. It does not print tokens, emails, serial numbers, hostnames, or environment variables.

## Inspection and recovery

```bash
cd "$HOME/git_work/rocket_proplusion_project"
git status --short
git log -1 --oneline
git show --no-patch v0.1.0
python3 scripts/system_report.py
```

The installer writes setup diagnostics under `logs/setup/` once the project has been safely initialised. Failed installation is not tagged as completed. Do not delete an existing directory or discard modifications to make a patch apply; return the conflict output instead.

If a commit hook or signing configuration blocks the checkpoint, the payload is preserved. Resolve that local Git issue and rerun. The installer does not bypass hooks, signing preferences, or permission checks, and does not make network requests.

## Later patch contract

Every later ZIP will name its required base commit/tag, list file hashes, preserve unrelated changes, run appropriate container checks, commit each accepted change, and tag a completed major stage. Failed checks remain in the same stage. Return the output before the next stage is prepared.

GitHub setup is deferred until the verified stack/scaffold stage. We will verify the `Heavenly-Cyber` login, create the chosen repository, push commits and stage tags, and publish concrete major checkpoint releases. No authentication token belongs in a ZIP, source file, result, log, or container.
