# Frozen completion protocol

The intended result is a measured comparison of the same local Qwen3.5-4B
Q4_K_M model with no supplied evidence and with the top three BM25 passages.
An independent ideal-nozzle evaluator audits its answers. This completes the
existing local-LLM project. It does not revive the earlier hybrid-propellant
sweep, train a model, or claim validated real-engine prediction.

## Actual deliverables

- A frozen original 48-case benchmark with a 12/36 development/evaluation split.
- A short original technical corpus with official NASA/NIST source links.
- Independent ideal-nozzle reference calculations and verification records.
- A default full run: 36 evaluation cases, two conditions and three seeds,
  giving 216 actual model responses. The optional presentation pilot gives 12.
- Raw requests and responses, independent scores, error categories, paired
  outcomes, CSVs, plots, an HTML evidence report and pending human-review sheet.
- A term paper, 25-slide editable PowerPoint with notes, PDF backup, rendered
  slide images, automated presentation QC, and a hand-in ZIP.
- Scoped Git checkpoints and ordinary push attempts after each saved change.

The authoritative settings are `configs/study-protocol.json`. Seeds 17, 43
and 89 preserve the existing committed CPU profile. Earlier presentation notes
mentioned seed 101 and a pilot as the primary result. The completed default
uses the full protocol and records its own identity and measured results.

## What the score means

Both conditions receive identical instructions, question inputs, allowed issue
codes and decoding settings. The evidence passages are the controlled change.
The answering prompt contains neither evaluator metadata nor numerical gold.
The evaluator computes the reference only after the received response is saved.

The primary score requires the specified seven-field JSON object, a correct
answer/abstention decision, the applicable issue code and, for numeric cases,
a finite dimensionally converted value within `max(atol, 0.01*abs(reference))`.
Malformed and empty direct answers remain incorrect. A response actually
received is immutable on resume, including an incorrect response. Transport
errors have one predefined retry and retain their diagnostics. Missing requests
leave the run partial and cannot earn final success tags.

Cited-ID precision and retrieved-reference recall are separate audit metrics.
An ID match does not establish that a passage supports a claim. Explanations,
physical assumptions and citation support require human review, which remains
explicitly pending. No human review or expert question validation is invented.

## Scientific checks

The bisection solver selects the supersonic root. SciPy brentq independently
cross-checks 35 gamma/area combinations. The exact Mach-two identity, mass
continuity, energy relation, pressure thrust and unit conversions are tested.
All existing Stage 03 tests run with the new scientific tests in the selected
worker. Installed research dependencies and source pins are retained.

The reference assumes steady one-dimensional ideal flow and a calorically
perfect gas. Choking and shock-free operation are explicit where needed.
Supplied-state thrust uses its given state. Cases that insist on a mismatched
model test applicability, rather than pretending that all richer flow problems
are insoluble. Combustion chemistry, separation and real-engine validation are
outside the claim.

## Local operation

Run as the normal desktop user. The launcher checks Git identity, repository
destinations, unrelated edits, RAM, disk, Docker, cached images, the frozen lock
and model checksum. It can rebuild missing images from existing pins and
download a missing selected model. It does not replace the host Docker
installation or silently select another model. LibreOffice Impress and Poppler
are installed with normal local sudo if needed for presentation rendering.

Source, validation, measurements and final documentation are separate saved
checkpoints. Major completed stages get annotated tags. Existing tags are never
overwritten. A later completed run uses an additional run tag when necessary.
Every checkpoint triggers an atomic normal push attempt using existing host
credentials. No token enters the repository or a container. Push/authentication
failure leaves local results available and records publication as pending.
Remote changes are never force-overwritten or automatically merged.

Research jobs use the existing nonroot CPU worker, a bounded model service,
read-only source/model mounts, no added capabilities, a private internal network
and no published host API port. Generated outputs stay under `resutls/`, logs
under `logs/`, and temporary state under `tmp/`. Compact evidence snapshots and
the final hand-in files are saved under `docs/final/` for Git publication.
Only project-owned interrupted containers/networks are cleaned up.

Inference resumes a compatible active run by source/runtime fingerprint.
Use `--new-run` only to request a distinct preserved measurement. The default
per-invocation inference budget is 720 minutes, not a predicted running time.
Each request has a 300-second timeout. Budget exhaustion saves a partial run.
Rerunning the same command resumes the remaining requests.

## Presentation compliance

The supplied professor guidelines remain in `source-material/Guidelines.pdf`.
The earlier partial deck and notes are preserved alongside them. The completed
deck covers topic rationale, motivation, related work, a bounded research gap,
the approach and scientific justification, assumptions, theoretical and
computational analysis, actual results, expected outcomes and impact.
The final manifest maps all nine requirements to slide numbers.

All numerical result fields and the editable chart workbook come from the
measured summary. A local LibreOffice render supplies the PDF and all slide
PNGs. Automated QC checks slide bounds, filled fields, chart/metric agreement,
page count, visible text bounds and PPTX-to-PDF word coverage. A bounded text-fit
repair rerenders if needed. These are automated checks, not a claim that a human
has inspected the presentation. The slide PNGs remain available for review.

## Commands

```bash
python3 -B scripts/complete_project.py all
python3 -B scripts/complete_project.py status
python3 -B scripts/complete_project.py publish
```

The old `scripts/project.py` intentionally guards only Stage 03 ancestry and
cannot orchestrate later commits. Use the new completion launcher for this
completed study. `--local-only` skips remote publication and
`--profile presentation` explicitly selects the small pilot.

The supplied related-work records were checked against primary arXiv pages on
5 November 2026. The original literature-search limits still apply. Study-specific
percentages from other papers are never inserted as this project's results.
