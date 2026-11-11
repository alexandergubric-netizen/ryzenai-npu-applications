"""Editable document and table formats used inside Tsubasa workspaces."""
import csv
import json
import re
from pathlib import Path

import pymupdf
from docx import Document
from openpyxl import Workbook


def write_draft(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def document_operation(name, args, source, output):
    if name == "doc_create":
        data = {"title": args["title"], "markdown": args["markdown"]}
    else:
        data = json.loads(source.read_text(encoding="utf-8"))
    if name == "doc_edit":
        section = args["section"]
        if section == "*":
            data["markdown"] = args["markdown"]
        else:
            lines = data["markdown"].splitlines()
            headings = [(i, len(m[1]), m[2]) for i,line in enumerate(lines)
                        if (m := re.fullmatch(r"(#{1,6}) +(.+)", line))]
            hits = [(i,n) for i,n,title in headings if title == section]
            if len(hits) != 1:
                raise ValueError("Choose a unique section heading.")
            start, depth = hits[0]
            end = next((i for i,n,_ in headings if i > start and n <= depth), len(lines))
            lines[start+1:end] = args["markdown"].splitlines()
            data["markdown"] = "\n".join(lines)
    if name in ("doc_edit","doc_create"):
        write_draft(output, data)
    elif args["format"] == "docx":
        doc = Document()
        doc.add_heading(data["title"], 0)
        for line in data["markdown"].splitlines():
            heading = re.fullmatch(r"(#{1,6}) +(.+)", line)
            if heading:
                doc.add_heading(heading[2],len(heading[1]))
            else:
                doc.add_paragraph(line)
        doc.save(output)
    elif args["format"] == "pdf":
        import html
        import os
        import subprocess
        from tempfile import TemporaryDirectory
        exe=Path(os.environ["ProgramFiles(x86)"])/"Microsoft/Edge/Application/msedge.exe"
        import time
        # Edge's profile may still be locked by a helper when this folder is removed; the job reaps it after.
        with TemporaryDirectory(dir=output.parent, ignore_cleanup_errors=True) as directory:
            folder=Path(directory)
            page=folder/"document.html"
            blocks=[]
            for line in data["markdown"].splitlines():
                heading=re.fullmatch(r"(#{1,6}) +(.+)",line)
                tag="h"+str(len(heading[1])) if heading else "p"
                blocks.append("<"+tag+">"+html.escape(heading[2] if heading else line)+"</"+tag+">")
            page.write_text("""<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'">"""+
                "<h1>"+html.escape(data["title"])+"</h1>"+"".join(blocks),encoding="utf-8")
            result=folder/"printed.pdf"
            subprocess.run([str(exe),"--headless","--disable-gpu","--disable-extensions",
                "--disable-background-networking","--disable-sync","--no-first-run","--no-pdf-header-footer",
                "--user-data-dir="+str(folder/"profile"),"--print-to-pdf="+str(result),page.resolve().as_uri()],
                check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            # Since Edge 156 the launcher returns at once and a helper process prints, so wait for a finished file.
            deadline, size = time.monotonic() + 25, -1
            while time.monotonic() < deadline:
                now = result.stat().st_size if result.is_file() else -1
                if now > 0 and now == size:
                    break
                size = now
                time.sleep(0.2)
            if not result.is_file() or not result.stat().st_size:
                raise ValueError("Edge did not produce a PDF.")
            result.rename(output)
    else:
        raise ValueError("Choose PDF or DOCX.")


def validate_grid(columns, rows):
    if not 1 <= len(columns) <= 50 or len(rows) > 500 or not all(isinstance(c,str) and 0<len(c)<=200 for c in columns):
        raise ValueError("Use 1-50 named columns and up to 500 rows.")
    for row in rows:
        if not isinstance(row,list) or len(row)!=len(columns):
            raise ValueError("Row width must match the columns.")
        for cell in row:
            if isinstance(cell,dict) and set(cell)=={"formula"} and isinstance(cell["formula"],str):
                if re.fullmatch(r"=SUM\([A-Z]{1,2}[1-9][0-9]{0,2}:[A-Z]{1,2}[1-9][0-9]{0,2}\)",cell["formula"]):
                    continue
            if cell is None or type(cell) in (bool,int,float) or isinstance(cell,str) and len(cell)<=4000:
                continue
            raise ValueError("Unsupported cell value.")


def table_operation(name, args, source, output):
    data = ({"columns":args["columns"],"rows":args["rows"]} if name=="table_create"
            else json.loads(source.read_text(encoding="utf-8")))
    if name=="table_update":
        for op in args["ops"]:
            if set(op)!={"row","column","value"}:
                raise ValueError("Supply row, column and value.")
            r,c=op["row"],op["column"]
            if type(r)!=int or type(c)!=int or not 1<=r<=len(data["rows"]) or not 1<=c<=len(data["columns"]):
                raise ValueError("Cell is outside the table.")
            data["rows"][r-1][c-1]=op["value"]
    validate_grid(data["columns"],data["rows"])
    if name in ("table_create","table_update"):
        write_draft(output,data)
        return
    rows=[data["columns"],*data["rows"]]
    if args["format"]=="xlsx":
        book=Workbook()
        for r,row in enumerate(rows,1):
            for c,value in enumerate(row,1):
                cell=book.active.cell(r,c)
                cell.value=value["formula"] if isinstance(value,dict) else value
                if isinstance(value,str):
                    cell.data_type="s"
        book.save(output)
        book.close()
    elif args["format"]=="csv":
        with output.open("w",encoding="utf-8-sig",newline="") as stream:
            writer=csv.writer(stream)
            for row in rows:
                values=[v["formula"] if isinstance(v,dict) else v for v in row]
                writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(("=","+","-","@")) else v for v in values])
    else:
        raise ValueError("Choose XLSX or CSV.")

