"""Generate the synthetic documents the evidence tests and the demo need.

**Generated, not committed.** A checked-in PDF is a binary nobody reviews, and directive 9
is about what reaches anything public. With a generator, every value in every document is
visible in reviewable source — you can read this file and know exactly what is in them.

Everything here is fictional. "Amara Okonkwo" is the existing synthetic demo applicant
(SYNTHETIC_DEMO_CASE); reference numbers use an obviously fake prefix; no real test
centre, Home Office reference format, or person appears.

    uv run python -m scripts.make_fixtures [output-dir]

The awkward ones are the point. A clean PDF proves very little — these are the files that
found the bugs:

- `scan-no-text-layer.pdf` — a photograph of a page. Valid, readable, and says nothing to
  a text parser. Must be PARTIALLY_COMPLETED, not FAILED.
- `password-protected.pdf` — terminal, and must be detected before any page is touched.
- `empty.pdf` — zero bytes. Not a document.
- `not-really-a-pdf.pdf` — an executable wearing a PDF's name and declared type.
- `huge-embedded-image.pdf` — the resource bound. Proves the worker recycles rather than
  the container dying.
- `many-pages.pdf` — past the page cap, so the read is truncated rather than abandoned.
"""

import sys
import zlib
from pathlib import Path

import pymupdf

APPLICANT = "Amara Okonkwo"
FAKE_PREFIX = "SYNTH"


def _page(doc: pymupdf.Document, title: str, lines: list[str]) -> None:
    page = doc.new_page()
    page.insert_text((72, 80), "SYNTHETIC FIXTURE — NOT A REAL DOCUMENT", fontsize=9)
    page.insert_text((72, 120), title, fontsize=16)
    for index, line in enumerate(lines):
        page.insert_text((72, 156 + index * 20), line, fontsize=11)


def immigration_status(path: Path) -> None:
    doc = pymupdf.open()
    _page(
        doc,
        "Confirmation of settled status",
        [
            f"Name: {APPLICANT}",
            "Status: Indefinite leave to remain",
            "Granted on: 1 January 2019",
            f"Reference: {FAKE_PREFIX}-ILR-000001",
        ],
    )
    doc.save(path)
    doc.close()


def english_test(path: Path) -> None:
    doc = pymupdf.open()
    _page(
        doc,
        "English language test result",
        [
            f"Candidate: {APPLICANT}",
            "Level: B1 CEFR",
            "Result: Pass",
            "Date of test: 12 March 2024",
            f"Certificate number: {FAKE_PREFIX}-ENG-000002",
        ],
    )
    doc.save(path)
    doc.close()


def life_in_the_uk(path: Path) -> None:
    doc = pymupdf.open()
    _page(
        doc,
        "Life in the UK test — pass notification",
        [
            f"Candidate: {APPLICANT}",
            "Result: Pass",
            "Date of test: 4 April 2024",
            f"Unique reference: {FAKE_PREFIX}-LUK-000003",
        ],
    )
    doc.save(path)
    doc.close()


def travel_booking(path: Path) -> None:
    doc = pymupdf.open()
    _page(
        doc,
        "Flight booking confirmation",
        [
            f"Passenger: {APPLICANT}",
            f"Booking reference: {FAKE_PREFIX}-TRV-000004",
            "London (LHR) to Athens (ATH)    5 June 2024",
            "Athens (ATH) to London (LHR)   15 July 2024",
        ],
    )
    doc.save(path)
    doc.close()


def scan_no_text_layer(path: Path) -> None:
    """A page that is only an image — what a phone photo of a letter produces.

    Valid, readable, and completely silent to a text parser. The pipeline must call this
    `PARTIALLY_COMPLETED`: the work was done and there was nothing to find. Reading it
    needs OCR or a multimodal model, both M8.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 600, 800))
    pixmap.set_rect(pixmap.irect, (235, 235, 230))
    page.insert_image(pymupdf.Rect(0, 0, 600, 800), pixmap=pixmap)
    doc.save(path)
    doc.close()


def password_protected(path: Path) -> None:
    doc = pymupdf.open()
    _page(doc, "Confidential", [f"Name: {APPLICANT}", "This document is encrypted."])
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="synthetic-password")
    doc.close()


def many_pages(path: Path, pages: int = 60) -> None:
    """More pages than the cap, so the read is truncated rather than abandoned."""
    doc = pymupdf.open()
    for number in range(pages):
        _page(doc, f"Page {number + 1} of {pages}", [f"Line for page {number + 1}."])
    doc.save(path)
    doc.close()


def huge_embedded_image(path: Path) -> None:
    """A small file that becomes very large in memory once decoded.

    A page cap cannot help here — this expands on `open()` or on one page, before there
    is anything to count. It exists to prove the *worker recycles* rather than the
    container dying, which is the only control that actually applies (threat model §7).
    """
    width = height = 4000
    raw = b"\x00" * (width * height * 3)
    compressed = zlib.compress(raw, level=9)

    doc = pymupdf.open()
    page = doc.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height))
    pixmap.set_rect(pixmap.irect, (255, 255, 255))
    page.insert_image(pymupdf.Rect(0, 0, 600, 800), pixmap=pixmap)
    doc.save(path, deflate=True, deflate_images=True)
    doc.close()
    print(
        f"    (raw {len(raw) / 1_000_000:.0f}MB decoded, {len(compressed) / 1000:.0f}KB compressed)"
    )


def empty(path: Path) -> None:
    path.write_bytes(b"")


def not_really_a_pdf(path: Path) -> None:
    """An executable wearing a PDF's name. The magic-byte check is what catches it."""
    path.write_bytes(b"MZ\x90\x00" + b"\x00" * 200)


GENERATORS = {
    "immigration-status.pdf": immigration_status,
    "english-test.pdf": english_test,
    "life-in-the-uk.pdf": life_in_the_uk,
    "travel-booking.pdf": travel_booking,
    "scan-no-text-layer.pdf": scan_no_text_layer,
    "password-protected.pdf": password_protected,
    "many-pages.pdf": many_pages,
    "huge-embedded-image.pdf": huge_embedded_image,
    "empty.pdf": empty,
    "not-really-a-pdf.pdf": not_really_a_pdf,
}

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "documents"


def generate(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, make in GENERATORS.items():
        path = directory / name
        make(path)
        print(f"  {name:26} {path.stat().st_size:>9,} bytes")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    print(f"Generating synthetic fixtures into {target}")
    generate(target)
