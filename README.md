# RocketNozzle-LLM

Rocket Propulsion term-paper project: measure local LLM reliability on rocket-nozzle numbers, units, evidence, and model applicability. The selected topic is **ML-Based Rocket Nozzle Performance Prediction**, adapted into a reproducible LLM-only versus BM25-RAG study.

Start with [the manifesto](docs/PROJECT_MANIFESTO.md), [literature review](docs/LITERATURE_SEARCH.md), [stack decision](docs/STAGE_02_STACK_DECISION.md), and [Stage 03 manual](docs/STAGE_03_MANUAL.md).

## Current stage

**Stage 03 terminal recovery:** if the scaffold is saved at `a194902efa08dd12c5d25138bb063a717f473bc6` and sudo reports that a terminal is required, apply `rocket-project-stage-03-repair-01.zip`. See [the recovery instructions](docs/STAGE_03_REPAIR_01.md). After that repair, use its ZIP or `python3 scripts/project.py setup` for retries; the original ZIP preserves its original file hashes and rejects repaired files.

This is the Stage 03 environment scaffold. A local `v0.3.0` tag is created only after Docker builds, isolation/library checks, GGUF checksum verification, a local model API check, and container cleanup actually pass. The resulting `docs/STAGE_03_VERIFICATION.json` records what ran. GitHub publication follows those checks. Stage 04 creates the reviewed corpus and benchmark; evaluation scores do not exist yet.

## One-command setup and reproduction

Run the downloaded patch from your normal Pop!_OS user account:

```bash
python3 "$HOME/Downloads/rocket-project-stage-03.zip"
```

After the scaffold is saved, the same workflow is available in the repository:

```bash
cd "$HOME/git_work/rocket_proplusion_project"
python3 scripts/project.py setup
```

The first setup requires internet access, local sudo for signed host packages/Docker, and a GitHub sign-in as `Heavenly-Cyber`. It creates a **private** GitHub repository and publishes the three saved stage tags/releases. Authentication happens on your host. The model download is approximately 2.55 GiB; image downloads and a source build are additional. Model readiness requires at least 6 GiB currently available RAM.

For a fresh clone after publication:

```bash
gh repo clone Heavenly-Cyber/rocket_proplusion_project "$HOME/git_work/rocket_proplusion_project"
cd "$HOME/git_work/rocket_proplusion_project"
python3 scripts/project.py setup --local-only
```

Pinned Python/uv image digests, the complete llama.cpp source commit, Debian snapshot, and hashed transitive `uv.lock` are committed during setup. A clone reuses those pins and builds local images; it does not refresh floating tags. Linux amd64 is the initial validated target. Other platforms need their own verification before a portability claim.

## Commands

| Command | Purpose |
| --- | --- |
| `python3 scripts/project.py setup` | Save each setup checkpoint, verify locally, then publish |
| `python3 scripts/project.py setup --local-only` | Finish local checks and leave remote publication pending |
| `python3 scripts/project.py verify --local-only` | Rerun real container/model software checks |
| `python3 scripts/project.py about` | Export the reviewed manifesto into a new `resutls/` run folder |
| `python3 scripts/project.py doctor` | Check source integrity and selected host versions |
| `python3 scripts/project.py cleanup` | Remove this repository's interrupted containers and networks |
| `python3 scripts/project.py publish` | Verify Heavenly-Cyber and publish saved tags/releases |

Every worker/model job has a unique ID, a nonroot UID/GID, CPU/RAM/PID limits, a read-only root filesystem, no added capabilities, and no host-published API ports. Research sessions use an internal Docker network. Setup resolution/download jobs need internet. Trusted image compilation uses a temporary resource-limited BuildKit builder.

Outputs stay under **`resutls/`**; operational logs stay under **`logs/`**. Models, caches, and temporary work use `models/`, `cache/`, and `tmp/`. These generated directories are ignored by Git. Containers/networks/builders are removed after work; installed Docker and reusable images/model files are retained. No benchmark measurements or proposed gap solution are claimed in this stage.
