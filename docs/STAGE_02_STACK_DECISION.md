# Stage 02 — stack decision and reproducibility contract

**Checkpoint:** v0.2.0 — selected tools, not a built environment.  
**Decision date:** 14 October 2026.  
**Required Stage 01 commit:** d4b28f834d75086e5f1752b4b7b48ecc4dc07684.  
**Repository:** ~/git_work/rocket_proplusion_project/.  
**Project:** Reliability of Local LLMs for Rocket Nozzle Performance Prediction.

## 1. Decision and confirmed machine

Use a Python CLI, uv-managed dependencies inside Docker, CPU llama.cpp inference, Qwen3.5-4B Q4_K_M, and BM25 retrieval.

This is the best practical starting configuration for the reported machine and initial study. It is a selection based on metadata and resource constraints, not proof of flawless installation or superior accuracy. Successful builds and real-model smoke tests remain required.

| Reported item | Value | Implication |
| --- | --- | --- |
| OS | Pop!_OS 24.04 LTS | Check the Ubuntu Noble host-package route |
| Architecture | x86_64 | Validate Linux/amd64 first |
| CPU threads | 12 | Begin with six inference threads and one request |
| RAM | 15.27 GiB | Small quantised model and bounded context |
| Free disk | 160.96 GiB | Suitable starting space; measure actual consumption |
| Host Python / Git | 3.12.3 / 2.43.0 | Adequate for patches/Git; container Python is independent |
| Docker, Compose, uv, gh | Absent | Docker is the next host prerequisite; uv stays in images |
| nvidia-smi | Absent | GPU hardware presence is not established; CPU baseline requires no GPU |

These values come from the returned report. Do not substitute another laptop's specifications or infer absent hardware from a missing command.

## 2. Exact selected versions

Primary release records and maintainer-published PyPI metadata were checked. These are direct-version inputs to the next resolver, not a complete transitive lock.

| Component | Version | Purpose |
| --- | --- | --- |
| Container Python | 3.13.16 | Stable research interpreter |
| uv | 0.13.1 | Resolve and install locked dependencies inside Docker |
| llama.cpp | v0.6.0 | CPU GGUF inference server |
| Docker Engine | 29.9.0 | Host runtime; exact distro package availability checked during setup |
| Docker Compose | 5.6.0 | Temporary job-scoped service lifecycle |
| GitHub CLI | 2.102.0 | Later repository, tag, and release publication |
| NumPy | 2.5.4 | Arrays and numerical scoring |
| SciPy | 1.18.1 | Area–Mach root solving and reference checks |
| bm25s | 0.3.13 | Sparse lexical retrieval |
| Pydantic | 2.14.1 | Strict question, answer, and run schemas |
| HTTPX | 0.28.1 | Internal model API and bounded artifact download requests |
| pypdf | 6.20.1 | Text-bearing PDF extraction with page provenance |
| Pint | 0.26.1 | Quantities and unit conversion |
| Matplotlib | 3.11.2 | Exportable charts with headless Agg |
| pytest | 9.1.1 | Development: physics, split, and lifecycle checks |
| Ruff | 0.17.0 | Development: code checks and formatting |

Use standard argparse, JSON, CSV, hashing, timestamps, and logging. Typer/Rich were considered but are unnecessary for this CLI. Host Git is retained. HTTPX uses its verified stable release, rather than a development version selected merely for recency.

Published bounds are compatible at the direct-dependency level: NumPy and SciPy require Python >=3.12; SciPy accepts NumPy >=2.0,<2.8; Pint requires Python >=3.12. Full resolution, wheel availability, imports, and actual runtime paths still require container checks.

Primary records: [Python](https://www.python.org/downloads/release/python-31316/), [uv](https://github.com/astral-sh/uv/releases/tag/0.13.1), [llama.cpp](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0), [Docker](https://docs.docker.com/engine/release-notes/29/), [Compose](https://github.com/docker/compose/releases/tag/v5.6.0), [gh](https://github.com/cli/cli/releases/tag/v2.102.0). Exact package source links are in configs/stack-selection.json.

## 3. Selected model bytes

| Field | Value |
| --- | --- |
| Original model | Qwen/Qwen3.5-4B |
| Quantisation publisher | Unsloth, a third-party GGUF publisher |
| Repository | unsloth/Qwen3.5-4B-GGUF |
| Revision | e87f176479d0855a907a41277aca2f8ee7a09523 |
| File | Qwen3.5-4B-Q4_K_M.gguf |
| Size | 2,740,937,888 bytes, approximately 2.55 GiB |
| SHA-256 | 00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4 |
| Licence | Apache-2.0 according to publisher/model metadata |
| Input | Text only; no vision projector required for this task |
| Status | Not downloaded or run by Stage 02 |

The revision, file size, and hash were retrieved from publisher metadata. Use the fixed revision, not main. Validate size/hash before accepting a download. This identifies bytes, not scientific accuracy.

Weight-file size is not total RAM usage. Runtime state, context, scratch space, and the research process need more memory. No speed or accuracy has been measured.

Start with direct-answer mode. The model card documents enable_thinking=False; its actual llama.cpp template behaviour must be tested and recorded. Never silently switch model or thinking mode.

Sources: [Original Qwen model](https://huggingface.co/Qwen/Qwen3.5-4B), [GGUF publisher](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF), [artifact metadata](https://huggingface.co/api/models/unsloth/Qwen3.5-4B-GGUF?blobs=true).

## 4. Retrieval choice and its research limit

BM25 establishes an auditable first retrieval baseline without another neural model or a database service. Use the low-level bm25s API with Lucene BM25, k1=1.2, b=0.75, and top_k=3. No stemming or stopword removal initially; reviewed tokenisation must preserve symbols and negation. Resolve score ties with stable passage IDs.

This is a **lexical RAG baseline**. It does not reproduce the combustion paper's dense-vector retrieval, and results cannot establish the reliability of all RAG methods. Paraphrase recall is a possible weakness to measure. Dense/hybrid retrieval is later work.

The maintainer describes NumPy-based sparse scoring without requiring a neural inference stack. Use the API with explicit paths, rather than CLI defaults that might write elsewhere. No published speed benchmark is claimed to apply to this laptop.

[Maintainer's release page](https://pypi.org/project/bm25s/0.3.13/).

## 5. Initial CPU protocol

These are starting settings, not measured capacities. Validate and freeze them before evaluation.

| Setting | Value |
| --- | --- |
| Inference threads / CPU limit | 6 / 6 CPUs |
| Model-service RAM limit | 8 GiB |
| Research-worker RAM / CPU limit | 2 GiB / 2 CPUs |
| Concurrent requests | 1 |
| Context | 4,096 tokens |
| Maximum prompt, including template | 2,800 tokens |
| Maximum generated output | 768 tokens |
| Retrieval | Up to three passages, budgeted with actual model tokens |
| Thinking | Disabled, with template verification |
| Temperature / top_p / top_k | 0.7 / 0.8 / 20 |
| Presence penalty | 1.5 |
| Repeat seeds | 17, 43, 89 |
| Request timeout | 300 seconds; confirm against smoke runtime |

Sampling follows the model card's direct-answer guidance. Apply identical settings to both conditions. Seeds help record repetitions but do not promise hardware-independent output.

Flag oversized prompts and truncated outputs. Do not clip important inputs silently or exclude failures from denominators. The two process limits sum to 10 GiB; this is a budget, not a guarantee. Inspect currently available memory and effective cgroup limits before a job. Any required profile change receives a commit before evaluation.

## 6. Container and storage contract

~~~mermaid
flowchart TD
    A["Host launcher and configuration"] --> B["Temporary Docker job session"]
    B --> C["CPU model service"]
    B --> D["Python research worker"]
    E["Read-only model and reviewed evidence"] --> C
    E --> D
    C <-->|Internal API| D
    F["Hidden references for evaluator only"] --> D
    D --> G["resutls/run_id"]
    B --> H["logs/run_id"]
    G --> I["Save status and remove job resources"]
    H --> I
~~~

Hidden references may enter the evaluator, never inference prompts or the retrieval index. Enforce that boundary in the answering adapter.

Default to standard Docker Engine with explicit sudo for daemon operations and **non-root container users matching host UID/GID**. Invoke the launcher as the ordinary user. Do not automatically add the account to the privileged docker group. Rootless Docker was evaluated; its bind-mount ownership needs a separately validated profile.

Each run gets a unique Compose project. Publish no host ports. Use an internal job network with no outbound Internet during inference; setup and downloads are separate online operations.

Use read-only roots, scoped writable mounts/tmpfs, dropped capabilities, no-new-privileges, CPU/memory/PID limits, and no Docker-socket mount. Never execute model-generated code. Inputs are read-only; outputs/logs/caches have designated writable paths.

Capture status and logs before removing containers and the job network. Preserve failed/interrupted output. Provide project-scoped recovery cleanup for SIGKILL, daemon failure, or host crash. Never prune unrelated resources.

The Docker daemon is host infrastructure, distinct from research containers. Job cleanup removes project containers/network. Cached images and verified weights remain for reuse.

| Path | Contents |
| --- | --- |
| resutls/<run_id>/ | Responses, scores, charts, report, run/status records |
| logs/<run_id>/ | Operational errors, stderr, timeouts |
| logs/setup/ | Patch/setup diagnostics |
| models/ | Verified ignored weights |
| data/raw/, data/processed/, data/index/ | Local sources and generated corpus/index artifacts |
| cache/, tmp/ | Bounded caches and temporary files |
| configs/, docs/ | Tracked decisions, non-secret settings, manuals |

No regenerating outputs go into the root. Configure Matplotlib Agg/cache paths and disable research-job Python bytecode. uv environments live in built images. Preserve the requested spellings resutls and rocket_proplusion_project.

## 7. Reproducibility: what remains

~~~mermaid
flowchart TD
    A["Saved Stage 02 selection"] --> B["Install and inspect Docker"]
    B --> C["Resolve packages inside container"]
    C --> D["Save lock, digests, source commit"]
    D --> E["Build and check runtime"]
    E --> F{"Checks passed?"}
    F -->|No| G["Repair, commit, and repeat"]
    G --> C
    F -->|Yes| H["Tag scaffold checkpoint"]
    H --> I["Later benchmark and model study"]
~~~

Stage 02 contains direct-version pins and fixed model identity. It does not yet contain a generated uv.lock, container digests, full llama.cpp commit, built image, downloaded model, or model output. Null fields in the version manifest explicitly represent pending work.

Stage 03 must resolve and commit:
- Transitive uv.lock with artifact hashes and locked/frozen install checks.
- Python/uv image digests and the full llama.cpp source commit, with verified retrieval.
- Built-image identities and non-Python OS/build dependency records.
- Permission, API/template, resource-limit, output-placement, failure/interrupt, and cleanup evidence.

Build llama.cpp inside Docker with native CPU compilation disabled. Record flags and platforms. Validate Linux/amd64 first; ARM64 needs its own tested build/digest. Docker can provide a Linux runtime on other desktops where supported, but emulation performance is not established here.

Cold setup needs downloads. Prepared runs should be offline. Docker does not ensure identical GPU output or bit-identical rebuilds from changing OS repositories; preserve the tested image digests and build records.

## 8. Pop!_OS setup and remote repository

Docker documents Ubuntu Noble support and excludes derivatives from official support. Verify the Ubuntu-base route locally; do not assume derivative autodetection succeeds.

Stage 03 will provide a reviewed installer with package availability checks. Preserve existing package/source/runtime state and refuse conflicts rather than remove unrelated installations. Administrative installation uses the user's local sudo prompt; scientific code runs only in containers.

No host uv, pnpm/Node, CUDA, PyTorch, Transformers, vector database, or permanent web service is needed for the first study. OCR is deferred; extraction failures go to manual review.

Later GitHub setup verifies Heavenly-Cyber. Proposed remote: Heavenly-Cyber/rocket_proplusion_project, private initially unless the user chooses public. Push saved tags and concrete releases after creating it. Current local tags are unpublished.

## 9. What this patch actually saves

Updated README, this decision, three JSON configurations, manuals, receipt, validation notes, and a read-only supplementary preflight script. The installer validates the Stage 01 commit, preserves modifications, commits the explicit patch, and tags v0.2.0.

It installs no package, downloads no model, starts no container, and takes no GitHub action. Save this selection and return its output before Stage 03.

## 10. Package and implementation sources

- [NumPy 2.5.4](https://pypi.org/project/numpy/2.5.4/)
- [SciPy 1.18.1](https://pypi.org/project/scipy/1.18.1/)
- [bm25s 0.3.13](https://pypi.org/project/bm25s/0.3.13/)
- [Pydantic 2.14.1](https://pypi.org/project/pydantic/2.14.1/)
- [HTTPX 0.28.1](https://pypi.org/project/httpx/0.28.1/)
- [pypdf 6.20.1](https://pypi.org/project/pypdf/6.20.1/)
- [Pint 0.26.1](https://pypi.org/project/Pint/0.26.1/)
- [Matplotlib 3.11.2](https://pypi.org/project/matplotlib/3.11.2/)
- [pytest 9.1.1](https://pypi.org/project/pytest/9.1.1/)
- [Ruff 0.17.0](https://pypi.org/project/ruff/0.17.0/)
- [Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/)
- [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/)
- [Official Python image variants](https://github.com/docker-library/python/blob/master/versions.json)
- [Rootless alternative](https://docs.docker.com/engine/security/rootless/)

Checked during the 14 October 2026 selection. Upgrades require a saved patch and revalidation; latest/main is never a research-run identity.

