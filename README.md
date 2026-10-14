# RocketNozzle-LLM

Rocket Propulsion term-paper project: evaluate local LLM reliability on rocket-nozzle performance, units, evidence support, and model applicability.

**Current stage:** `v0.1.0`, proposal/documentation only. No inference experiment, frozen dependency environment, or measured result exists yet.

Read [the project manifesto](docs/PROJECT_MANIFESTO.md), [literature search](docs/LITERATURE_SEARCH.md), and [Stage 01 manual](docs/STAGE_01_MANUAL.md).

The requested local directory is `~/git_work/rocket_proplusion_project/`. Generated research outputs will use `resutls/` and operational logs will use `logs/`, preserving the requested spelling. Scientific tasks will run in temporary Docker containers; exact dependencies and commands are selected in the next stage after a system check.

## Current commands

After applying the Stage 01 ZIP:

```bash
cd "$HOME/git_work/rocket_proplusion_project"
git status --short
git log -1 --oneline
git tag --list
python3 scripts/system_report.py
```

The last command only inspects prerequisites and writes an ignored diagnostic file under `logs/`. It does not install packages, start containers, or print credentials.

## Next checkpoint

Return the Stage 01 installer output. Stage 02 will document the selected stack and exact versions. Later patches build the reproducible scaffold, reviewed benchmark, actual LLM runs, and final term-paper report in sequence.

The intended GitHub owner is [Heavenly-Cyber](https://github.com/Heavenly-Cyber). No remote repository is created by this patch. We will verify the signed-in account before creating/pushing it.
