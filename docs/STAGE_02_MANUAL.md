# Stage 02 manual

This checkpoint saves the selected tools before building the environment. It requires the saved, clean Stage 01 repository at commit `d4b28f834d75086e5f1752b4b7b48ecc4dc07684`, with annotated tag `v0.1.0`.

Download `rocket-project-stage-02.zip` into `~/Downloads` and run as your ordinary user:

```bash
python3 "$HOME/Downloads/rocket-project-stage-02.zip"
```

Do not extract it over the repository or run it through sudo. The embedded Python installer checks archive hashes, the repository location, base commit, tag, and existing files before applying changes.

## What happens

1. Verify Stage 01 and a clean worktree.
2. Save the selected stack, version/model manifest, CPU profile, host snapshot, manuals, and supplementary prerequisite inspector.
3. Check the decision metadata.
4. Commit explicit patch files and create annotated `v0.2.0`.
5. Print a read-only preflight result and instructions to return the output.

The installer does not install Docker or research packages, download weights, start containers, create a remote, or run an experiment. Host file/Git/metadata operations are the bootstrap exception; scientific processing is containerised later.

## Expected output

```text
STAGE_02_SAVED
Commit: <actual local commit>
Tag: v0.2.0
Working tree: clean
STACK: Python 3.13.16; uv 0.13.1; llama.cpp v0.6.0; Qwen3.5-4B Q4_K_M; BM25
STAGE_02_PREFLIGHT_BEGIN
...
STAGE_02_PREFLIGHT_END
NEXT_STAGE_PENDING: return this output before Stage 03
```

Missing Docker is expected at this documentation stage. It does not invalidate the saved tool decision. Stage 03 needs the prerequisite installed and reachable before locking or executing the project.

Paste this output into the conversation. The supplemental preflight reports effective cgroup controllers, available RAM, CPU capability flags, and prerequisite presence; it does not print credentials, usernames, emails, or serial numbers.

## Conflicts and interrupted application

Existing modifications are preserved. Do not discard work just to apply a patch; return the conflict output. The installer creates a journal under `logs/setup/` before writing, so rerunning the same ZIP can resume a partially applied patch only when all changed paths still match that patch's expected bytes.

If a Git hook or signing preference blocks the commit/tag, resolve that Git issue and rerun this same ZIP. Nothing advances to Stage 03 automatically. A successfully reapplied checkpoint adds no duplicate commit/tag. Running an old patch after later work is rejected.

## Inspect the checkpoint

```bash
cd "$HOME/git_work/rocket_proplusion_project"
git status --short
git log -2 --oneline
git show --no-patch v0.2.0
python3 scripts/stage02_preflight.py
```

Package pins are selected, not installed or fully resolved. Read `docs/STAGE_02_STACK_DECISION.md` for the exact pending reproducibility checks. No host uv or JavaScript package manager is needed for the planned first benchmark.
