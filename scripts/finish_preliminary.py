#!/usr/bin/env python3
"""Finish a preliminary hand-in from saved data. Starts no LLM service."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zipfile

sys.dont_write_bytecode = True

from complete_project import Workflow, utc  # noqa: E402
from host_common import ROOT, ProjectError, folder, safe, write_json  # noqa: E402
from presentation_render_compat import ensure_impress, normalize_pptx  # noqa: E402

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell_text(cell):
    return " ".join(" ".join(node.text or "" for node in cell.findall(".//{"+A+"}t")).split())


def quality_check(out, deck, bbox):
    summary=json.loads((out/"summary.json").read_text())
    a,b=(summary["conditions"][c] for c in ("llm_only","rag"))
    if a["completed"]!=b["completed"] or summary["completed"]!=2*a["completed"]:
        raise RuntimeError("Paired observation counts differ")
    if not summary["completed"]<=summary["all_saved_responses"]<=216:
        raise RuntimeError("Saved response coverage is inconsistent")
    expected_words={}
    with zipfile.ZipFile(deck) as archive:
        package=ET.fromstring(archive.read("ppt/presentation.xml"))
        size=package.find("{"+P+"}sldSz")
        width,height=int(size.get("cx")),int(size.get("cy"))
        names=[n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml",n)]
        if len(names)!=25:
            raise RuntimeError("Expected 25 presentation slides")
        for name in names:
            number=int(re.search(r"slide(\d+)",name).group(1))
            root=ET.fromstring(archive.read(name))
            words=" ".join(n.text or "" for n in root.findall(".//{"+A+"}t"))
            if "{{" in words or "}}" in words:
                raise RuntimeError("Unfilled result field in slide "+str(number))
            expected_words[number]=Counter(re.findall(r"[A-Za-z0-9]+",words.lower()))
            for tag in ("{"+A+"}xfrm","{"+P+"}xfrm"):
                for transform in root.findall(".//"+tag):
                    off,ext=transform.find("{"+A+"}off"),transform.find("{"+A+"}ext")
                    if off is None or ext is None:
                        continue
                    x,y,cx,cy=(int(off.get("x")),int(off.get("y")),int(ext.get("cx")),int(ext.get("cy")))
                    if min(x,y)<0 or x+cx>width+9525 or y+cy>height+9525:
                        raise RuntimeError("Slide object outside the page: "+str(number))
        root=ET.fromstring(archive.read("ppt/slides/slide15.xml"))
        table=root.find(".//{"+A+"}tbl")
        rows=[[cell_text(c) for c in r.findall("{"+A+"}tc")] for r in table.findall("{"+A+"}tr")]
        if rows[1][1].replace(" ","")!=f'{a["correct"]}/{a["completed"]}' or rows[1][2].replace(" ","")!=f'{b["correct"]}/{b["completed"]}':
            raise RuntimeError("Presentation overall counts differ from the recorded summary")
        root=ET.fromstring(archive.read("ppt/slides/slide16.xml"))
        table=root.find(".//{"+A+"}tbl")
        rows=[[cell_text(c) for c in r.findall("{"+A+"}tc")] for r in table.findall("{"+A+"}tr")]
        expected=json.loads((out/"presentation-values.json").read_text())["family_table"]
        if rows!=expected:
            raise RuntimeError("Editable family table differs from recorded metrics")
        if sum(x["llm_only"]["completed"] for x in summary["families"].values())!=a["completed"]:
            raise RuntimeError("Family denominators do not sum to the paired total")
    pages=ET.fromstring(bbox.read_text()).findall(".//{*}page")
    if len(pages)!=25:
        raise RuntimeError("Rendered PDF slide count differs")
    for number,page in enumerate(pages,1):
        words=page.findall(".//{*}word")
        if len(words)<5:
            raise RuntimeError("Blank rendered slide "+str(number))
        width,height=float(page.get("width")),float(page.get("height"))
        for word in words:
            x0,x1,y0,y1=(float(word.get(k)) for k in ("xMin","xMax","yMin","yMax"))
            if min(x0,y0)<5 or x1>width-5 or y1>height-5:
                raise RuntimeError("Rendered text reaches page edge on slide "+str(number))
        actual=Counter(re.findall(r"[A-Za-z0-9]+"," ".join("".join(w.itertext()) for w in words).lower()))
        missing=sum((expected_words[number]-actual).values())
        if missing>max(2,.025*sum(expected_words[number].values())):
            raise RuntimeError("Text clipping on slide "+str(number))
    proof=dict(status="passed",slides=25,native_result_tables_match_metrics=True,
        pdf_pages=25,slide_bounds=True,pdf_text_coverage=True,new_model_requests=0,
        scope="Automated data, structural and PDF rendering checks. Slide images remain available for visual review.")
    write_json(str((out/"presentation-qc.json").relative_to(ROOT)),proof)
    return proof


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-only",action="store_true")
    args=parser.parse_args()
    options=SimpleNamespace(local_only=args.local_only,profile="presentation",budget_minutes=720,new_run=False)
    workflow=Workflow(options)
    if os.geteuid()==0:
        raise SystemExit("Run as your normal user, without sudo before the launcher")
    lock=(folder("logs/setup")/"project-command.lock").open("a")
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("The model run is still active. Press Ctrl+C once in its terminal, wait for cleanup, then rerun this finish script.")
    def stop(signum,frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,stop)
    signal.signal(signal.SIGTERM,stop)
    try:
        if workflow.runner.git("status","--porcelain","--untracked-files=all"):
            raise ProjectError("Unrelated Git changes were preserved; save them before finalizing")
        active=json.loads(safe("logs/setup/final-active-full.json").read_text())
        saved=safe(active["result_path"])
        manifest=json.loads((saved/"run-manifest.json").read_text())
        if manifest["fingerprint"]!=active["fingerprint"]:
            raise ProjectError("Saved run identity differs")
        for name,expected in manifest["source_hashes"].items():
            if not safe(name).is_file() or sha(safe(name))!=expected:
                raise ProjectError("Frozen scientific source differs: "+name)
        validation=safe("docs/final/validation")
        proof=json.loads((validation/"VALIDATION.json").read_text())
        if proof.get("status")!="passed" or proof.get("reference_status")!="passed":
            raise ProjectError("The existing passed validation receipt is unavailable")
        if shutil.disk_usage(ROOT).free<512*1024**2:
            raise ProjectError("Need at least 512 MiB free disk for the presentation package")
        workflow.connect_docker()
        workflow.rendering_tools()
        renderer=ensure_impress(workflow)
        image=manifest["images"]["worker"]["id"]
        if workflow.jobs.inspect(image,kind="image") is None:
            raise ProjectError("The saved worker image is missing; no lengthy rebuild was started")
        mounts=[(safe(n),"/app/"+n,True) for n in ("scripts","completion","configs")]
        mounts.extend([(saved,"/saved",True),(validation,"/validation",True)])
        record=workflow.jobs.job(image,["/app/scripts/build_preliminary.py"],kind="fast-presentation",
            entrypoint="/opt/venv/bin/python",extra_mounts=mounts,
            env={"PYTHONPATH":"/app:/app/src","PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0"},timeout=600)
        out=ROOT/record["result_path"]
        summary=json.loads((out/"summary.json").read_text())
        destination=folder("docs/final/preliminary")
        evidence=folder("docs/final/preliminary/evidence")
        evidence_names=["summary.json","selection.json","run-manifest.json","all-observed.csv","answers.csv",
            "all-observed-answers.json","all-answers.json","human-review.csv","saved-evidence.zip",
            "condition-comparison.png","study-report.html","RESULTS_SUMMARY.md","worked-example.json",
            "reference-validation.json","presentation-values.json"]
        for name in evidence_names:
            if (out/name).exists():
                shutil.copyfile(out/name,evidence/name)
        workflow.checkpoint(["docs/final/preliminary/evidence"],
            "results: save deadline-cutoff observations and preliminary matched-pair comparison")
        print("Saved",summary["all_saved_responses"],"responses; analysing",summary["completed_pair_count"],"matched pairs. Rendering only.",flush=True)
        from completion.presentation import reduce_text_size
        deck=out/"Rocket_Nozzle_LLM_Presentation_Preliminary.pptx"
        normalize_pptx(deck)
        pdf=out/(deck.stem+".pdf")
        bbox=out/"presentation-text-bounds.xhtml"
        profile=folder("tmp/libreoffice/"+out.name)
        for attempt in range(4):
            pdf.unlink(missing_ok=True)
            workflow.runner.run([renderer,"-env:UserInstallation="+profile.as_uri(),"--headless",
                "--infilter=Impress MS PowerPoint 2007 XML",
                "--convert-to","pdf:impress_pdf_Export","--outdir",str(out),deck.as_uri()],timeout=600)
            if not pdf.exists():
                raise ProjectError("Presentation PDF was not created")
            workflow.runner.run(["pdftotext","-bbox",str(pdf),str(bbox)],timeout=90)
            try:
                qc=quality_check(out,deck,bbox)
                break
            except RuntimeError as error:
                if attempt==3 or not any(word in str(error) for word in ("clipping","Rendered text")):
                    raise
                print("Repairing rendered text fit:",error,flush=True)
                reduce_text_size(deck)
        previews=out/"presentation-preview"
        previews.mkdir(exist_ok=True)
        workflow.runner.run(["pdftoppm","-png","-scale-to","1200",str(pdf),str(previews/"slide")],timeout=360)
        if len(list(previews.glob("slide-*.png")))!=25:
            raise ProjectError("Not all slides rendered to preview images")
        demo='''# Preliminary presentation demonstration

The full 216-response study remains unfinished. This package uses actual saved
responses and includes every available complete baseline/RAG case-and-seed pair.
No additional model inference was performed to create the presentation.

1. Open the preliminary PPTX or PDF in this folder.
2. Explain nozzle thrust and the independent worked-example.json.
3. Show the saved-response count and the number of matched pairs separately.
4. Open evidence/study-report.html to inspect actual paired responses and failures.
5. State template correlation, time-cutoff selection and pending human review.

The source run stays resumable. To finish the original 216-response study later:

```bash
cd "$HOME/git_work/rocket_proplusion_project"
python3 -B scripts/complete_project.py all
```

Use `python3 -B scripts/complete_project.py publish` to retry pending publication.
'''
        (out/"PROFESSOR_DEMO.md").write_text(demo)
        finals=[deck.name,pdf.name,"TERM_PAPER.md","TERM_PAPER.html","PRESENTER_NOTES.md",
                "PROFESSOR_DEMO.md","RESULTS_SUMMARY.md","presentation-qc.json"]
        for name in finals:
            shutil.copyfile(out/name,destination/name)
        package=out/"Rocket_Propulsion_Preliminary_Handin.zip"
        with zipfile.ZipFile(package,"w",zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(set(finals+evidence_names+["area-mach.png"])):
                if (out/name).is_file():
                    archive.write(out/name,name)
            guideline=safe("docs/final/source-material/Guidelines.pdf")
            if guideline.is_file():
                archive.write(guideline,"Professor_Guidelines.pdf")
        shutil.copyfile(package,destination/package.name)
        document=dict(status="PRELIMINARY_PRESENTATION_READY",full_study_completed=False,new_model_requests=0,
            saved_full_run=active["run_id"],all_saved_responses=summary["all_saved_responses"],
            analysed_pair_count=summary["completed_pair_count"],analysed_response_count=summary["completed"],
            original_schedule=216,cutoff_selection=summary["selection_rule"],created_utc=utc(),
            prior_validation=proof,local_rendering_qc=qc,result_path=str(out.relative_to(ROOT)),
            guideline_mapping={"rationale":[2,3],"motivation":[4],"state of art":[5],"research gap":[6],
                "approach":[11,12,14],"justification":[7,8,10],"analysis":[9,10,15,16,17,18],
                "expected versus observed":[19],"impact":[20]},
            files={name:sha(destination/name) for name in finals+[package.name]})
        write_json("docs/final/preliminary/PRELIMINARY_MANIFEST.json",document)
        workflow.checkpoint(["docs/final/preliminary"],
            "docs: save preliminary presentation paper and hand-in without further model inference")
        print("\nPRELIMINARY_PRESENTATION_READY",flush=True)
        print("PowerPoint:",destination/deck.name,flush=True)
        print("PDF:",destination/pdf.name,flush=True)
        print("Hand-in:",destination/package.name,flush=True)
        print("Full run preserved:",saved,flush=True)
        print("SAVED_AND_PUSHED" if workflow.published else "SAVED_LOCALLY_PUBLICATION_PENDING",flush=True)
        return 0
    except (ProjectError,RuntimeError,ValueError,KeyError,OSError) as error:
        print("SAVED_PROGRESS; preliminary finish stopped:",error,flush=True)
        return 1
    except KeyboardInterrupt:
        print("Stopped; source responses remain preserved.",flush=True)
        return 130
    finally:
        if workflow.jobs:
            try:
                workflow.jobs.cleanup()
            except (ProjectError,OSError) as error:
                print("Cleanup diagnostic:",error,flush=True)
        workflow.stop_keepalive.set()
        lock.close()


if __name__=="__main__":
    raise SystemExit(main())
