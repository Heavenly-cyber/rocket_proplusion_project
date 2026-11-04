"""Container entry point for references, actual model measurements and reports."""
import argparse
import csv
import hashlib
import html
import json
import os
from pathlib import Path
import statistics
import time

from completion.physics import area_ratio, reference, verification
from completion.protocol import FAMILIES, LABELS, Retriever, key, load_data, payload, schedule
from completion.scoring import evaluate


def dump(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".pending")
    temp.write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")
    temp.replace(path)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def reference_job(out):
    proof = verification()
    dump(out/"reference-validation.json", proof)
    dump(out/"worked-example.json", proof["worked_example"])
    import matplotlib.pyplot as plt
    xs = [0.1+i*0.025 for i in range(197)]
    fig, ax = plt.subplots(figsize=(9, 5))
    for gamma in (1.2, 1.3, 1.4):
        ax.plot(xs, [area_ratio(x, gamma) for x in xs], label=f"gamma={gamma}")
    ax.axvline(1, color="grey", ls="--", lw=1)
    ax.set(xlabel="Mach number", ylabel="Area ratio A/A*", ylim=(.8, 12),
           title="Ideal area-Mach relation and the two branches")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out/"area-mach.png", dpi=180)
    plt.close(fig)
    cases, _, _ = load_data()
    dump(out/"reference-cases.json", [dict(case_id=c["id"], split=c["split"],
                                          value=reference(c)[0], unit=reference(c)[1]) for c in cases])
    print("REFERENCE_VALIDATION_PASSED: 35 independent root and continuity cross-checks", flush=True)


def read_records(out, planned):
    rows = []
    for item in planned:
        path = out/"scores"/(key(item)+".json")
        if path.is_file():
            rows.append(json.loads(path.read_text()))
    return rows


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def summarize(out, manifest, cases, planned):
    records = read_records(out, planned)
    summary = dict(run_id=manifest["run_id"], profile=manifest["profile"],
                   scheduled=len(planned), completed=len(records),
                   status="complete" if len(records)==len(planned) else "partial",
                   fingerprint=manifest["fingerprint"], source_commit=manifest["source_commit"],
                   conditions={}, families={}, paired={}, human_review="pending",
                   limits="One quantized local model, small original correlated templates, fixed ideal physics. "
                          "Human review of reasoning and claim support remains pending. No significance or real-engine claim.")
    lookup = {c["id"]:c for c in cases}
    for condition in ("llm_only", "rag"):
        own = [r for r in records if r["condition"]==condition]
        total = sum(x["condition"]==condition for x in planned)
        numeric = [r for r in own if r["score"]["reference_value"] is not None]
        summary["conditions"][condition] = dict(
            scheduled=total, completed=len(own), correct=sum(r["score"]["correct"] for r in own),
            accuracy=sum(r["score"]["correct"] for r in own)/total,
            schema_valid=sum(r["score"]["schema_valid"] for r in own),
            unit_correct=sum(r["score"]["unit_correct"] is True for r in numeric),
            numeric_scheduled=sum(lookup[x["case_id"]]["reference"]["decision"]=="answer"
                                  for x in planned if x["condition"]==condition),
            empty_answers=sum(not r.get("answer", "").strip() for r in own),
            median_seconds=statistics.median(r["elapsed_seconds"] for r in own) if own else None,
            measured_request_seconds=sum(r["elapsed_seconds"] for r in own),
            mean_citation_id_precision=mean([r["score"]["citation_id_precision"] for r in own]),
            mean_retrieval_recall=mean([r["score"]["retrieved_reference_recall"] for r in own]),
            failures={category:sum(r["score"]["failure"]==category for r in own)
                      for category in ("schema", "decision", "issue", "unit", "numeric")})
    for family in FAMILIES:
        summary["families"][family] = {}
        for condition in ("llm_only", "rag"):
            own = [r for r in records if r["condition"]==condition and r["family"]==family]
            total = sum(x["condition"]==condition and lookup[x["case_id"]]["family"]==family for x in planned)
            correct = sum(r["score"]["correct"] for r in own)
            summary["families"][family][condition] = dict(correct=correct, scheduled=total,
                                                         completed=len(own), accuracy=correct/total)
    pairs = {}
    for r in records:
        pairs.setdefault((r["case_id"], r["seed"]), {})[r["condition"]] = r
    transitions = dict(both_correct=0, rag_only_correct=0, baseline_only_correct=0, both_incorrect=0)
    for pair in pairs.values():
        if len(pair)!=2:
            continue
        a, b = (pair[c]["score"]["correct"] for c in ("llm_only", "rag"))
        field = "both_correct" if a and b else "rag_only_correct" if b else "baseline_only_correct" if a else "both_incorrect"
        transitions[field] += 1
    summary["paired"] = transitions
    summary["delta_percentage_points"] = 100*(summary["conditions"]["rag"]["accuracy"]-summary["conditions"]["llm_only"]["accuracy"])
    summary["seeds"] = sorted({x["seed"] for x in planned})
    summary["unique_evaluation_cases"] = len({x["case_id"] for x in planned})
    summary["measured_request_seconds"] = sum(r["elapsed_seconds"] for r in records)
    dump(out/"summary.json", summary)
    with (out/"answers.csv").open("w", newline="") as stream:
        fields = ["case_id", "family", "condition", "seed", "correct", "schema_valid", "failure",
                  "reference_value", "reference_unit", "converted_value", "relative_error", "elapsed_seconds"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for r in records:
            flat = dict(r, **r["score"])
            writer.writerow({k:flat.get(k) for k in fields})
    with (out/"human-review.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case_id", "seed", "condition", "physical_reason_review", "citation_support_review", "reviewer", "notes"])
        for r in records:
            writer.writerow([r["case_id"], r["seed"], r["condition"], "pending", "pending", "", ""])
    dump(out/"all-answers.json", records)
    graph(out, summary)
    write_html(out, summary, records, lookup)
    write_paper(out, summary, records)
    return summary


def graph(out, summary):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for offset, condition, color, label in [(-.18,"llm_only","#28476b","LLM only"),(.18,"rag","#0c8e86","BM25 RAG")]:
        values = [100*summary["families"][f][condition]["accuracy"] for f in FAMILIES]
        ax.bar([x+offset for x in range(6)], values, width=.35, color=color, label=label)
    ax.set(xticks=range(6), xticklabels=LABELS, ylabel="Correct / scheduled responses (%)",
           ylim=(0, 110), title=f'Ideal-nozzle reliability: {summary["profile"]} ({summary["status"]})')
    ax.tick_params(axis="x", labelsize=9)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out/"condition-comparison.png", dpi=180)
    plt.close(fig)


def write_html(out, summary, records, lookup):
    esc = html.escape
    body = ["<!doctype html><html><meta charset='utf-8'><title>Rocket nozzle reliability study</title>",
            "<style>body{font:17px system-ui;max-width:1150px;margin:35px auto;padding:20px;color:#142c40}"
            "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ccd5dd;padding:12px;text-align:left}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f8;padding:15px}"
            "details{margin:16px 0;border:1px solid #ced8df;padding:14px}img{max-width:100%}</style>",
            f'<h1>Local LLM Reliability for Ideal Rocket Nozzles</h1><p>Run {esc(summary["run_id"])}. '
            f'Status: <strong>{summary["status"].upper()}</strong>. '
            f'{summary["completed"]}/{summary["scheduled"]} recorded responses.</p>',
            '<p>These are actual local model responses checked against ideal reference equations. '
            'A partial run does not support final accuracy conclusions. Missing requests remain in scheduled denominators.</p>',
            '<table><tr><th>Condition</th><th>Correct / scheduled</th><th>Schema valid</th><th>Median request time</th></tr>']
    for name, c in summary["conditions"].items():
        duration = f'{c["median_seconds"]:.1f} s' if c["median_seconds"] is not None else 'unavailable'
        body.append(f'<tr><td>{name}</td><td>{c["correct"]}/{c["scheduled"]} ({100*c["accuracy"]:.1f}%)</td>'
                    f'<td>{c["schema_valid"]}/{c["scheduled"]}</td><td>{duration}</td></tr>')
    body.extend(['</table><img src="condition-comparison.png" alt="Measured accuracy by family">',
                 f'<p>RAG minus baseline: {summary["delta_percentage_points"]:+.1f} percentage points. '
                 'Descriptive paired comparison. Repeated seeds and question templates are correlated.</p>',
                 '<p>Citation-ID precision and retrieval recall describe traceability. '
                 'They do not establish semantic support. Physical explanations and citation support await human review.</p>'])
    for r in records:
        body.append(f'<details><summary>{esc(r["case_id"])} / {r["seed"]} / {r["condition"]}: '
                    f'{"correct" if r["score"]["correct"] else r["score"]["failure"]}</summary>'
                    f'<h3>Question</h3><p>{esc(lookup[r["case_id"]]["question"])}</p>'
                    f'<h3>Raw direct answer</h3><pre>{esc(r["answer"])}</pre>'
                    f'<h3>Independent score</h3><pre>{esc(json.dumps(r["score"],indent=2))}</pre>'
                    f'<h3>Retrieved passages</h3><pre>{esc(json.dumps(r["passages"],indent=2))}</pre></details>')
    body.append(f'<h2>Limits</h2><p>{esc(summary["limits"])}</p></html>')
    (out/"study-report.html").write_text("\n".join(body))


def write_paper(out, summary, records):
    a, b = (summary["conditions"][c] for c in ("llm_only", "rag"))
    rows = "\n".join(f'| {label} | {summary["families"][f]["llm_only"]["correct"]}/{summary["families"][f]["llm_only"]["scheduled"]} | '
                     f'{summary["families"][f]["rag"]["correct"]}/{summary["families"][f]["rag"]["scheduled"]} |'
                     for f, label in zip(FAMILIES, LABELS))
    paper = f'''# Local LLM Reliability for Ideal Rocket Nozzles

**Ideal Rocket-Nozzle Performance: An Evidence and Physics Audit**  
Heavenly, Aerospace Engineering, IIT Kharagpur. Rocket Propulsion term paper.  
Run: `{summary['run_id']}`. Profile: **{summary['profile']}**. Status: **{summary['status']}**.  
Scientific source commit: `{summary['source_commit']}`. Experiment fingerprint: `{summary['fingerprint']}`.

## Abstract

This project evaluates Qwen3.5-4B Q4_K_M on ideal rocket-nozzle questions with and without three BM25-retrieved technical passages. An independent evaluator checks structured output, answer or abstention decisions, issue codes, dimensions and numerical values. This run recorded {summary['completed']} of {summary['scheduled']} scheduled responses. LLM-only produced {a['correct']}/{a['scheduled']} correct scheduled responses. BM25 RAG produced {b['correct']}/{b['scheduled']}. The descriptive difference is {summary['delta_percentage_points']:+.1f} percentage points. These counts describe this frozen benchmark and quantized local model. They do not measure real-engine accuracy or establish a general causal benefit of RAG. If the recorded status is partial, the counts are incomplete and cannot support a completed-study claim.

## 1. Topic rationale and motivation

The selected broad course topic is ML-Based Rocket Nozzle Performance Prediction. This work studies a pretrained language model rather than training a CFD surrogate. Nozzle mass flow, exhaust speed and thrust give interpretable targets with conservation-based ideal references. Fluent answers can still confuse static and stagnation pressure, miss pressure thrust or mishandle squared-length conversions. A useful engineering assistant should also identify when information is missing or the requested physical model is inappropriate.

The objective is a reproducible reliability measurement. The deterministic solver serves as the evaluator and never corrects a model answer before scoring. A weaker or unchanged RAG result is scientifically useful because it identifies the limits of supplying equations alone.

## 2. Related work and bounded research gap

Yang et al. introduce domain knowledge injection and evaluation in combustion science [1]. ThermoQA uses programmatic ground truth for engineering thermodynamics [2]. PhyNiKCE couples neural agents with physical constraints for CFD [3]. ChatCFD covers structured CFD automation, including nozzle precedent [4]. These are related approaches with different tasks and model budgets. Their reported percentages are not performance targets or findings of this experiment. The three cited 2026 records are preprints. The repository retains a fuller scoped literature-search record and its limitations.

Within the studies reviewed, the joint local-model evaluation of ideal-nozzle values, units, evidence IDs, applicability and abstention remains insufficiently characterised. This is a bounded working gap, not an exhaustive novelty claim. Ordinary RAG and deterministic physical checking are established techniques. The contribution here is their controlled, inspectable application to this specific small local-model setting.

## 3. Physics and assumptions

Assume steady one-dimensional inviscid adiabatic flow of a calorically perfect ideal gas. Chamber p0 and T0 denote stagnation conditions, R is the specific gas constant, At is sonic throat area and Ae is exit area. For appropriate choked, shock-free cases:

`F = mdot Ve + (pe - pa) Ae`

`mdot = p0 At / sqrt(T0) sqrt(gamma/R) [2/(gamma+1)]^[(gamma+1)/(2(gamma-1))]`

`Ae/At = (1/Me) [(2/(gamma+1))(1+(gamma-1)Me^2/2)]^[(gamma+1)/(2(gamma-1))]`

`Te = T0/[1+(gamma-1)Me^2/2]`, `pe = p0(Te/T0)^[gamma/(gamma-1)]`, `Ve = Me sqrt(gamma R Te)`.

The area-Mach solver explicitly selects the supersonic branch. Bisection roots are cross-checked against SciPy brentq over 35 combinations. The Mach-two identity gives Ae/At=1.6875 for gamma=1.4. Mass continuity and an independently expressed energy relation add consistency checks. A worked case uses p0=1 MPa, T0=900 K, At=0.001 m^2, Me=2, gamma=1.4, R=287 J/(kg K), pa=100 kPa. Full-precision computed values appear in `worked-example.json`.

These checks validate implementation consistency within an ideal model. They do not validate combustion chemistry, viscous losses, internal shocks, separation or real-engine performance. Supplied-state thrust questions use the given exit state directly. Applicability questions ask whether the specifically requested ideal formula can be applied.

## 4. Frozen benchmark and controlled method

The original dataset contains 48 template-generated cases in six families. Each family has two development and six evaluation cases, giving 12 development and 36 evaluation cases. Development cases enter reference checks and tests, not the scored evaluation. Full mode uses all 36 evaluation cases in two conditions and seeds 17, 43 and 89, giving 216 responses. The seeds preserve the committed CPU profile. The earlier presentation notes mentioned another third seed, so this frozen protocol is authoritative. Presentation mode uses one fixed evaluation case per family and seed 17 for 12 responses. This run used {summary['unique_evaluation_cases']} evaluation cases and seeds {summary['seeds']}.

Both conditions use the same model file, quantization, runtime, decoding settings and question inputs. The conditions differ only in supplied passages. BM25 uses the Lucene variant with k1=1.2, b=0.75 and top-k=3 without stemming or stopword removal [7]. The short corpus contains original educational paraphrases and source links, not numerical benchmark answers. The request schedule uses a frozen shuffle to reduce systematic order effects. No generated code is executed. Reference inputs, expected decisions and numerical targets never enter model prompts. The raw response is saved before the evaluator computes a reference.

## 5. Scoring and evidence

The primary score requires a valid seven-field JSON response, the correct answer/abstention decision and issue, and for numerical cases a finite value with compatible dimensions within `max(atol, 0.01*abs(reference))`. Pint converts units before comparison. Invalid JSON, empty direct answers and invalid units count as incorrect. Transport failures remain unavailable in scheduled denominators and make the run partial. Incorrect observed answers are never retried to improve the score.

Separate records retain schema validity, dimensionality, raw-number agreement, numerical error, decisions, source retrieval recall, citation-ID precision, request runtime and exposed token counts. Citation IDs are scored within RAG. An ID match does not prove semantic support. `human-review.csv` leaves physical reasoning and citation-support judgement pending. Resource limits are configuration, not measured peak RAM.

## 6. Recorded results

| Family | LLM only correct/scheduled | BM25 RAG correct/scheduled |
|---|---:|---:|
{rows}

Overall LLM-only accuracy on scheduled requests is {100*a['accuracy']:.1f}%. BM25 RAG accuracy is {100*b['accuracy']:.1f}%. The difference is {summary['delta_percentage_points']:+.1f} percentage points. Schema-valid outputs were {a['schema_valid']}/{a['scheduled']} and {b['schema_valid']}/{b['scheduled']}, respectively. The run recorded {summary['measured_request_seconds']:.1f} seconds of model-request wall time, including prompt processing and response generation. This sum excludes model loading, test execution and presentation rendering.

Paired outcomes: both correct {summary['paired']['both_correct']}, RAG alone correct {summary['paired']['rag_only_correct']}, baseline alone correct {summary['paired']['baseline_only_correct']}, both incorrect {summary['paired']['both_incorrect']}. The HTML report exposes the exact questions, raw answers, retrieved passages and independent scores. There is no synthetic model response in these metrics.

## 7. Discussion and expected outcomes

The observed difference describes the tested system. Higher citation traceability can coexist with numerical failure because retrieving a relation and calculating its value are distinct operations. A negative difference can reflect the supplied context and the model's response to it, but this experiment does not isolate individual causes. Repeated seeds and shared templates are correlated. Their response counts must not be represented as hundreds of independent engineering tasks or evidence of statistical significance.

Before measurement, retrieval could plausibly improve access to equations or applicability rules while arithmetic errors persist. Zero or negative improvement was also plausible. No minimum accuracy gain was promised. The quantitative expectations concerned execution coverage: 36 evaluation cases, two conditions, three seeds and 216 retained responses in full mode. Measured findings above are separate from those expectations.

## 8. Impact, limitations and next steps

The immediate contribution is a reproducible teaching and research audit that links local LLM output to nozzle physics and keeps failures inspectable. The main limitations are one model and quantization, a small original corpus, template correlation, strict structured-output requirements, limited ideal-flow validity and pending expert review. Prompts reveal the problem inputs and the issue-code vocabulary to both conditions, as required for fair structured evaluation. This does not claim resistance to benchmark memorization or template recognition.

A future controlled experiment could add a calculator or a required-input validator to target observed errors. Those are proposals, not implemented remedies or measured improvements here. Expert review, independent question authoring and richer thermophysical models would be needed before expanding the scientific claim.

## 9. Reproduction and saved evidence

The host launcher performs repository, disk, RAM, Docker, image, model-checksum and publication checks. Scientific code runs in bounded nonroot disposable containers on a private internal network with no published model port. Source and benchmark checkpoints precede inference. Raw requests, raw responses, metrics, figures and reports persist under `resutls/`; operational records use `logs/`. Model and image caches remain reusable. Published evidence snapshots contain the actual run artifacts. Git push failures preserve local work and are reported separately from local scientific completion.

Run `python3 -B scripts/complete_project.py all` in the repository. The default is the full study and it resumes the compatible unfinished run. Use `publish` to retry publication without repeating inference. `docs/final/FINAL_MANIFEST.json` identifies the final files and stage evidence.

## References

1. Yang et al., *A unified foundational framework for knowledge injection and evaluation of Large Language Models in Combustion Science*, 2026 preprint. https://arxiv.org/abs/2603.04452
2. Duzkar, *ThermoQA: A Three-Tier Benchmark for Evaluating Thermodynamic Reasoning in Large Language Models*, 2026 preprint. https://arxiv.org/abs/2604.19758
3. Fan et al., *PhyNiKCE: A Neurosymbolic Agentic Framework for Autonomous Computational Fluid Dynamics*, 2026 preprint. https://arxiv.org/abs/2602.11666
4. Fan et al., *ChatCFD: An LLM-Driven Agent for End-to-End CFD Automation with Structured Knowledge and Reasoning*, 2025, arXiv v3 2026. https://arxiv.org/abs/2506.02019
5. NASA Glenn, *Thrust Equations Summary*. https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/thrust-equations-summary/
6. NASA Glenn, *Compressible Area Ratio*. https://www.grc.nasa.gov/www/k-12/rocket/astar.html
7. BM25S implementation and documentation. https://github.com/xhluca/bm25s
8. NIST, *Guide for the Use of the International System of Units*, SP 811. https://www.nist.gov/pml/special-publication-811

Literature descriptions use the supplied scoped review, with the four primary arXiv records rechecked on 5 November 2026. No outside study's accuracy is substituted for this project's measurements.
'''
    (out/"TERM_PAPER.md").write_text(paper)
    summary_text = (f'# Recorded study results\n\nRun: `{summary["run_id"]}`. Status: **{summary["status"]}**. '
                    f'Profile: **{summary["profile"]}**. Responses: {summary["completed"]}/{summary["scheduled"]}.\n\n'
                    f'LLM only: {a["correct"]}/{a["scheduled"]} ({100*a["accuracy"]:.1f}%). '
                    f'RAG: {b["correct"]}/{b["scheduled"]} ({100*b["accuracy"]:.1f}%). '
                    f'Difference: {summary["delta_percentage_points"]:+.1f} percentage points.\n\n'
                    '| Family | LLM only | BM25 RAG |\n|---|---:|---:|\n'+rows+'\n\n'+summary['limits']+'\n')
    (out/"RESULTS_SUMMARY.md").write_text(summary_text)


def run(out, args):
    import httpx
    cases, corpus, protocol = load_data()
    requested = json.loads(os.environ["ROCKET_RUN_MANIFEST"])
    manifest_path = out/"run-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["fingerprint"] != requested["fingerprint"]:
            raise RuntimeError("Resume fingerprint differs; prior results preserved")
    else:
        manifest = requested
        dump(manifest_path, manifest)
    planned = schedule(cases, manifest["profile"], protocol)
    dump(out/"schedule.json", planned)
    retriever = Retriever(corpus)
    lookup = {c["id"]:c for c in cases}
    started = time.monotonic()
    failure = None
    with httpx.Client(base_url="http://llm:8080", timeout=httpx.Timeout(protocol["request_timeout_seconds"],connect=10), trust_env=False) as client:
        for _ in range(150):
            try:
                if client.get("/health", timeout=5).status_code==200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            failure = "Model health timeout"
        for index, item in enumerate(planned):
            if failure or time.monotonic()-started > args.budget_minutes*60:
                failure = failure or "Explicit inference time budget reached; rerun to resume"
                break
            ident = key(item)
            raw_path = out/"responses"/(ident+".json")
            case = lookup[item["case_id"]]
            passages = retriever.get(case["question"]) if item["condition"]=="rag" else []
            request = payload(case, passages, item["seed"], protocol)
            request_sha = digest(request)
            dump(out/"requests"/(ident+".json"), dict(payload=request, sha256=request_sha, passages=passages))
            if raw_path.exists():
                raw = json.loads(raw_path.read_text())
                if raw["request_sha256"] != request_sha:
                    raise RuntimeError("Saved response belongs to another prompt; preserved")
            else:
                raw = None
                for attempt in range(protocol["network_retries"]+1):
                    before = time.monotonic()
                    try:
                        # Use the actual server chat template for token counting. These
                        # endpoints perform tokenization, not model answer generation.
                        applied = client.post("/apply-template", json={"messages":request["messages"],
                            "add_generation_prompt":True, "chat_template_kwargs":{"enable_thinking":False}})
                        applied.raise_for_status()
                        template = applied.json()["prompt"]
                        tokenized = client.post("/tokenize", json={"content":template, "add_special":False})
                        tokenized.raise_for_status()
                        token_count = len(tokenized.json()["tokens"])
                        if token_count > protocol["max_prompt_tokens"]:
                            raise RuntimeError("Prompt exceeds frozen token budget")
                        response = client.post("/v1/chat/completions", json=request)
                        response.raise_for_status()
                        data = response.json()
                        content = data["choices"][0]["message"].get("content")
                        if content is None:
                            content = ""
                        if not isinstance(content, str):
                            raise ValueError("API content is not text")
                        raw = dict(request_sha256=request_sha, elapsed_seconds=time.monotonic()-before,
                                   prompt_tokens_preflight=token_count, response=data, answer=content,
                                   attempt=attempt+1, usage=data.get("usage", {}))
                        # Immutable received responses, including malformed answers,
                        # are saved before computing any gold value or score.
                        dump(raw_path, raw)
                        break
                    except (httpx.HTTPError, ValueError, KeyError, RuntimeError) as error:
                        problem = dict(key=ident, attempt=attempt+1, error_type=type(error).__name__,
                                       error=str(error).split(" for url ")[0], elapsed_seconds=time.monotonic()-before)
                        dump(out/"transport-failures"/(ident+f'-{time.time_ns()}.json'), problem)
                        # Only transport errors receive the one predefined retry.
                        if attempt==protocol["network_retries"] or not isinstance(error,httpx.TransportError):
                            failure = problem["error"]
                            break
            if raw is None:
                break
            score = evaluate(case, raw["answer"], passages)
            record = dict(item, family=case["family"], answer=raw["answer"],
                          passages=passages, score=score, elapsed_seconds=raw["elapsed_seconds"],
                          usage=raw.get("usage", {}), request_sha256=request_sha)
            dump(out/"scores"/(ident+".json"), record)
            print(f'[{index+1}/{len(planned)}] {ident}: {score["failure"]}', flush=True)
            if (index+1)%12==0:
                summarize(out, manifest, cases, planned)
    summary = summarize(out, manifest, cases, planned)
    dump(out/"completion-status.json", dict(status=summary["status"], error=failure,
                                            completed=summary["completed"], scheduled=len(planned)))
    print(f'STUDY_{summary["status"].upper()}: {summary["completed"]}/{len(planned)}', flush=True)
    # Partial evidence is a successful saved job, not successful final science.
    # The host decides whether stage tags/final publication are permitted.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["reference", "run"])
    parser.add_argument("--output", type=Path, default=Path("/out"))
    parser.add_argument("--budget-minutes", type=float, default=720)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.command=="reference":
        reference_job(args.output)
    else:
        run(args.output, args)


if __name__=="__main__":
    main()
