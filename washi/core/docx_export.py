"""PDF -> Word (.docx) without extra packages: text blocks become paragraphs (font, size, bold, italic, colour kept,
large text becomes headings), images are embedded, every PDF page starts a new Word page.

Used when pdf2docx (better layout, but needs OpenCV + NumPy) is not installed - e.g. in the shared installer."""
import re
import zipfile
from xml.sax.saxutils import escape

import fitz

EMU = 12700   # EMU per point

CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Default Extension="jpeg" ContentType="image/jpeg"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""
RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
</w:styles>"""
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')


def _font(name):
    n = re.sub(r"^[A-Z]{6}\+", "", name or "")
    n = re.split(r"[-,]", n)[0]
    n = re.sub(r"(MT|PS|Std|Pro)$", "", n)
    n = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", n).strip()
    low = n.lower()
    if "nimbus sans" in low or "helvetica" in low:
        return "Arial"
    if "nimbus roman" in low or low.startswith("times"):
        return "Times New Roman"
    if "nimbus mono" in low or "courier" in low:
        return "Courier New"
    return n or "Calibri"


def _run(text, span):
    flags, low = span["flags"], span["font"].lower()
    rpr = [f'<w:rFonts w:ascii="{escape(_font(span["font"]))}" w:hAnsi="{escape(_font(span["font"]))}" w:cs="{escape(_font(span["font"]))}"/>']
    if flags & 16 or "bold" in low or "black" in low:
        rpr.append("<w:b/>")
    if flags & 2 or "italic" in low or "oblique" in low:
        rpr.append("<w:i/>")
    color = "%06X" % (span["color"] or 0)
    if color != "000000":
        rpr.append(f'<w:color w:val="{color}"/>')
    rpr.append(f'<w:sz w:val="{max(2, round(span["size"] * 2))}"/>')
    if flags & 1:
        rpr.append('<w:vertAlign w:val="superscript"/>')
    return f'<w:r><w:rPr>{"".join(rpr)}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def export(doc, pages, path):
    body, media, rels = [], [], []
    first = doc[pages[0]].rect
    sizes = []
    for pno in pages:
        for b in doc[pno].get_text("dict")["blocks"]:
            if b.get("type") == 0:
                sizes += [s["size"] for l in b["lines"] for s in l["spans"] if s["text"].strip()]
    sizes.sort()
    normal = sizes[len(sizes) // 2] if sizes else 11
    for k, pno in enumerate(pages):
        page = doc[pno]
        blocks = sorted(page.get_text("dict", sort=True)["blocks"], key=lambda b: (round(b["bbox"][1]), b["bbox"][0]))
        for b in blocks:
            if b.get("type") == 1 and b.get("image"):
                ext = (b.get("ext") or "png").lower()
                data = b["image"]
                if ext not in ("png", "jpeg", "jpg"):
                    try:
                        data, ext = fitz.Pixmap(data).tobytes("png"), "png"
                    except Exception:  # noqa: BLE001
                        continue
                ext = "jpeg" if ext == "jpg" else ext
                n = len(media) + 1
                media.append((f"word/media/image{n}.{ext}", data))
                rid = f"rIdImg{n}"
                rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image{n}.{ext}"/>')
                x0, y0, x1, y1 = b["bbox"]
                w = int(max(1, x1 - x0) * EMU)
                h = int(max(1, y1 - y0) * EMU)
                body.append(
                    f'<w:p><w:r><w:drawing><wp:inline><wp:extent cx="{w}" cy="{h}"/><wp:docPr id="{n}" name="Image {n}"/>'
                    f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
                    f'<pic:nvPicPr><pic:cNvPr id="{n}" name="image{n}"/><pic:cNvPicPr/></pic:nvPicPr>'
                    f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                    f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
                    f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')
                continue
            if b.get("type") != 0:
                continue
            spans = [s for l in b["lines"] for s in l["spans"]]
            text = "".join(s["text"] for s in spans).strip()
            if not text:
                continue
            big = max((s["size"] for s in spans if s["text"].strip()), default=normal)
            style = ""
            if big >= normal * 1.6 and len(text) < 160:
                style = '<w:pStyle w:val="Heading1"/>'
            elif big >= normal * 1.25 and len(text) < 160:
                style = '<w:pStyle w:val="Heading2"/>'
            indent = max(0, b["bbox"][0] - first.x0 - 60)
            ppr = style + (f'<w:ind w:left="{int(indent * 20)}"/>' if 10 < indent < 300 else "")
            runs = []
            for li, line in enumerate(b["lines"]):
                for s in line["spans"]:
                    if s["text"]:
                        runs.append(_run(s["text"], s))
                if li < len(b["lines"]) - 1:
                    last = "".join(s["text"] for s in line["spans"]).rstrip()
                    if last.endswith("-") and not last.endswith(" -"):
                        continue
                    runs.append('<w:r><w:t xml:space="preserve"> </w:t></w:r>')
            body.append(f"<w:p><w:pPr>{ppr}</w:pPr>{''.join(runs)}</w:p>")
        if k < len(pages) - 1:
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
    w, h = int(first.width * 20), int(first.height * 20)
    sect = (f'<w:sectPr><w:pgSz w:w="{w}" w:h="{h}"{" w:orient=\"landscape\"" if w > h else ""}/>'
            '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>')
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {NS}><w:body>{"".join(body)}{sect}</w:body></w:document>'
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                + "".join(rels) + "</Relationships>")
    meta = doc.metadata or {}
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + escape(meta.get("title") or "") + '</dc:title><dc:creator>'
            + escape(meta.get("author") or "") + '</dc:creator></cp:coreProperties>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("docProps/core.xml", core)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        for name, data in media:
            z.writestr(name, data)
    return path
