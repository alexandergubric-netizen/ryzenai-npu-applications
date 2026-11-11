"""PDF operations for the Tsubasa worker. Output paths come from its staging broker."""
import base64
from contextlib import ExitStack, nullcontext
from types import SimpleNamespace

import pymupdf
from vendor.phase3.washi_search import search


def selected(spec, count):
    if spec.strip().lower() in ("all", "*"):
        return list(range(count))
    result = []
    for item in spec.split(","):
        bounds = item.strip().split("-")
        if len(bounds) > 2 or not all(value.isdecimal() for value in bounds):
            raise ValueError("Enter page numbers or ranges such as 1,3-5.")
        first, last = int(bounds[0]), int(bounds[-1])
        if not 1 <= first <= last <= count or len(result) + last-first+1 > 300:
            raise ValueError("Page range is outside the document or too large.")
        result.extend(range(first-1, last))
    return result


def open_pdf(stack, path):
    document = stack.enter_context(pymupdf.open(path))
    if not document.is_pdf or document.needs_pass or not 1 <= len(document) <= 300:
        raise ValueError("Choose an unlocked PDF with 1 to 300 pages.")
    return document


def perform(name, args, inputs, output=None):
    with ExitStack() as stack:
        documents = [open_pdf(stack, path) for path in inputs]
        document = documents[0]
        if name == "pdf_search":
            if not args["query"].strip():
                raise ValueError("Enter a search phrase.")
            adapter = SimpleNamespace(doc=document, lock=nullcontext(), rect_out=lambda page, rect: list(rect))
            return [{"page": hit["p"]+1, "snippet": hit["snippet"]} for hit in search(adapter, args["query"], limit=100)]
        if name == "pdf_render_page":
            index = selected(str(args["page"]), len(document))[0]
            page = document[index]
            scale = min(1.5, 900/max(1, page.rect.width, page.rect.height))
            pixels = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            return {"png": base64.b64encode(pixels.tobytes("png")).decode("ascii")}
        indexes = selected(args.get("pages", "all"), len(document))
        if name == "pdf_read":
            text = []
            remaining = 16000
            for index in indexes:
                part = document[index].get_text()[:remaining]
                text.append({"page": index+1, "text": part})
                remaining -= len(part)
                if remaining == 0:
                    break
            return text
        if name not in ("pdf_merge", "pdf_extract_pages"):
            raise ValueError("Unknown PDF operation.")
        result = stack.enter_context(pymupdf.open())
        for source in documents:
            for index in (indexes if name == "pdf_extract_pages" else range(len(source))):
                if len(result) >= 300:
                    raise ValueError("Output exceeds 300 pages.")
                result.insert_pdf(source, from_page=index, to_page=index, links=False, annots=False, widgets=False)
        result.save(output)
        return {"pages": len(result)}

