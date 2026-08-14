# src/morningstar_modbus/maintenance/extract.py
"""Text extraction for vendor documents used by maintenance scans."""

from __future__ import annotations

from pathlib import Path


def extract_pdf_pages(path: Path) -> tuple[str, ...]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF extraction requires the maintenance extra: "
            "python -m pip install -e '.[maintenance]'"
        ) from exc

    reader = PdfReader(str(path))
    return tuple((page.extract_text() or "") for page in reader.pages)
