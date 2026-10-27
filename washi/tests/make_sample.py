"""Writes tests/sample.pdf - a 6-page report with headings, paragraphs, a table, bookmarks and a small form -
for trying Washi by hand and for the UI smoke test. Run: python tests\\make_sample.py"""
import os

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sample.pdf")

SECTIONS = [
    ("Quarterly Report Q3 2026", "Northwind Paper Co.", [
        "This report summarises the third quarter of 2026 for Northwind Paper Co., a maker of hand-made washi paper "
        "for bookbinding, restoration and design studios. Revenue grew by 12 percent to EUR 4.2 million, driven by "
        "the new conservation line and strong demand from museums in Germany and Denmark.",
        "The board approved a second paper machine in Kosice. Installation starts on 3 November 2026 and the line "
        "should be producing by 15 January 2027. The project budget is EUR 640,000.",
    ]),
    ("1. Sales", None, [
        "Sales to museums and archives rose 31 percent. Retail sales were flat, while online orders through the new "
        "web shop reached 18 percent of revenue. The largest single order came from the Royal Danish Library "
        "(EUR 210,000 for 40,000 sheets of kozo paper).",
        "The sales team will focus on Austria and Poland in Q4. Target: three new archive customers by 31 December 2026.",
    ]),
    ("2. Production", None, [
        "The mill produced 412,000 sheets (+9 percent). Waste fell from 6.1 to 4.3 percent after the new drying racks "
        "were installed in August. Energy use per sheet dropped by 7 percent.",
        "Mitsumata fibre prices rose 15 percent because of a poor harvest in Kochi prefecture. Purchasing has secured "
        "supply until June 2027 at fixed prices.",
    ]),
    ("3. People", None, [
        "Two papermakers joined in September: Jana Kovacova and Tomas Horvath. Training with master papermaker "
        "Hiroshi Tanaka continues until the end of November.",
        "Staff turnover was 3 percent. The annual safety audit on 12 October 2026 found no major issues.",
    ]),
    ("4. Finance", None, [
        "Gross margin improved to 48 percent (Q2: 44 percent). Operating costs were EUR 1.6 million. Cash at the end "
        "of the quarter: EUR 1.1 million. The company has no bank debt.",
        "Risks: fibre prices, the euro / yen exchange rate and delays in delivering the new machine.",
    ]),
    ("5. Approval", None, [
        "Please review this report and sign below. Comments are due by 24 October 2026.",
    ]),
]


def main():
    doc = fitz.open()
    toc = []
    css = "body{font-family:sans-serif;font-size:11pt;line-height:1.45;color:#1b2130} h1{font-size:22pt;color:#27407a;margin:0 0 4pt} " \
          "h2{font-size:15pt;color:#27407a;margin:0 0 8pt} .sub{color:#8a7a5c;font-size:12pt;margin-bottom:14pt} p{margin:0 0 9pt}"
    for i, (title, sub, paras) in enumerate(SECTIONS):
        page = doc.new_page(width=595, height=842)
        html = (f"<h1>{title}</h1><div class='sub'>{sub}</div>" if i == 0 else f"<h2>{title}</h2>") + "".join(f"<p>{p}</p>" for p in paras)
        if title.startswith("4."):
            html += ("<table style='border-collapse:collapse;width:100%;font-size:10pt'><tr style='background:#e4e9f5'><th style='text-align:left;padding:4pt'>Item</th>"
                     "<th style='text-align:right;padding:4pt'>Q2</th><th style='text-align:right;padding:4pt'>Q3</th></tr>"
                     + "".join(f"<tr><td style='padding:4pt;border-bottom:1px solid #ddd'>{a}</td><td style='text-align:right;padding:4pt;border-bottom:1px solid #ddd'>{b}</td>"
                               f"<td style='text-align:right;padding:4pt;border-bottom:1px solid #ddd'>{c}</td></tr>"
                               for a, b, c in (("Revenue (EUR m)", "3.75", "4.20"), ("Gross margin", "44 %", "48 %"), ("Sheets produced", "378,000", "412,000"), ("Waste", "6.1 %", "4.3 %")))
                     + "</table>")
        page.insert_htmlbox(fitz.Rect(64, 64, 531, 760), html, css=css)
        page.insert_text((64, 806), f"Northwind Paper Co. · Q3 2026 · page {i + 1}", fontsize=8, color=(0.55, 0.55, 0.6))
        toc.append([1 if i == 0 or not title[0].isdigit() else 1, title, i + 1])
        if title.startswith("5."):
            for k, (label, y) in enumerate((("Name", 160), ("Date", 196))):
                page.insert_text((64, y + 14), label, fontsize=10)
                w = fitz.Widget()
                w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                w.rect = fitz.Rect(120, y, 360, y + 20)
                w.field_name = label.lower()
                w.border_color = (0.7, 0.72, 0.8)
                page.add_widget(w)
            page.insert_text((64, 248), "I approve this report", fontsize=10)
            c = fitz.Widget()
            c.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
            c.rect = fitz.Rect(190, 236, 204, 250)
            c.field_name = "approve"
            page.add_widget(c)
    toc.insert(2, [2, "Museums and archives", 2])
    doc.set_toc(toc)
    doc.set_metadata({"title": "Quarterly Report Q3 2026", "author": "Northwind Paper Co.", "subject": "Q3 results"})
    doc.save(OUT, garbage=3, deflate=True)
    print(OUT)


if __name__ == "__main__":
    main()
