# Literature-search record and limits

**Search cutoff:** 14 October 2026.  
**Purpose:** Select a feasible LLM-centred topic from the supplied propulsion list and formulate a qualified evaluation gap.  
**Method:** Targeted primary-source search, direct paper-record checks, and relevant accessible full-text inspection. This is a preliminary scoped review, not a systematic review or exhaustive novelty search.

## Queries recorded

The search used the following query strings, followed by opening the candidate primary sources:

- `large language model rocket nozzle performance prediction benchmark physics 2025 2026`
- `large language models combustion engineering retrieval augmented generation 2024 2025 2026`
- `rocket nozzle performance machine learning surrogate model 2024 2025 2026 research`
- `"large language" "nozzle" benchmark`
- `"rocket nozzle" "language models"`
- `"nozzle" "RAG" "LLM"`
- `"A multi-objective optimization approach for rocket nozzle"`
- `"ThermoQA" benchmark large language thermodynamic`
- `"PhyNiKCE"`
- `"ChatCFD" "2026" Fan structured knowledge`

Searches combined broader coverage with targeted terms. Neither the absence of a search hit nor the sources below proves that all relevant literature was found.

## Retained evidence

| ID | Primary record / fixed version | Inspection performed | Status used in proposal |
| --- | --- | --- | --- |
| P1 | [2603.04452v1](https://arxiv.org/abs/2603.04452v1) | Abstract, framework, benchmark construction, controlled retrieval results, discussion in [HTML](https://arxiv.org/html/2603.04452v1) | 2026 preprint; figures/scores not independently reproduced |
| P2 | [2604.19758v1](https://arxiv.org/abs/2604.19758v1) | Abstract, scope, tier structure, references/scoring; confirmed nozzle component inclusion in [HTML](https://arxiv.org/html/2604.19758v1) | 2026 preprint; programmatic benchmark precedent |
| P3 | [2602.11666v1](https://arxiv.org/abs/2602.11666v1) | Abstract plus validation suite and relevant limitations/results in [HTML](https://arxiv.org/html/2602.11666v1) | 2026 preprint; direct physics-aware CFD/nozzle precedent |
| P4 | [2506.02019v3](https://arxiv.org/abs/2506.02019v3) | Record, abstract, version history, linked journal DOI; nozzle inclusion verified from abstract | 2025 first submission / February 2026 revision; full independent technical review pending |
| P5 | [2504.19394v2](https://arxiv.org/abs/2504.19394v2) | Record, abstract, version history | 2025 preprint; rocketry-design precedent |
| P6 | [2401.00544v2](https://arxiv.org/abs/2401.00544v2) | Record, abstract, version history, linked Energy and AI DOI | 2024 journal-linked combustion-RAG precedent; not independently reproduced |
| P7 | [2403.02054v1](https://arxiv.org/abs/2403.02054v1) | Record and abstract; supersonic-nozzle optimisation confirmed | 2024 arXiv version; optimisation precedent |
| T1 | [NASA thrust-equations page](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/thrust-equations-summary/) | Current official page; legacy page redirect followed | Primary textbook physics source, not evidence of actual-engine accuracy |
| T2 | [NASA compressible-area-ratio page](https://www.grc.nasa.gov/www/k-12/rocket/astar.html) | Official page discussion of choking, mass flow, and area/Mach relation | Primary textbook physics source |

The date assigned to each paper follows its primary record and version history, not a search-engine crawl date. An identifier's month prefix is not substituted for the displayed submission date. Journal-linked records are described only as far as the checked record supports them.

## Overlap that prevents broad novelty claims

- LLMs already appear in rocket design, supersonic-nozzle optimisation, engineering thermodynamics, combustion retrieval, and physics-aware CFD.
- ThermoQA already includes nozzle component questions.
- ChatCFD and PhyNiKCE already include nozzle cases and physical-validity evaluation.
- A physics reference or symbolic constraint checker is therefore an established approach.

Our candidate contribution is a compact local-model evaluation of the joint combination of rocket-nozzle performance, units, evidence support, applicability, and abstention. This combination is a proposed scope, not a verified first-ever achievement.

## Sources not used as central evidence

Searches found a recent publisher entry for *A multi-objective optimization approach for rocket nozzle design based on hybrid surrogate model*, DOI [10.1016/j.physleta.2025.131200](https://doi.org/10.1016/j.physleta.2025.131200). Direct full-page access was blocked, and search metadata mixed online/issue dates. It is a follow-up lead, not the basis of a numerical or detailed method claim in the manifesto.

Secondary blogs, social posts, research aggregators, and repository metadata were not used to establish the proposal's scientific claims. Abstract-level inspection is explicitly distinguished from full-text inspection above.

## Gaps still to check before the final paper

1. Follow citations and datasets in P1–P4 for closer nozzle-specific evaluation work.
2. Check publication updates and later versions before final bibliography submission.
3. Record model and benchmark licences; do not assume that public access means redistribution permission.
4. Inspect relevant complete methods before reproducing another paper's experiment.
5. Confirm course notation and deliverable expectations from the professor's actual material if provided.
6. Update the gap if a prior study covers our exact combination or if our own baseline shows no meaningful weakness.

## How to state the gap in the term paper

Use: **“Within the studies reviewed, this joint local-model evaluation remains insufficiently characterised.”**

Avoid: “No one has applied LLMs to nozzles,” “RAG always fails beyond 60%,” “this is the first benchmark,” or “our calculator solves real-engine performance.” None is supported by this preliminary review.
