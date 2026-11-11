"""Discover and perform direct conversions available in the private runtime."""
import csv
from tempfile import TemporaryDirectory
from pathlib import Path

from tools.office_files import document_operation, table_operation, write_draft
from vendor.phase3.morph_routes import Edge, routes

EDGES = [Edge("tsubasa-document", None, {"md","txt"}, {"docx","pdf"}),
         Edge("tsubasa-table", None, {"csv","tsv"}, {"xlsx"})]


def targets(path):
    source = path.suffix[1:].lower()
    if not any(source in edge.srcs for edge in EDGES):
        return []
    return sorted(routes(source, edge_list=EDGES))


def convert(path, target, output):
    if target not in targets(path):
        raise ValueError("Unsupported conversion for this source.")
    if path.stat().st_size > 2_000_000:
        raise ValueError("Source exceeds the conversion size limit.")
    with TemporaryDirectory(dir=output.parent) as directory:
        draft = Path(directory)/"draft.json"
        if target == "xlsx":
            with path.open(encoding="utf-8-sig",newline="") as stream:
                rows = csv.reader(stream, delimiter="\t" if path.suffix.lower()==".tsv" else ",")
                columns = next(rows, [])
                data = []
                for row in rows:
                    if len(data) >= 500:
                        raise ValueError("Table exceeds 500 rows.")
                    data.append(row)
            write_draft(draft,{"columns":columns,"rows":data})
            table_operation("table_export",{"format":target},draft,output)
        else:
            content = path.read_text(encoding="utf-8-sig")
            if len(content)>14000:
                raise ValueError("Document exceeds 14000 characters.")
            write_draft(draft,{"title":path.stem,"markdown":content})
            document_operation("doc_export",{"format":target},draft,output)

