"""Render data/pdf-src/*.txt into the PDFs that live in the knowledge base.

The shop only publishes its warranty terms and care guide as PDFs, so the
ingestion has to handle PDFs too. Keeping the source text here means the PDFs
can be rebuilt instead of being opaque binaries in the repo.
"""

from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "data" / "pdf-src"
KB_DIR = ROOT / "data" / "kb"


def render(text: str) -> FPDF:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    for line in text.splitlines():
        if line.startswith("# "):
            pdf.set_title(line[2:])
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 10, line[2:], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        elif line.startswith("## "):
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 8, line[3:], new_x="LMARGIN", new_y="NEXT")
        elif line.startswith("- "):
            pdf.set_font("Helvetica", size=11)
            pdf.multi_cell(0, 6, "  -  " + line[2:], new_x="LMARGIN", new_y="NEXT")
        elif line.strip():
            pdf.set_font("Helvetica", size=11)
            pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.ln(3)

    return pdf


def main() -> None:
    for src in sorted(SRC_DIR.glob("*.txt")):
        out = KB_DIR / f"{src.stem}.pdf"
        render(src.read_text(encoding="utf-8")).output(str(out))
        print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
