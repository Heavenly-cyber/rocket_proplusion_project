"""Check the Impress component and normalize an editable PPTX for import."""
import hashlib
import json
from pathlib import Path
import posixpath
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def ensure_impress(workflow):
    registry=Path("/usr/lib/libreoffice/share/registry/impress.xcd")
    query=subprocess.run(["dpkg-query","-W","-f=${db:Status-Abbrev}","libreoffice-impress"],
                         capture_output=True,text=True)
    installed=query.returncode==0 and query.stdout.startswith("ii") and registry.is_file()
    if not installed:
        print("Checking the missing LibreOffice Impress component. Java is not being installed.",flush=True)
        if not shutil.which("apt-get"):
            raise RuntimeError("LibreOffice Impress is required; the host package manager is unavailable")
        workflow.sudo()
        workflow.runner.run(["sudo","-n","apt-get","update"],timeout=600)
        args=["sudo","-n","env","DEBIAN_FRONTEND=noninteractive","apt-get","install","-y",
              "--no-remove","--no-install-recommends"]
        if query.returncode==0 and query.stdout.startswith("ii"):
            args.append("--reinstall")
        workflow.runner.run(args+["libreoffice-impress"],timeout=1800)
    if not registry.is_file():
        raise RuntimeError("The LibreOffice Impress import registry is still missing")
    for candidate in (Path("/usr/bin/libreoffice"),Path("/usr/lib/libreoffice/program/soffice")):
        if candidate.is_file():
            print("Using the installed Impress renderer:",candidate,flush=True)
            return str(candidate)
    raise RuntimeError("The system LibreOffice renderer was not found")


def normalize_pptx(deck):
    if not deck.is_file() or not zipfile.is_zipfile(deck):
        raise RuntimeError("The presentation source is missing or is not a PPTX ZIP package: "+str(deck))
    original=deck.read_bytes()
    with zipfile.ZipFile(deck) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("The presentation ZIP has a corrupt entry")
        parts={name:archive.read(name) for name in archive.namelist()}
    for required in ("[Content_Types].xml","_rels/.rels","ppt/presentation.xml"):
        if required not in parts:
            raise RuntimeError("Missing PowerPoint package entry: "+required)
    # Preserve every slide/table/notes byte. Only package metadata is changed.
    ET.register_namespace("",REL)
    relationships=0
    for name,data in list(parts.items()):
        if not name.endswith(".rels"):
            continue
        root=ET.fromstring(data)
        base="" if name=="_rels/.rels" else str(Path(name).parent.parent/Path(name).name[:-5])
        for rel in root:
            if rel.get("TargetMode")=="External":
                continue
            target=rel.get("Target","")
            absolute=target.lstrip("/") if target.startswith("/") else posixpath.normpath(
                posixpath.join(posixpath.dirname(base),target))
            if absolute not in parts:
                raise RuntimeError("Broken internal presentation link: "+name+" -> "+target)
            rel.set("Target",posixpath.relpath(absolute,posixpath.dirname(base) or "."))
            relationships+=1
        parts[name]=ET.tostring(root,encoding="utf-8",xml_declaration=True)
    ET.register_namespace("",CT)
    types=ET.fromstring(parts["[Content_Types].xml"])
    for node in types:
        if node.get("Extension")=="xml":
            node.set("ContentType","application/xml")
    if "docProps/core.xml" in parts and not any(n.get("PartName")=="/docProps/core.xml" for n in types):
        ET.SubElement(types,"{"+CT+"}Override",PartName="/docProps/core.xml",
                      ContentType="application/vnd.openxmlformats-package.core-properties+xml")
    parts["[Content_Types].xml"]=ET.tostring(types,encoding="utf-8",xml_declaration=True)
    backup=deck.with_name(deck.stem+".before-import-repair.pptx")
    if not backup.exists():
        backup.write_bytes(original)
    temp=deck.with_suffix(".repaired-pptx")
    with zipfile.ZipFile(temp,"w",zipfile.ZIP_DEFLATED) as archive:
        for name,data in parts.items():
            archive.writestr(name,data)
    temp.replace(deck)
    record=dict(scope="Impress import compatibility; slide text, values, tables and notes preserved",
                input_sha256=hashlib.sha256(original).hexdigest(),output_sha256=hashlib.sha256(deck.read_bytes()).hexdigest(),
                internal_links_verified=relationships,new_model_requests=0)
    (deck.parent/"presentation-import-repair.json").write_text(json.dumps(record,indent=2)+"\n")
    print("PowerPoint import package checked; slide content is preserved.",flush=True)
