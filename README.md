# RocketNozzle-LLM

Rocket Propulsion term-paper project: evaluate local LLM reliability on rocket-nozzle numbers, units, evidence support, and model applicability.

**Current checkpoint:** `v0.2.0`, tool selection saved. The environment and model study have not been built/run yet.

Read [the manifesto](docs/PROJECT_MANIFESTO.md), [literature search](docs/LITERATURE_SEARCH.md), [stack decision](docs/STAGE_02_STACK_DECISION.md), and [Stage 02 manual](docs/STAGE_02_MANUAL.md).

## Selected stack

- Python 3.13.16 and uv 0.13.1 inside Docker.
- CPU llama.cpp v0.6.0 with a pinned Qwen3.5-4B Q4_K_M GGUF.
- BM25 lexical retrieval; SciPy/Pint references and unit checks.
- Strict JSON records, headless charts, temporary containers, persistent scoped outputs.

Exact selected versions are in `configs/stack-selection.json`. Model identity is fixed; transitive lock, container digests, full inference source commit, and runtime verification are Stage 03 work. `configs/cpu-profile.json` describes provisional limits/sampling; `configs/host-profile.json` records the returned machine summary without credentials.

## Current commands

```bash
cd "$HOME/git_work/rocket_proplusion_project"
git status --short
git log -2 --oneline
git tag --list
python3 scripts/stage02_preflight.py
```

The preflight only inspects host prerequisites and writes under ignored `logs/`. Research commands will be provided with the Docker scaffold. Outputs use `resutls/`; operational logs use `logs/`, preserving the requested spelling.

## Next checkpoint

Return the Stage 02 patch output. Stage 03 will install/verify Docker, generate the lock in containers, build/check the scaffold, and prepare GitHub setup for [Heavenly-Cyber](https://github.com/Heavenly-Cyber).
