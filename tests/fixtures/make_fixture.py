"""One-off generator for tests/fixtures/sample.pdf (requires reportlab).

Run: poetry run python tests/fixtures/make_fixture.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).parent / "sample.pdf"


def main() -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(OUT), pagesize=LETTER)
    flow = [
        Paragraph("Solar System Facts", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "This short document lists a few factual statements about the "
            "solar system for testing the PDF ingestion pipeline.",
            styles["BodyText"],
        ),
        Spacer(1, 18),
        Paragraph("The Inner Planets", styles["Heading1"]),
        Paragraph(
            "Mercury is the closest planet to the Sun. Venus is the hottest "
            "planet in the solar system, with surface temperatures around 465 "
            "degrees Celsius. Earth is the only planet known to support life. "
            "Mars has two small moons named Phobos and Deimos.",
            styles["BodyText"],
        ),
        PageBreak(),
        Paragraph("The Outer Planets", styles["Heading1"]),
        Paragraph(
            "Jupiter is the largest planet in the solar system. Saturn is "
            "famous for its extensive ring system. Uranus rotates on its side "
            "relative to its orbit. Neptune was the first planet located "
            "through mathematical prediction rather than observation.",
            styles["BodyText"],
        ),
    ]
    doc.build(flow)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
