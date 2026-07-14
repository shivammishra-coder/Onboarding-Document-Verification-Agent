"""
Unified document loader - lazily rasterizes PDF pages OR a single image
into PNG bytes, ONE PAGE AT A TIME, so pages Stage 2 decides not to use
are never rendered at all.

Whether the source PDF has a real digital text layer or is a pure scan
makes NO difference here - the whole pipeline is vision-based now, so
every page is rasterized to an image regardless of its content. That's
what makes this same code correct for scanned PDFs, text PDFs, and plain
images alike - there's no branch that inspects text at all.
"""
import io
import os
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image

RASTER_DPI = 200
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


class DocumentLoader:
    """Opens a file once, exposes page count and per-page lazy rendering.
    Use as a context manager so the underlying PDF handle always closes:
        with DocumentLoader(path) as loader:
            page1 = loader.render_page(0)
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.ext = os.path.splitext(file_path)[1].lower()
        self._pdf_doc: Optional[fitz.Document] = None

        if self.ext == ".pdf":
            self._pdf_doc = fitz.open(file_path)
            self.page_count = len(self._pdf_doc)
        elif self.ext in IMAGE_EXTS:
            self.page_count = 1  # a plain image is a single "page"
        else:
            raise ValueError(f"Unsupported file type: {self.ext}")

    def render_page(self, page_index: int) -> bytes:
        """page_index is 0-indexed. Renders ONLY this one page - the PDF
        can have 50 pages, calling this once still only touches one."""
        if self._pdf_doc is not None:
            pix = self._pdf_doc.load_page(page_index).get_pixmap(dpi=RASTER_DPI)
            return pix.tobytes("png")

        if page_index != 0:
            raise IndexError("Image files only have a single page (index 0)")
        with Image.open(self.file_path) as img:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return buf.getvalue()

    def close(self):
        if self._pdf_doc is not None:
            self._pdf_doc.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()