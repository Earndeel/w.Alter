#!/usr/bin/env python3
"""Fill a flat (non-AcroForm) PDF form with LEFT-ALIGNED FreeText annotations.

Usage: fill_pdf_left_align.py fields.json input.pdf output.pdf

fields.json shape (PDF coords, y=0 at TOP of page):
{
  "pages": [{"page_number": 1, "pdf_width": W, "pdf_height": H}],
  "form_fields": [
    {
      "page_number": 1,
      "description": "...",
      "entry_bounding_box": [left, top, right, bottom],
      "entry_text": {"text": "VALUE", "font_size": 10}
    }
  ]
}

Why this exists: pypdf's FreeText annotation centers text by default in its
rect, which looks wrong on ruled form lines. Setting ann.alignment = 0 after
construction forces left alignment (the /Q key = 0).

Verify after filling: pdftoppm -png -r 140 out.pdf page  (no pdf2image dep).
"""
import json
import sys

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText


def tf_pdf(bbox, pdf_height):
    """Convert [left, top, right, bottom] (y=0 top) to pypdf rect (y=0 bottom)."""
    left, top, right, bottom = bbox
    return left, pdf_height - bottom, right, pdf_height - top


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    fields_data = json.load(open(sys.argv[1]))
    input_pdf, output_pdf = sys.argv[2], sys.argv[3]

    reader = PdfReader(input_pdf)
    writer = PdfWriter()
    writer.append(reader)

    pidim = {i + 1: float(p.mediabox.height) for i, p in enumerate(reader.pages)}

    for field in fields_data["form_fields"]:
        pnum = field["page_number"]
        et = field.get("entry_text") or {}
        text = et.get("text")
        if not text:
            continue
        rect = tf_pdf(field["entry_bounding_box"], pidim[pnum])
        ann = FreeText(
            text=text,
            rect=rect,
            font=et.get("font", "Helvetica"),
            font_size=f"{et.get('font_size', 10)}pt",
            font_color=et.get("font_color", "000000"),
            border_color=None,
            background_color=None,
        )
        ann.alignment = 0  # force left alignment
        writer.add_annotation(page_number=pnum - 1, annotation=ann)

    with open(output_pdf, "wb") as f:
        writer.write(f)
    print(f"OK: {len(fields_data['form_fields'])} annotations, left-aligned")


if __name__ == "__main__":
    main()
