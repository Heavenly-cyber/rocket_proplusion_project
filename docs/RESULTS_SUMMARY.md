# Recorded study results

Run: `study-full-20261104t230605_054765z-213fdc07`. Status: **complete**. Profile: **full**. Responses: 216/216.

LLM only: 33/108 (30.6%). RAG: 37/108 (34.3%). Difference: +3.7 percentage points.

| Family | LLM only | BM25 RAG |
|---|---:|---:|
| Mass flow | 0/18 | 0/18 |
| Thrust | 0/18 | 0/18 |
| Exit speed | 0/18 | 0/18 |
| Mixed units | 0/18 | 1/18 |
| Applicability | 15/18 | 18/18 |
| Missing inputs | 18/18 | 18/18 |

One quantized local model, small original correlated templates, fixed ideal physics. Human review of reasoning and claim support remains pending. No significance or real-engine claim.

<!-- ROCKET_TRANSPORT_TIMEOUT_NOTE -->
## Execution note

This study resumed after HTTP read timeouts. The original transport limit was 300 seconds; resumed requests allow 1800 seconds. The model, prompts, token limit, seeds, benchmark, references and scoring rules did not change. Previously received responses were retained. execution-overrides.json records the boundary.
