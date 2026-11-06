"""Create an honest presentation from saved responses, with no model requests."""
import argparse
import copy
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import statistics
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
for prefix, uri in (("a", A), ("p", P), ("r", R)):
    ET.register_namespace(prefix, uri)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def average(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def summarize(records, selected, original, manifest, families):
    selected_keys = {(r["case_id"], r["seed"], r["condition"]) for r in selected}
    result = dict(
        run_id=manifest["run_id"], profile="preliminary completed pairs", status="preliminary",
        scheduled=len(selected), completed=len(selected), source_commit=original["source_commit"],
        fingerprint=manifest["fingerprint"], conditions={}, families={}, paired={}, human_review="pending",
        all_saved_responses=len(records), original_full_schedule=216, original_full_run_status="incomplete",
        unpaired_responses_retained=len(records)-len(selected),
        completed_pair_count=len(selected)//2,
        selection_rule="All case/seed pairs with both received responses at the interruption cutoff; no score-based filtering",
        selected_keys=[list(k) for k in sorted(selected_keys)],
        seeds=sorted({r["seed"] for r in selected}),
        unique_evaluation_cases=len({r["case_id"] for r in selected}),
        measured_request_seconds=sum(r["elapsed_seconds"] for r in selected),
        all_saved_request_seconds=sum(r["elapsed_seconds"] for r in records),
        limits="Time-limited preliminary evaluation. Availability at the interruption cutoff determined inclusion. "
               "The planned 216-response study is incomplete. Templates and repeated seeds are correlated. "
               "No significance, expert-review or real-engine validation claim.",
    )
    for condition in ("llm_only", "rag"):
        own = [r for r in selected if r["condition"] == condition]
        numeric = [r for r in own if r["score"]["reference_value"] is not None]
        total = len(own)
        result["conditions"][condition] = dict(
            scheduled=total, completed=total, correct=sum(r["score"]["correct"] for r in own),
            accuracy=sum(r["score"]["correct"] for r in own)/total,
            schema_valid=sum(r["score"]["schema_valid"] for r in own),
            unit_correct=sum(r["score"]["unit_correct"] is True for r in numeric), numeric_scheduled=len(numeric),
            empty_answers=sum(not r["answer"].strip() for r in own),
            median_seconds=statistics.median(r["elapsed_seconds"] for r in own),
            measured_request_seconds=sum(r["elapsed_seconds"] for r in own),
            mean_citation_id_precision=average([r["score"]["citation_id_precision"] for r in own]),
            mean_retrieval_recall=average([r["score"]["retrieved_reference_recall"] for r in own]),
            failures={category:sum(r["score"]["failure"]==category for r in own)
                      for category in ("schema", "decision", "issue", "unit", "numeric")},
        )
    for family in families:
        result["families"][family] = {}
        for condition in ("llm_only", "rag"):
            own = [r for r in selected if r["family"]==family and r["condition"]==condition]
            n, correct = len(own), sum(r["score"]["correct"] for r in own)
            result["families"][family][condition] = dict(correct=correct, scheduled=n, completed=n,
                                                         accuracy=correct/n if n else None)
    pairs = {}
    for r in selected:
        pairs.setdefault((r["case_id"],r["seed"]), {})[r["condition"]] = r
    transitions = dict(both_correct=0, rag_only_correct=0, baseline_only_correct=0, both_incorrect=0)
    for pair in pairs.values():
        a, b = (pair[c]["score"]["correct"] for c in ("llm_only","rag"))
        key = "both_correct" if a and b else "rag_only_correct" if b else "baseline_only_correct" if a else "both_incorrect"
        transitions[key] += 1
    result["paired"] = transitions
    result["delta_percentage_points"] = 100*(result["conditions"]["rag"]["accuracy"]-result["conditions"]["llm_only"]["accuracy"])
    return result


def write_csv(path, records):
    fields = ["case_id", "family", "seed", "condition", "correct", "failure", "schema_valid",
              "reference_value", "reference_unit", "converted_value", "relative_error", "elapsed_seconds"]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            values = dict(record, **record["score"])
            writer.writerow({name:values.get(name) for name in fields})


def shape_text(root, name, value):
    for shape in root.findall(".//{"+P+"}sp"):
        identity = shape.find("{"+P+"}nvSpPr/{"+P+"}cNvPr")
        if identity is not None and identity.get("name")==name:
            nodes = shape.findall(".//{"+A+"}t")
            if not nodes:
                raise RuntimeError("Missing named text in slide")
            nodes[0].text = value
            for node in nodes[1:]:
                node.text = ""
            return
    raise RuntimeError("Missing slide shape: "+name)


def fill_cell(cell, value):
    body = cell.find("{"+A+"}txBody")
    paragraphs = body.findall("{"+A+"}p")
    paragraph = paragraphs[0]
    for extra in paragraphs[1:]:
        body.remove(extra)
    nodes = paragraph.findall(".//{"+A+"}t")
    nodes[0].text = str(value)
    for node in nodes[1:]:
        node.text = ""
    for node in paragraph.iter():
        if node.tag.rsplit("}",1)[-1] in {"rPr","defRPr","endParaRPr"}:
            node.set("sz","1800")


def update_deck(deck, summary, labels, families):
    with zipfile.ZipFile(deck) as archive:
        parts = {name:archive.read(name) for name in archive.namelist()}
    source_table = ET.fromstring(parts["ppt/slides/slide15.xml"]).find(".//{"+P+"}graphicFrame")
    # Replace the family chart with an editable count table so unmeasured
    # families are shown as N/A rather than as a zero-percent bar.
    table_frame = copy.deepcopy(source_table)
    table = table_frame.find(".//{"+A+"}tbl")
    old_rows = table.findall("{"+A+"}tr")
    header, row_template = copy.deepcopy(old_rows[0]), copy.deepcopy(old_rows[1])
    for row in old_rows:
        table.remove(row)
    values = [["Family", "LLM only", "BM25 RAG"]]
    for family, label in zip(families, labels):
        row = [label]
        for condition in ("llm_only","rag"):
            cell = summary["families"][family][condition]
            row.append(f'{cell["correct"]}/{cell["scheduled"]} ({100*cell["accuracy"]:.1f}%)'
                       if cell["scheduled"] else "N/A: no pairs")
        values.append(row)
    total_height = sum(int(r.get("h")) for r in old_rows)
    for index, values_row in enumerate(values):
        row = copy.deepcopy(header if index==0 else row_template)
        row.set("h",str(total_height//len(values)))
        for cell, value in zip(row.findall("{"+A+"}tc"), values_row):
            fill_cell(cell,value)
        table.append(row)
    slide16 = ET.fromstring(parts["ppt/slides/slide16.xml"])
    tree = slide16.find("{"+P+"}cSld/{"+P+"}spTree")
    for frame in list(tree):
        if frame.tag=="{"+P+"}graphicFrame":
            tree.remove(frame)
    tree.append(table_frame)
    shape_text(slide16,"title","Preliminary results by question family")
    shape_text(slide16,"foot","Complete pairs only. N/A means no completed pair for that family.")
    parts["ppt/slides/slide16.xml"] = ET.tostring(slide16,encoding="utf-8",xml_declaration=True)
    relname="ppt/slides/_rels/slide16.xml.rels"
    relations=ET.fromstring(parts[relname])
    removed=[]
    for node in list(relations):
        if node.get("Type","").endswith("/chart"):
            target=node.get("Target")
            if not target.startswith("/"):
                raise RuntimeError("Unexpected source chart path")
            removed.append(target.lstrip("/"))
            relations.remove(node)
    parts[relname]=ET.tostring(relations,encoding="utf-8",xml_declaration=True)
    content=ET.fromstring(parts["[Content_Types].xml"])
    for name in removed:
        parts.pop(name,None)
        for item in list(content):
            if item.get("PartName")=="/"+name:
                content.remove(item)
    parts["[Content_Types].xml"]=ET.tostring(content,encoding="utf-8",xml_declaration=True)
    for number in range(1,26):
        name=f"ppt/slides/slide{number}.xml"
        root=ET.fromstring(parts[name])
        if number==1:
            shape_text(root,"subtitle","Ideal Rocket-Nozzle Performance:\nA Preliminary Evidence and Physics Audit")
        else:
            shape_text(root,"run",f'PRELIMINARY: {summary["all_saved_responses"]} saved responses, '
                       f'{summary["completed_pair_count"]} completed pairs. Planned full study: 216 responses.')
        if number==12:
            shape_text(root,"foot",f'{summary["all_saved_responses"]}/216 saved. '
                       f'{summary["completed"]} responses in {summary["completed_pair_count"]} matched pairs analysed.')
        if number==15:
            shape_text(root,"title","Preliminary paired reliability")
            shape_text(root,"foot",f'{summary["completed_pair_count"]} matched case/seed pairs. '
                       f'RAG difference: {summary["delta_percentage_points"]:+.1f} percentage points.')
            for text in root.findall(".//{"+A+"}t"):
                if text.text=="Correct / scheduled":
                    text.text="Correct / paired records"
        if number==19:
            for text in root.findall(".//{"+A+"}t"):
                if text.text and text.text.startswith("Recorded coverage:"):
                    text.text=f'{summary["all_saved_responses"]}/216 saved; full study unfinished'
        parts[name]=ET.tostring(root,encoding="utf-8",xml_declaration=True)
    with zipfile.ZipFile(deck,"w",zipfile.ZIP_DEFLATED) as archive:
        for name,data in parts.items():
            archive.writestr(name,data)
    return values


def build(saved, out):
    from completion import presentation, worker
    from completion.protocol import FAMILIES, LABELS, key, load_data
    from completion.scoring import evaluate
    cases, _, _ = load_data()
    lookup={c["id"]:c for c in cases}
    original=json.loads((saved/"run-manifest.json").read_text())
    schedule=json.loads((saved/"schedule.json").read_text())
    records=[]
    source_hashes={}
    evidence=out/"saved-evidence.zip"
    with zipfile.ZipFile(evidence,"w",zipfile.ZIP_DEFLATED) as archive:
        for item in schedule:
            ident=key(item)
            raw_path=saved/"responses"/(ident+".json")
            if not raw_path.is_file():
                continue
            raw=json.loads(raw_path.read_text())
            request_path=saved/"requests"/(ident+".json")
            request=json.loads(request_path.read_text())
            request_sha=hashlib.sha256(json.dumps(request["payload"],sort_keys=True).encode()).hexdigest()
            if request_sha!=raw["request_sha256"] or request_sha!=request["sha256"]:
                raise RuntimeError("Saved request/response identity differs: "+ident)
            case=lookup[item["case_id"]]
            score=evaluate(case,raw["answer"],request["passages"])
            record=dict(item,family=case["family"],answer=raw["answer"],passages=request["passages"],
                        elapsed_seconds=raw["elapsed_seconds"],usage=raw.get("usage",{}),score=score,
                        request_sha256=request_sha)
            records.append(record)
            for path in (raw_path,request_path):
                relative=path.relative_to(saved).as_posix()
                archive.write(path,relative)
                source_hashes[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
        for filename in ("run-manifest.json","schedule.json","execution-overrides.json","container-lifecycle.json"):
            if (saved/filename).exists():
                archive.write(saved/filename,filename)
        for path in sorted((saved/"transport-failures").glob("*.json")):
            archive.write(path,path.relative_to(saved))
    if not records:
        raise RuntimeError("No saved model responses are available")
    groups={}
    for record in records:
        groups.setdefault((record["case_id"],record["seed"]),{})[record["condition"]]=record
    selected=[pair[condition] for _,pair in sorted(groups.items()) if len(pair)==2
              for condition in ("llm_only","rag")]
    if not selected:
        raise RuntimeError("No completed baseline/RAG pair exists yet; original responses are preserved")
    selection=dict(parent_run_id=original["run_id"],parent_fingerprint=original["fingerprint"],
        stopped_early_for="Presentation deadline; no further model requests",
        all_saved_count=len(records),full_scheduled=216,
        inclusion_rule="All complete case/seed pairs at cutoff, regardless of correctness",
        selected=[key(r) for r in selected],source_response_hashes=source_hashes,
        full_run_complete=False)
    fingerprint=hashlib.sha256(json.dumps(selection,sort_keys=True).encode()).hexdigest()
    manifest=dict(run_id="preliminary-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"),profile="preliminary completed pairs",fingerprint=fingerprint,
        source_commit=original["source_commit"],started_utc=datetime.now(timezone.utc).isoformat(),
        parent_run_manifest=original,selection=selection,
        aggregation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_model_requests=0)
    summary=summarize(records,selected,original,manifest,FAMILIES)
    dump(out/"run-manifest.json",manifest)
    dump(out/"selection.json",selection)
    dump(out/"summary.json",summary)
    dump(out/"all-answers.json",selected)
    dump(out/"all-observed-answers.json",records)
    write_csv(out/"answers.csv",selected)
    write_csv(out/"all-observed.csv",records)
    with (out/"human-review.csv").open("w",newline="") as stream:
        writer=csv.writer(stream)
        writer.writerow(["case_id","seed","condition","physical_reason_review","citation_support_review"])
        for r in records:
            writer.writerow([r["case_id"],r["seed"],r["condition"],"pending","pending"])
    for filename in ("worked-example.json","reference-validation.json","reference-cases.json","area-mach.png"):
        source=saved/filename
        if not source.exists():
            source=Path("/validation")/filename
        if source.exists():
            shutil.copyfile(source,out/filename)
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,5))
    for offset,condition,label,color in ((-.18,"llm_only","LLM only","#28476B"),(.18,"rag","BM25 RAG","#0C8E86")):
        values=[summary["families"][f][condition]["accuracy"] for f in FAMILIES]
        ax.bar([i+offset for i in range(6)],
               [100*v if v is not None else math.nan for v in values],width=.35,label=label,color=color)
    ax.set(xticks=range(6),xticklabels=LABELS,ylabel="Correct / completed paired responses (%)",ylim=(0,110),
           title=f'Preliminary paired evaluation: {len(records)} saved responses, {len(selected)//2} pairs')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out/"condition-comparison.png",dpi=160)
    plt.close(fig)
    worker.write_paper(out,summary,selected)
    worker.write_html(out,summary,selected,lookup)
    statement=(f'PRELIMINARY EVALUATION. {len(records)} actual model responses were saved from the planned '
        f'216-request schedule. The primary comparison uses all {len(selected)//2} case/seed pairs '
        f'({len(selected)} responses) for which both conditions completed. '
        f'The other {len(records)-len(selected)} unpaired responses remain in all-observed.csv and the raw evidence ZIP. '
        'The run stopped for the presentation deadline. Pair inclusion did not depend on correctness. '
        'The full 216-response study remains unfinished. Rates refer to this observed paired subset only.')
    paper=out/"TERM_PAPER.md"
    paper.write_text(paper.read_text().replace("## Abstract","**"+statement+"**\n\n## Abstract",1)+
        "\n\n## Time cutoff and selection limitation\n\n"+statement+
        "\n\nNo paired data for a family means unmeasured, not zero accuracy. "
        "Stop-time availability may depend on problem difficulty. The paired subset need not represent the whole benchmark.\n")
    report=out/"study-report.html"
    text=report.read_text().replace("<h1>",'<p><strong>'+html.escape(statement)+'</strong></p><h1>',1)
    rows=[]
    for r in records:
        rows.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in
            (r["case_id"],r["seed"],r["condition"],r["score"]["correct"],r["score"]["failure"]))+'</tr>')
    text=text.replace('</html>','<h2>All received responses</h2><p>Includes unmatched observations. '
        'These rows are not pooled into the paired accuracy comparison.</p><table><tr><th>Case</th><th>Seed</th>'
        '<th>Condition</th><th>Correct</th><th>Failure label</th></tr>'+''.join(rows)+'</table></html>')
    report.write_text(text)
    validation=json.loads(Path("/validation/VALIDATION.json").read_text())
    # The preliminary deck uses a native table for family counts; no model or
    # scoring source is changed to adapt the existing presentation template.
    presentation.attach_measured_chart=lambda parts,summary:None
    deck=presentation.create_deck(out,validation)
    table_values=update_deck(deck,summary,LABELS,FAMILIES)
    target=out/"Rocket_Nozzle_LLM_Presentation_Preliminary.pptx"
    deck.replace(target)
    notes=out/"PRESENTER_NOTES.md"
    notes.write_text('# Preliminary presentation scope\n\n'+statement+'\n\n'+notes.read_text()+
        '\n\nUse the family table to state exact denominators. N/A means no completed pair. '
        'Do not describe these responses as independent questions or as a completed 216-response study.\n')
    a,b=(summary["conditions"][c] for c in ("llm_only","rag"))
    (out/"RESULTS_SUMMARY.md").write_text('# Preliminary results\n\n'+statement+
        f'\n\nPaired results: LLM only {a["correct"]}/{a["completed"]} ({100*a["accuracy"]:.1f}%), '
        f'BM25 RAG {b["correct"]}/{b["completed"]} ({100*b["accuracy"]:.1f}%). '
        f'Descriptive difference {summary["delta_percentage_points"]:+.1f} percentage points.\n\n'+summary['limits']+'\n')
    dump(out/"presentation-values.json",dict(family_table=table_values,preliminary_statement=statement,
        tests_previously_passed=validation["tests_passed"],new_inference_requests=0))
    print(f'PRELIMINARY_EVIDENCE_READY: {len(records)} saved responses, {len(selected)//2} completed pairs. No new inference.',flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--saved",type=Path,default=Path("/saved"))
    parser.add_argument("--output",type=Path,default=Path("/out"))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    build(args.saved,args.output)


if __name__=="__main__":
    main()
