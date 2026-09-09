"""Build the NSRI-compliant .docx submission from the revised manuscript.

NSRI requires manuscripts in Word or LaTeX, in a standard font (Times New Roman
or Arial), double spaced, with continuous line numbering. The originally
submitted PDF met none of those: it was a Google Docs PDF export in Garamond at
1.16x spacing with no line numbers. This script renders the Markdown manuscript
to a .docx that satisfies all four.

It renders headings, bold/italic/code spans, superscript citations, bulleted
lists, Markdown pipe tables as real Word tables, and embeds each figure at its
`[INSERT FIGURE n HERE — path]` marker.

Run:
    python scripts/build_submission_docx.py
    python scripts/build_submission_docx.py --input paper/other.md --output out.docx
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

REPO = Path(__file__).resolve().parents[1]
BODY_FONT = "Times New Roman"
BODY_PT = 12
FIGURE_WIDTH_IN = 6.0

# **bold**, *italic*, `code`, <sup>..</sup> — matched in one pass so nesting of
# the delimiters cannot desynchronise the runs.
INLINE = re.compile(
    r"(\*\*.+?\*\*|(?<!\*)\*(?!\*).+?(?<!\*)\*(?!\*)|`[^`]+`|<sup>.*?</sup>)",
    re.S,
)
FIG_MARKER = re.compile(r"\[INSERT FIGURE (\d+) HERE\s*[—-]\s*`?([^`\]]+?)`?\]")


def configure_document(doc: Document, plain: bool = False) -> None:
    """Times New Roman 12pt. Manuscripts are double spaced and line numbered;
    `plain` (for the response letter) is single spaced with no line numbers."""
    style = doc.styles["Normal"]
    style.font.name = BODY_FONT
    style.font.size = Pt(BODY_PT)
    # Explicit east-asian mapping, or Word substitutes its own default font.
    style.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    pf = style.paragraph_format
    pf.line_spacing = 1.0 if plain else 2.0
    pf.space_before = Pt(0)
    pf.space_after = Pt(6) if plain else Pt(0)

    # Word's built-in heading styles are blue and sans-serif; journals expect
    # black body-font headings.
    for name in ("Title", "Heading 1", "Heading 2", "Heading 3", "Heading 4"):
        if name not in doc.styles:
            continue
        heading = doc.styles[name]
        heading.font.name = BODY_FONT
        heading.font.color.rgb = RGBColor(0, 0, 0)
        heading.font.bold = True
        heading.paragraph_format.line_spacing = 1.0 if plain else 2.0
        heading.paragraph_format.space_before = Pt(6)
        heading.paragraph_format.space_after = Pt(0)

    for section in doc.sections:
        section.left_margin = section.right_margin = Inches(1)
        section.top_margin = section.bottom_margin = Inches(1)
        if not plain:
            add_line_numbers(section)


def add_line_numbers(section) -> None:
    """Continuous line numbering, restarting only at the document start.

    python-docx exposes no API for this, so the w:lnNumType element is written
    into the section properties directly.
    """
    sect_pr = section._sectPr
    for existing in sect_pr.findall(qn("w:lnNumType")):
        sect_pr.remove(existing)
    ln = sect_pr.makeelement(qn("w:lnNumType"), {})
    ln.set(qn("w:countBy"), "1")
    ln.set(qn("w:restart"), "continuous")
    ln.set(qn("w:distance"), "360")  # 0.25" from text
    sect_pr.append(ln)


def add_runs(paragraph, text: str) -> None:
    """Add `text` to `paragraph`, honouring inline Markdown and <sup>."""
    for piece in INLINE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**"):
            run = paragraph.add_run(piece[2:-2])
            run.bold = True
        elif piece.startswith("<sup>"):
            run = paragraph.add_run(re.sub(r"</?sup>", "", piece))
            run.font.superscript = True
        elif piece.startswith("`") and piece.endswith("`"):
            run = paragraph.add_run(piece[1:-1])
            run.font.name = "Courier New"
            run.font.size = Pt(BODY_PT - 1)
        elif piece.startswith("*") and piece.endswith("*"):
            run = paragraph.add_run(piece[1:-1])
            run.italic = True
        else:
            paragraph.add_run(piece)


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def add_table(doc: Document, rows: list[str]) -> None:
    header = split_row(rows[0])
    body = [split_row(r) for r in rows[2:]]  # rows[1] is the --- separator
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.autofit = True
    for cell, text in zip(table.rows[0].cells, header):
        cell.paragraphs[0].clear()
        add_runs(cell.paragraphs[0], text)
        for run in cell.paragraphs[0].runs:
            run.bold = True
    # Repeat the header row when a table breaks across pages.
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tr_pr.append(tr_pr.makeelement(qn("w:tblHeader"), {}))
    for record in body:
        cells = table.add_row().cells
        # Tolerate a ragged row rather than dropping it.
        for cell, text in zip(cells, record + [""] * (len(header) - len(record))):
            cell.paragraphs[0].clear()
            add_runs(cell.paragraphs[0], text)
    # Tables are single-spaced and one size down so wide ones stay readable.
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                para.paragraph_format.line_spacing = 1.0
                para.paragraph_format.space_after = Pt(0)
                for run in para.runs:
                    run.font.size = Pt(9)
    doc.add_paragraph()


def add_figure(doc: Document, path: Path, number: str) -> None:
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.line_spacing = 1.0
    if path.exists():
        para.add_run().add_picture(str(path), width=Inches(FIGURE_WIDTH_IN))
    else:
        run = para.add_run(f"[Figure {number} not found: {path}]")
        run.italic = True
        print(f"  WARNING: missing figure {path}")


def convert(md: str, doc: Document, repo: Path) -> dict[str, int]:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    lines = md.split("\n")
    stats = {"headings": 0, "tables": 0, "figures": 0, "paragraphs": 0}
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        if not line.strip() or line.strip() == "---":
            i += 1
            continue

        # Figure marker: emit the image, then the caption line(s) that follow.
        marker = FIG_MARKER.search(line)
        if marker:
            number, rel = marker.group(1), marker.group(2).strip()
            add_figure(doc, repo / rel, number)
            stats["figures"] += 1
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                caption = lines[i].lstrip()[1:].strip()
                if caption:
                    para = doc.add_paragraph()
                    para.paragraph_format.line_spacing = 1.0
                    add_runs(para, caption)
                    for run in para.runs:
                        run.font.size = Pt(10)
                i += 1
            doc.add_paragraph()
            continue

        # A blockquote that is not a figure marker (defensive; none at present).
        if line.lstrip().startswith(">"):
            para = doc.add_paragraph()
            add_runs(para, line.lstrip()[1:].strip())
            i += 1
            continue

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            doc.add_heading(line.lstrip("# ").strip(), level=min(level, 4))
            stats["headings"] += 1
            i += 1
            continue

        if line.lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            if len(block) >= 2:
                add_table(doc, block)
                stats["tables"] += 1
            continue

        if re.match(r"^\s*[-*]\s+", line):
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i].rstrip()):
                text = re.sub(r"^\s*[-*]\s+", "", lines[i].rstrip())
                para = doc.add_paragraph(style="List Bullet")
                add_runs(para, text)
                i += 1
            continue

        # Ordinary paragraph: join until a blank line or a new block starts.
        chunk = []
        while i < len(lines):
            nxt = lines[i].rstrip()
            if (not nxt.strip() or nxt.startswith("#") or nxt.lstrip().startswith(("|", ">"))
                    or nxt.strip() == "---" or re.match(r"^\s*[-*]\s+", nxt)):
                break
            chunk.append(nxt)
            i += 1
        if chunk:
            para = doc.add_paragraph()
            add_runs(para, " ".join(chunk))
            stats["paragraphs"] += 1
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path,
                    default=REPO / "paper" / "REVISED_paper_NSRI-J-2026-0178.md")
    ap.add_argument("--output", type=Path,
                    default=REPO / "paper" / "NSRI-J-2026-0178_revision1.docx")
    ap.add_argument("--repo", type=Path, default=REPO)
    ap.add_argument("--plain", action="store_true",
                    help="single spaced, no line numbering (for the response letter)")
    args = ap.parse_args()

    doc = Document()
    configure_document(doc, plain=args.plain)
    stats = convert(args.input.read_text(encoding="utf-8"), doc, args.repo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(args.output)

    print(f"[written] {args.output}")
    print(f"  headings={stats['headings']} tables={stats['tables']} "
          f"figures={stats['figures']} paragraphs={stats['paragraphs']}")
    if args.plain:
        print(f"  font={BODY_FONT} {BODY_PT}pt | single spaced | no line numbers | 1in margins")
    else:
        print(f"  font={BODY_FONT} {BODY_PT}pt | line spacing=2.0 (double) "
              f"| continuous line numbering | 1in margins")


if __name__ == "__main__":
    main()
