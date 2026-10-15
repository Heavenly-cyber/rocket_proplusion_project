# Professor demonstration guide

## Run this before the presentation

Download `rocket-project-final.zip` into `~/Downloads/`. Run it as your normal user, without sudo before Python:

```bash
python3 "$HOME/Downloads/rocket-project-final.zip"
```

This one command checks the returned verified checkpoint, saves a publication fix, saves the complete benchmark source, runs tests/lint/reference analysis in disposable Docker jobs, performs the 12-response local pilot, saves reports and completed stage tags, removes resources, then attempts GitHub publication. Normal sudo prompts remain local. No return-to-chat gate separates these steps.

The default inference budget is 15 minutes, plus up to 5 minutes for model health and the other checks. This is a limit, not a measured duration guarantee. Do not start the 216-response mode immediately before presenting. The validated cached images/model must still exist. Close heavy applications if the launcher reports insufficient available RAM.

Outputs never need to leave the project: `resutls/<run-id>/` contains reference calculations, graphs, raw answers, metrics and an HTML report. `logs/` contains operational diagnostics. Cached images and model files remain. Generated reports do not appear in the root.

Expected completed local checkpoints are `v0.3.0`, `v0.4.0`, `v0.5.0`, and `v1.0.0`. The latter certify the basic measured prototype, not a full 216-response study or expert validation. Local success prints `FINAL_LOCAL_READY`. Successful remote publication prints `FINAL_SAVED_AND_PUBLISHED`. GitHub failure leaves the local presentation and results available.

## Open the presentation

```bash
cd "$HOME/git_work/rocket_proplusion_project"
xdg-open docs/presentation/Rocket_Nozzle_LLM_Presentation_Final.pptx
```

PDF backup:

```bash
xdg-open docs/presentation/Rocket_Nozzle_LLM_Presentation_Final.pdf
```

Use slides 1–18 for the main talk. Slides 19–22 contain questions, the full protocol, a derivation and references. For a shorter talk use 1, 2, 3, 5, 6, 7, 8, 9, 11, 13, 15, 16, 17 and 18. The detailed notes are in the PowerPoint notes and `docs/presentation/PRESENTER_NOTES.md`.

## Commands to show the professor, in order

### 1. Show what is saved

```bash
cd "$HOME/git_work/rocket_proplusion_project"
git status --short
git tag --list
python3 -B scripts/study.py status
```

**Show:** a clean tree and the saved status/evidence paths. **Say:** “Each completed stage has an annotated tag. Stage 03 certifies the local environment and model API. Later receipts distinguish the benchmark checks from the measured pilot.” If a later stage remains pending, say so explicitly.

### 2. Show the physical reference

```bash
python3 -B scripts/study.py reference
```

This runs only the ideal-flow reference analysis in a new bounded offline container and prints `REFERENCE_OUTPUT`. The container is then removed. Open its directory automatically:

```bash
python3 -B - <<'PY'
import json, pathlib, subprocess
root=pathlib.Path.cwd()
record=json.loads((root/'logs/setup/latest-reference.json').read_text())
folder=root/record['result_path']
print((folder/'worked-example.json').read_text())
subprocess.run(['xdg-open',str(folder/'area-mach.png')],check=False)
PY
```

**Show:** `M_e=2`, area ratio `1.6875`, `T_e=500 K`, the exit velocity/pressure, mass flow and total thrust. **Say:** “These are ideal-flow calculations under stated assumptions. The independent root cross-check and continuity test validate the reference implementation.” Explain the pressure-thrust term on slide 7 and the branch choice on slides 8–10.

### 3. Show actual measured model answers

```bash
python3 -B - <<'PY'
import json, pathlib, subprocess
root=pathlib.Path.cwd()
record=json.loads((root/'logs/setup/latest-study.json').read_text())
report=root/record['result_path']/'study-report.html'
print(report)
subprocess.run(['xdg-open',str(report)],check=False)
PY
```

**Show:** run status, response counts, correct/scheduled counts and the condition chart. Expand the two answers for one numerical case and then the applicability/missing-input case. The report includes the exact question, raw answer and separate scores. Show a real failure if one occurred. If both are correct, show the agreement rather than inventing an error.

**Say:** “This is the recorded six-case presentation pilot, with paired conditions and one seed. A larger study is supported, but this pilot is descriptive. Citation-ID matching is an audit within RAG and does not prove that every claim is supported.”

### 4. Show cleanup

```bash
sudo docker ps -a --filter label=org.heavenly.rocket.owner --format '{{.Names}} {{.Status}}'
```

**Show:** no leftover project containers after the completed command. **Say:** “The model service exists only for the job. Results and logs persist locally.” This label filter may also list another active checkout of the same project. Do not run cleanup while another project command is active.

### 5. Show the source and saved report

```bash
git log -8 --oneline
cat docs/RESULTS_SUMMARY.md
```

If publication succeeded, open the GitHub repository and releases. If it did not, show the local saved commits and explain that publication is separate from the scientific run.

## If time or inference runs out

Do not rerun inference during the talk. Show the already passed 65-test environment checkpoint, slides 7–10, and the reference-analysis outputs. An incomplete pilot report is labelled `partial`; it cannot justify an LLM accuracy claim or final success tag. The professor explicitly permits expected results if clearly distinguished from demonstrated results.

You can save all sources and presentation documents without running inference:

```bash
python3 "$HOME/Downloads/rocket-project-final.zip" --save-only
```

To complete locally without waiting for GitHub:

```bash
python3 "$HOME/Downloads/rocket-project-final.zip" --local-only
```

To retry only publication after local completion:

```bash
python3 -B scripts/study.py publish
```

To run the full study later, preserving the presentation run:

```bash
python3 -B scripts/study.py run --profile full --budget-minutes 360
```

The full run makes 216 scheduled requests. Six hours is an explicit upper budget, not a predicted duration. It creates a new output folder and does not overwrite the presentation pilot.

## Short spoken introduction

“My project examines how reliably a small local language model reasons about ideal rocket-nozzle performance. I compare the same model with and without retrieved technical passages. I check its answers against independent nozzle equations, unit conversions and applicability rules. The goal is a reproducible failure audit and a justified research proposal.”

## Questions you should be ready for

- **Why not just use a numerical solver?** The deterministic calculation is the evaluator. The experiment measures whether a language model can use physical information correctly.
- **What is the research gap?** The reviewed studies leave the joint local-model audit of nozzle numbers, units, applicability and evidence insufficiently characterised. This is not a first-ever LLM/nozzle claim.
- **What is novel?** The bounded integrated evaluation and reproducible audit, not ordinary RAG or the ideal nozzle equations.
- **Does this predict a real engine?** The reference covers stated ideal-flow assumptions. It omits shocks, variable chemistry, losses and separation.
- **What outcome do you expect?** Retrieval may help evidence access while arithmetic or applicability errors remain. A zero or negative RAG benefit is valid.
- **How strong is the evidence?** The pilot is small and template-generated. Human expert review and claim-support adjudication remain pending.

## Reproduction from a fresh clone after publication

The current presentation command deliberately reuses your completed local images and model. On another Linux amd64 host, first install Git, host Python 3.11+ and GitHub CLI/authentication as needed, then:

```bash
gh repo clone Heavenly-Cyber/rocket_proplusion_project "$HOME/git_work/rocket_proplusion_project"
cd "$HOME/git_work/rocket_proplusion_project"
python3 -B scripts/study.py bootstrap
python3 -B scripts/study.py reference
python3 -B scripts/study.py run --profile presentation --budget-minutes 15
```

`bootstrap` uses the signed host-tool policy, frozen base-image/source/uv pins and a disposable bounded builder. It downloads and checksum-verifies the model in a container. Fresh downloads and CPU compilation can take substantial time and need internet. It records new local image identities under ignored `logs/setup/` without editing released receipts or tags. The subsequent run makes new local measurements rather than claiming the committed pilot was rerun. Other architectures require separate validation. Do not use bootstrap before today's presentation when the verified cache is already present.
