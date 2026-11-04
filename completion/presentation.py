"""Fill the editable deck with measured results, then check its local rendering."""
import html
import io
import json
import posixpath
import re
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
import zipfile
from collections import Counter

from .protocol import FAMILIES, load_data

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
for prefix, uri in (("a",A),("c",C),("p",P),("r",R)):
    ET.register_namespace(prefix,uri)


def dump(path,data):
    path.write_text(json.dumps(data,indent=2)+"\n")


def shortened(text,limit):
    text=" ".join(str(text).split())
    return text if len(text)<=limit else text[:limit-3].rstrip()+"..."


def tokens_for(out, validation):
    summary=json.loads((out/"summary.json").read_text())
    worked=json.loads((out/"worked-example.json").read_text())
    manifest=json.loads((out/"run-manifest.json").read_text())
    records=json.loads((out/"all-answers.json").read_text())
    a,b=(summary["conditions"][c] for c in ("llm_only","rag"))
    fields=dict(DATE=manifest["started_utc"][:10],RUN_ID=summary["run_id"],RUN_SHORT=summary["run_id"],
        SOURCE_COMMIT=summary["source_commit"],FINGERPRINT=summary["fingerprint"],
        PROFILE=summary["profile"],STATUS=summary["status"],COMPLETED=summary["completed"],
        SCHEDULED=summary["scheduled"],CASE_COUNT=summary["unique_evaluation_cases"],SEED_COUNT=len(summary["seeds"]),
        WORK_MACH=f'{worked["Me"]:.4g}',WORK_TE=f'{worked["Te"]:.4g}',WORK_VE=f'{worked["Ve"]:.2f}',
        WORK_PE=f'{worked["pe"]/1000:.3f}',WORK_MDOT=f'{worked["mdot"]:.6f}',WORK_F=f'{worked["F"]:.2f}',
        TEST_COUNT=validation["tests_passed"],REFERENCE_STATUS=validation["reference_status"],
        BASE_CORRECT=a["correct"],RAG_CORRECT=b["correct"],PER_CONDITION=a["scheduled"],
        BASE_ACCURACY=f'{100*a["accuracy"]:.1f}',RAG_ACCURACY=f'{100*b["accuracy"]:.1f}',
        BASE_SCHEMA=a["schema_valid"],RAG_SCHEMA=b["schema_valid"],
        BASE_LATENCY=f'{a["median_seconds"]:.1f}' if a["median_seconds"] is not None else 'n/a',
        RAG_LATENCY=f'{b["median_seconds"]:.1f}' if b["median_seconds"] is not None else 'n/a',
        DELTA=f'{summary["delta_percentage_points"]:+.1f}',
        BOTH_CORRECT=summary["paired"]["both_correct"],RAG_ONLY=summary["paired"]["rag_only_correct"],
        BASE_ONLY=summary["paired"]["baseline_only_correct"],BOTH_WRONG=summary["paired"]["both_incorrect"],
        BASE_SCHEMA_FAIL=a["failures"]["schema"],RAG_SCHEMA_FAIL=b["failures"]["schema"],
        BASE_CALC_FAIL=a["failures"]["numeric"]+a["failures"]["unit"],
        RAG_CALC_FAIL=b["failures"]["numeric"]+b["failures"]["unit"],
        OBSERVED_RESULT=f'RAG difference: {summary["delta_percentage_points"]:+.1f} percentage points',
        OBSERVED_ERRORS=f'Incorrect responses: {a["scheduled"]-a["correct"]} baseline, {b["scheduled"]-b["correct"]} RAG')
    pairs={}
    for record in records:
        if record["score"]["reference_value"] is not None:
            pairs.setdefault((record["case_id"],record["seed"]),{})[record["condition"]]=record
    candidates=[(k,v) for k,v in sorted(pairs.items()) if len(v)==2]
    selected=next(((k,v) for k,v in candidates if not all(r["score"]["correct"] for r in v.values())),
                  candidates[0] if candidates else None)
    cases,_,_=load_data()
    if selected:
        (ident,seed),pair=selected
        case=next(c for c in cases if c["id"]==ident)
        gold=pair["llm_only"]["score"]
        fields.update(EXAMPLE_ID=f'{ident}, seed {seed}',EXAMPLE_QUESTION=shortened(case["question"],245),
            EXAMPLE_REFERENCE=f'{gold["reference_value"]:.6g} {gold["reference_unit"]}')
        for condition,field in (("llm_only","EXAMPLE_BASE"),("rag","EXAMPLE_RAG")):
            record=pair[condition]
            parsed=record["score"].get("parsed_answer")
            label="correct" if record["score"]["correct"] else record["score"]["failure"]+" failure"
            value=(f'{parsed["value"]} {parsed["unit"]}, decision {parsed["decision"]}' if parsed
                   else 'Invalid JSON. '+shortened(record["answer"],85))
            fields[field]=shortened(f'{value}. Score: {label}.',175)
    else:
        fields.update(EXAMPLE_ID="No paired numerical response",EXAMPLE_QUESTION="No paired example is available in this partial run.",
                      EXAMPLE_REFERENCE="unavailable",EXAMPLE_BASE="unavailable",EXAMPLE_RAG="unavailable")
    return {"{{"+name+"}}":str(value) for name,value in fields.items()}


def workbook(categories,series):
    x="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet=ET.Element("worksheet",xmlns=x)
    data=ET.SubElement(sheet,"sheetData")
    values=[["Family",*series.keys()],*[[category,*[values[i] for values in series.values()]]
                                        for i,category in enumerate(categories)]]
    for r,row in enumerate(values,1):
        line=ET.SubElement(data,"row",r=str(r))
        for col,value in enumerate(row):
            cell=ET.SubElement(line,"c",r=chr(65+col)+str(r))
            if isinstance(value,str):
                cell.set("t","inlineStr")
                ET.SubElement(ET.SubElement(cell,"is"),"t").text=value
            else:
                ET.SubElement(cell,"v").text=str(value)
    output=io.BytesIO()
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="'+REL+'"><Relationship Id="rId1" Type="'+R+'/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml','<workbook xmlns="'+x+'" xmlns:r="'+R+'"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="'+REL+'"><Relationship Id="rId1" Type="'+R+'/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',ET.tostring(sheet,encoding="utf-8",xml_declaration=True))
    return output.getvalue()


def attach_measured_chart(parts,summary):
    categories=["Mass flow","Thrust","Exit speed","Mixed units","Applicability","Missing inputs"]
    series={name:[100*summary["families"][family][condition]["accuracy"] for family in FAMILIES]
            for name,condition in (("LLM only","llm_only"),("BM25 RAG","rag"))}
    charts=[n for n in parts if re.fullmatch(r"ppt/(?:slides/)?charts/chart\d+\.xml",n)]
    if len(charts)!=1:
        raise RuntimeError("Expected exactly one native measured chart")
    name=charts[0]
    root=ET.fromstring(parts[name])
    ns={"c":C}
    items=root.findall(".//c:ser",ns)
    if len(items)!=2:
        raise RuntimeError("Measured chart must have two series")
    for column,(node,(label,values)) in enumerate(zip(items,series.items()),1):
        col=chr(65+column)
        tx=node.find("c:tx",ns)
        if tx is None:
            tx=ET.SubElement(node,"{"+C+"}tx")
        tx.clear()
        ref=ET.SubElement(tx,"{"+C+"}strRef")
        ET.SubElement(ref,"{"+C+"}f").text=f'Sheet1!${col}$1'
        cache=ET.SubElement(ref,"{"+C+"}strCache")
        ET.SubElement(cache,"{"+C+"}ptCount",val="1")
        ET.SubElement(ET.SubElement(cache,"{"+C+"}pt",idx="0"),"{"+C+"}v").text=label
        for tag,typ,kind,range_formula,values_to_write in (
            ("cat","strRef","strCache","Sheet1!$A$2:$A$7",categories),
            ("val","numRef","numCache",f'Sheet1!${col}$2:${col}$7',values)):
            parent=node.find("c:"+tag,ns)
            if parent is None:
                parent=ET.SubElement(node,"{"+C+"}"+tag)
            parent.clear()
            ref=ET.SubElement(parent,"{"+C+"}"+typ)
            ET.SubElement(ref,"{"+C+"}f").text=range_formula
            cache=ET.SubElement(ref,"{"+C+"}"+kind)
            if typ=="numRef":
                ET.SubElement(cache,"{"+C+"}formatCode").text="0.0"
            ET.SubElement(cache,"{"+C+"}ptCount",val=str(len(values_to_write)))
            for idx,value in enumerate(values_to_write):
                ET.SubElement(ET.SubElement(cache,"{"+C+"}pt",idx=str(idx)),"{"+C+"}v").text=str(value)
    existing=root.find("c:externalData",ns)
    if existing is not None:
        root.remove(existing)
    ext=ET.Element("{"+C+"}externalData",{"{"+R+"}id":"rIdMeasuredWorkbook"})
    ET.SubElement(ext,"{"+C+"}autoUpdate",val="0")
    insertion=next((i for i,node in enumerate(root) if node.tag.rsplit('}',1)[-1] in
                    {'printSettings','userShapes','extLst'}),len(root))
    root.insert(insertion,ext)
    relname=str(Path(name).parent/"_rels"/(Path(name).name+".rels"))
    relroot=ET.fromstring(parts[relname]) if relname in parts else ET.Element("Relationships",xmlns=REL)
    for child in list(relroot):
        if child.get("Id")=="rIdMeasuredWorkbook":
            relroot.remove(child)
    ET.SubElement(relroot,"{"+REL+"}Relationship",Id="rIdMeasuredWorkbook",Type=R+"/package",
                  Target=posixpath.relpath('ppt/embeddings/measured-data.xlsx',str(Path(name).parent)))
    parts[relname]=ET.tostring(relroot,encoding="utf-8",xml_declaration=True)
    parts[name]=ET.tostring(root,encoding="utf-8",xml_declaration=True)
    parts["ppt/embeddings/measured-data.xlsx"]=workbook(categories,series)
    content=ET.fromstring(parts['[Content_Types].xml'])
    ct="http://schemas.openxmlformats.org/package/2006/content-types"
    if not any(c.get("Extension")=="xlsx" for c in content):
        ET.SubElement(content,"{"+ct+"}Default",Extension="xlsx",
                      ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    parts['[Content_Types].xml']=ET.tostring(content,encoding="utf-8",xml_declaration=True)


def create_deck(out,validation):
    assets=Path(__file__).parent/"assets"
    tokens=tokens_for(out,validation)
    with zipfile.ZipFile(assets/"results_template.pptx") as source:
        parts={n:source.read(n) for n in source.namelist()}
    for name,data in list(parts.items()):
        if name.endswith(".xml"):
            text=data.decode("utf-8")
            for token,value in tokens.items():
                text=text.replace(token,escape(value))
            if "{{" in text or "}}" in text:
                raise RuntimeError("Unfilled result field in "+name)
            parts[name]=text.encode("utf-8")
    summary=json.loads((out/"summary.json").read_text())
    attach_measured_chart(parts,summary)
    destination=out/"Rocket_Nozzle_LLM_Presentation_Final.pptx"
    with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as target:
        for name,data in parts.items():
            target.writestr(name,data)
    slides=json.loads((assets/"slides.json").read_text())
    notes=[]
    for i,slide in enumerate(slides,1):
        note=slide["notes"]
        for token,value in tokens.items():
            note=note.replace(token,value)
        notes.append(f'## Slide {i}: {slide["title"].replace(chr(10)," ")}\n\n{note}\n')
    (out/"PRESENTER_NOTES.md").write_text("# Presenter notes\n\n"+"\n".join(notes))
    # A readable local paper page is useful without a Markdown application.
    paper=(out/"TERM_PAPER.md").read_text()
    (out/"TERM_PAPER.html").write_text('<!doctype html><meta charset="utf-8"><title>Rocket Propulsion Term Paper</title>'
        '<style>body{font:17px system-ui;max-width:1000px;margin:40px auto}pre{white-space:pre-wrap;line-height:1.6;font:inherit}</style>'
        '<pre>'+html.escape(paper)+'</pre>')
    return destination


def validate_deck(out,pdf_bbox):
    deck=out/"Rocket_Nozzle_LLM_Presentation_Final.pptx"
    with zipfile.ZipFile(deck) as z:
        names=z.namelist()
        slide_names=[n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml",n)]
        if len(slide_names)!=25:
            raise RuntimeError("Final deck must have 25 slides")
        all_text=[]
        expected_page_words={}
        pres=ET.fromstring(z.read('ppt/presentation.xml'))
        size=pres.find("{"+P+"}sldSz")
        width,height=int(size.get("cx")),int(size.get("cy"))
        for name in slide_names:
            root=ET.fromstring(z.read(name))
            page_text=[t.text or "" for t in root.findall(".//{"+A+"}t")]
            all_text.extend(page_text)
            page_number=int(re.search(r'slide(\d+)',name).group(1))
            expected_page_words[page_number]=Counter(re.findall(r'[A-Za-z0-9]+',' '.join(page_text).lower()))
            for xfrm in root.findall(".//{"+A+"}xfrm"):
                off,ext=xfrm.find("{"+A+"}off"),xfrm.find("{"+A+"}ext")
                if off is None or ext is None:
                    continue
                x,y,cx,cy=(int(off.get("x")),int(off.get("y")),int(ext.get("cx")),int(ext.get("cy")))
                if x<0 or y<0 or x+cx>width+9525 or y+cy>height+9525:
                    raise RuntimeError("Slide object extends beyond the slide: "+name)
        if any("{{" in t for t in all_text):
            raise RuntimeError("Unfilled result field")
        chart_name=next(n for n in names if re.fullmatch(r"ppt/(?:slides/)?charts/chart\d+\.xml",n))
        root=ET.fromstring(z.read(chart_name))
        summary=json.loads((out/"summary.json").read_text())
        series=root.findall(".//{"+C+"}ser")
        for node,condition in zip(series,("llm_only","rag")):
            values=[float(x.text) for x in node.findall("{"+C+"}val/{"+C+"}numRef/{"+C+"}numCache/{"+C+"}pt/{"+C+"}v")]
            expected=[100*summary["families"][f][condition]["accuracy"] for f in FAMILIES]
            if values!=expected:
                raise RuntimeError("Chart differs from measured metrics")
        with zipfile.ZipFile(io.BytesIO(z.read('ppt/embeddings/measured-data.xlsx'))) as book:
            ET.fromstring(book.read('xl/worksheets/sheet1.xml'))
    pages=ET.fromstring(pdf_bbox.read_text()).findall(".//{*}page")
    if len(pages)!=25:
        raise RuntimeError("PDF slide count differs from PPTX")
    for number,page in enumerate(pages,1):
        words=page.findall(".//{*}word")
        if len(words)<5:
            raise RuntimeError(f"Blank or unreadable PDF slide {number}")
        pw,ph=float(page.get("width")),float(page.get("height"))
        for word in words:
            x0,x1,y0,y1=(float(word.get(k)) for k in ("xMin","xMax","yMin","yMax"))
            if min(x0,y0)<5 or x1>pw-5 or y1>ph-5:
                raise RuntimeError(f"Rendered text reaches slide edge on slide {number}")
        rendered=Counter(re.findall(r'[A-Za-z0-9]+',' '.join(''.join(w.itertext()) for w in words).lower()))
        expected=expected_page_words[number]
        missing=sum((expected-rendered).values())
        if missing>max(2,.025*sum(expected.values())):
            raise RuntimeError(f'Text coverage suggests clipping on slide {number}: {missing} words absent')
    proof=dict(status="passed",slides=25,native_chart_matches_metrics=True,
               editable_workbook=True,rendered_pdf_pages=len(pages),
               checks=["XML parse and object bounds","all result fields filled","chart equals recorded summary",
                       "embedded editable chart data","PDF text present on all slides","PDF text within page",
                       "PPTX-to-PDF word coverage"],
               scope="Automated structural and rendering checks. PNG previews are retained for visual review.")
    dump(out/"presentation-qc.json",proof)
    return proof


def reduce_text_size(deck):
    """Bounded automatic repair for local render overflow, retaining 17pt body minimum."""
    with zipfile.ZipFile(deck) as source:
        parts={name:source.read(name) for name in source.namelist()}
    for name,data in list(parts.items()):
        if not re.fullmatch(r'ppt/slides/slide\d+\.xml',name):
            continue
        root=ET.fromstring(data)
        for node in root.iter():
            if node.tag.rsplit('}',1)[-1] in {'rPr','defRPr','endParaRPr'} and node.get('sz'):
                size=int(node.get('sz'))
                if size>=1900:
                    node.set('sz',str(max(1700,size-200)))
        parts[name]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    with zipfile.ZipFile(deck,'w',zipfile.ZIP_DEFLATED) as target:
        for name,data in parts.items():
            target.writestr(name,data)
