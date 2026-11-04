# Presenter notes

## Slide 1

Introduce the topic as an evaluation of pretrained local LLM reasoning. It belongs to the broad area ML-Based Rocket Nozzle Performance Prediction, but does not train a CFD surrogate or propose a new nozzle geometry. The professor guidelines emphasize a technically justified proposal.

## Slide 2

State the research question exactly. Software readiness is established by the user terminal log, while scientific performance must come from the new run report. Theoretical calculations are ideal-flow reference calculations, not measurements of an actual engine.

## Slide 3

Explain that nozzle thrust is physically interpretable and admits conservation-based ideal references. Numerical plausibility is insufficient. A pressure-area term can materially change thrust even if exit velocity looks reasonable. The topic extends the selected ML-based prediction area to auditing pretrained language-model predictions.

## Slide 4

Give the concrete failure example: a model may return a thrust number while confusing kPa with Pa or dropping pressure thrust. The intended use is teaching and auditing, with a human remaining responsible for engineering interpretation. No operational design qualification is claimed.

## Slide 5

Sources checked 15 October 2026. These are primary arXiv records, and the three 2026 entries are preprints. Yang et al. study combustion-domain knowledge injection. ThermoQA uses programmatic thermodynamic references. PhyNiKCE integrates physics-aware CFD checks. ChatCFD demonstrates structured LLM-driven CFD automation. Do not imply these studies left all nozzle questions untouched or transfer their reported percentages to this project. Sources: https://arxiv.org/abs/2603.04452 https://arxiv.org/abs/2604.19758 https://arxiv.org/abs/2602.11666 https://arxiv.org/abs/2506.02019

## Slide 6

Use qualified language. This is a scoped review, not proof of absence or a first-ever benchmark. The contribution is the joint, reproducible evaluation of one local model on compact ideal-nozzle cases with units, evidence IDs, applicability and abstention. A small result may narrow the gap rather than establish a general weakness. Sources: https://arxiv.org/abs/2603.04452 https://arxiv.org/abs/2604.19758 https://arxiv.org/abs/2602.11666

## Slide 7

Define p0 and T0 as chamber stagnation conditions, Me as exit Mach number, gamma as heat-capacity ratio, R as specific gas constant, At as sonic throat area and Ae as exit area. F uses the pressure correction. The area-Mach relation is displayed in the appendix and implemented with a stated branch. Source: https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/thrust-equations-summary/ https://www.grc.nasa.gov/www/k-12/rocket/astar.html

## Slide 8

Explain why a small model with known assumptions is appropriate for a term-paper audit. Choked flow and the shock-free supersonic branch must be explicit. Constant gamma excludes variable heat capacity and dissociation. The model omits viscous, separation, chemical and multidimensional losses. These are not small details when applying results to a real engine.

## Slide 9

This is an analytic reference example, rounded on the slide. It is not a model inference result or engine measurement. Set gamma=1.4, R=287 J/(kg K), chamber stagnation p0=1 MPa, T0=900 K, At=0.001 m2, Me=2, and pa=100 kPa. The area relation gives Ae/At=1.6875 exactly, Te=500 K, Ve approximately 896.4 m/s, pe approximately 127.8 kPa, mass flow approximately 1.347 kg/s and thrust approximately 1.255 kN. The container reference command supplies full precision and verifies continuity. Source: https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/thrust-equations-summary/ https://www.grc.nasa.gov/www/k-12/rocket/astar.html

## Slide 10

The reference remains outside the answering prompt. The area-Mach bisection is cross-checked with SciPy brentq. A Mach-two analytic identity and mass continuity provide independent checks. Dimensional tests reject wrong units and nonfinite values. These checks validate the implemented ideal reference, not actual rocket-engine fidelity.

## Slide 11

For each fixed case, use the same Qwen model, decoding parameters and seed in both conditions. The LLM-only condition receives no evidence passage. The RAG condition receives three BM25-selected passages. Gold values are computed only after the response arrives. Save full request payloads and raw responses. Source for the BM25 implementation: https://github.com/xhluca/bm25s

## Slide 12

The benchmark is original and generated from reviewed equation templates, but no expert human review has been completed. Each family has two development and six evaluation cases. The presentation pilot selects one fixed evaluation case per family with seed 17. Full evaluation uses all 36 cases, two conditions and three seeds for 216 responses. Template variants are correlated.

## Slide 13

Combined correctness means the answer decision is correct and the converted value lies within the frozen tolerance. Numerical tolerance is 1% relative or the per-case absolute tolerance, whichever is larger. Unit dimension is tested with Pint. Applicability is scored against the predefined issue code. Citation-ID matching is only a traceability proxy. Human review is required for claim support, and the report explicitly marks it pending.

## Slide 14

Describe the process rather than tool-installation history. Dependencies and model revisions remain locked. The host manages Git and bounded Docker orchestration. Analysis and inference execute in disposable containers. Read-only code/model mounts and resource limits remain. Generated research outputs go under the exact user-requested resutls spelling.

## Slide 15

Evidence comes from the user-supplied terminal output, not a run in the authoring environment. Commit 1ce2f541df1c3c17d009db4dd5879f3d1ecfd095 and annotated v0.3.0 establish the completed local software checkpoint. All 65 tests and Ruff passed, model SHA256 verified, local model API passed and containers/private network removed. GitHub publication stopped separately at a repository metadata guard. These are software checks and are not LLM accuracy scores.

## Slide 16

No improvement percentage is defensible before running the comparison. A positive, zero or negative RAG effect is valid. Correct source retrieval and numerical correctness can move differently. The live report will show measured counts and preserve examples, including failures. The small pilot only supports descriptive conclusions for these questions.

## Slide 17

Use the separate PROFESSOR_DEMO.md for exact commands and what to say. Before presenting, run the final ZIP and open its HTML report. During the presentation show status, the reference result and the already saved model answers. A fresh live inference run is optional and should not interrupt the talk. If the local run is incomplete, say so and show validated software readiness plus the theoretical analysis without claiming measured accuracy.

## Slide 18

Conclude with a bounded contribution. The system makes ideal-nozzle reasoning inspectable and reproducible. It can support teaching and guide targeted follow-up experiments. Future remedies include structured input validation, solver tools and assumption-aware retrieval, but this project does not claim to have proven them. The prototype does not qualify an LLM for operational propulsion design.

## Slide 19

Suggested answers are in PRESENTER_NOTES.md. Is this machine learning? It evaluates predictions from a pretrained neural language model. Why not use a solver? The solver is the independent evaluator, while the experiment measures reasoning. Is RAG novel? No, it is the comparison baseline. Does this predict a real engine? Only ideal-flow reference quantities under explicit assumptions.

## Slide 20

Full profile: 36 evaluation cases times two conditions times three seeds equals 216 responses. Keep development cases out of evaluation scoring. There are only six template families, so repeated seeds are not independent questions. No tuning on evaluation outputs is permitted without starting a new benchmark version. Human expert review and citation-support adjudication remain pending.

## Slide 21

Starting with the steady mass-flow and isentropic relations, eliminate the state ratios to obtain A/Astar. With gamma=1.4 and M=2 the exponent equals 3 and the bracket equals 1.5. Therefore A/Astar=(1/2)*(1.5)^3=1.6875. Te/T0=1/1.8=5/9, so Te=500 K for T0=900 K. Continuity independently checks the throat mass flow against rho_e*Ve*Ae. Source: https://www.grc.nasa.gov/www/k-12/rocket/astar.html

## Slide 22

Primary sources inspected 15 October 2026. Retain full references in docs/PROJECT_MANIFESTO.md and docs/LITERATURE_SEARCH.md. The professor final-presentation guidelines are the source of the nine required content points. No claimed experimental accuracy has been imported from another study.
