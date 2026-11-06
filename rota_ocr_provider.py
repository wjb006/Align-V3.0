"""Private, on-device OCR for rota photos and scanned PDF pages.

The provider never uploads document bytes or extracted text. It uses the locally
installed/bundled Tesseract executable and local English language data.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from io import BytesIO
from pathlib import Path


MAX_PAGES = 20
MAX_IMAGE_EDGE = 8000
MAX_IMAGE_PIXELS = MAX_IMAGE_EDGE * MAX_IMAGE_EDGE
MAX_TEXT_CHARS = 1 * 1024 * 1024
OCR_TIMEOUT_SECONDS = 45


class OcrUnavailable(RuntimeError):
    """The local OCR runtime or one of its Python dependencies is unavailable."""


class OcrError(RuntimeError):
    """A local OCR operation failed safely."""


def _bundled_ocr_dir() -> Path | None:
    candidates = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / "ocr")
    candidates.append(Path(sys.executable).resolve().parent / "ocr")
    for candidate in candidates:
        if (candidate / "tesseract.exe").is_file():
            return candidate
    return None


class LocalTesseractProvider:
    """Tesseract adapter that performs all OCR on the current machine."""

    name = "local-tesseract"

    def __init__(self, command: str | None = None):
        try:
            import pytesseract
            from PIL import Image, ImageOps
        except ImportError as error:
            raise OcrUnavailable("The local OCR Python packages are not installed.") from error

        bundled = _bundled_ocr_dir()
        configured = command or os.environ.get("TESSERACT_CMD")
        install_dir = os.environ.get("TESSERACT_INSTALL_DIR", "").strip()
        if not configured and install_dir:
            configured = str(Path(install_dir) / "tesseract.exe")
        if not configured and bundled:
            configured = str(bundled / "tesseract.exe")
        if not configured:
            configured = shutil.which("tesseract")
        if not configured:
            raise OcrUnavailable("The local Tesseract OCR engine is not installed.")

        command_path = Path(configured)
        if command_path.is_file():
            resolved = str(command_path)
        else:
            resolved = shutil.which(str(configured)) or ""
        if not resolved:
            raise OcrUnavailable("The local Tesseract OCR engine could not be found.")

        self._pytesseract = pytesseract
        self._image = Image
        self._image_ops = ImageOps
        self._command = resolved
        self._tessdata = None
        if bundled and Path(resolved).resolve() == (bundled / "tesseract.exe").resolve():
            tessdata = bundled / "tessdata"
            if (tessdata / "eng.traineddata").is_file():
                self._tessdata = tessdata
        configured_data = os.environ.get("TESSDATA_PREFIX")
        if configured_data and (Path(configured_data) / "eng.traineddata").is_file():
            self._tessdata = Path(configured_data)
        self._pytesseract.pytesseract.tesseract_cmd = self._command
        self._config = "--oem 1 --psm 6"
        if self._tessdata:
            self._config += f' --tessdata-dir "{self._tessdata}"'

    def _ocr_image(self, image) -> str:
        try:
            image = self._image_ops.exif_transpose(image)
            if image.width < 1 or image.height < 1:
                raise OcrError("The image has invalid dimensions.")
            if image.width > MAX_IMAGE_EDGE or image.height > MAX_IMAGE_EDGE or image.width * image.height > MAX_IMAGE_PIXELS:
                raise OcrError("The image is larger than the local OCR limit.")
            prepared = self._image_ops.autocontrast(image.convert("L"))
            text = self._pytesseract.image_to_string(
                prepared,
                lang="eng",
                config=self._config,
                timeout=OCR_TIMEOUT_SECONDS,
            )
            return str(text or "")[:MAX_TEXT_CHARS]
        except OcrError:
            raise
        except Exception as error:
            raise OcrError("The local OCR engine could not read this image.") from error

    def extract_text(self, path, media_type: str) -> str:
        source = Path(path)
        try:
            if media_type in {"image/heic", "image/heif"}:
                try:
                    from pillow_heif import register_heif_opener
                except ImportError as error:
                    raise OcrUnavailable("HEIC support is not installed with the local OCR packages.") from error
                register_heif_opener()
            with self._image.open(source) as image:
                return self._ocr_image(image)
        except OcrUnavailable:
            raise
        except OcrError:
            raise
        except Exception as error:
            raise OcrError("This photo could not be decoded for local OCR.") from error

    def extract_pdf_text(self, path) -> str:
        try:
            import fitz
        except ImportError as error:
            raise OcrUnavailable("Local PDF page rendering is not installed.") from error
        pieces = []
        document = None
        try:
            document = fitz.open(str(path))
            if document.page_count < 1 or document.page_count > MAX_PAGES:
                raise OcrError("This PDF has too many pages for local OCR.")
            for page in document:
                native = str(page.get_text("text") or "").strip()
                has_image_content = bool(page.get_images(full=True))
                native_has_shift = (
                    bool(re.search(r"\d{1,2}[:.]\d{2}", native))
                    and bool(__import__("re").search(
                        r"\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}",
                        native,
                        re.IGNORECASE,
                    ))
                )
                if len("".join(ch for ch in native if ch.isalnum())) >= 20 and native_has_shift and not has_image_content:
                    pieces.append(native)
                else:
                    rect = page.rect
                    scale = min(2.0, MAX_IMAGE_EDGE / max(float(rect.width), float(rect.height), 1.0))
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    image_bytes = pixmap.tobytes("png")
                    with self._image.open(BytesIO(image_bytes)) as image:
                        pieces.append(self._ocr_image(image))
                if sum(len(piece) for piece in pieces) > MAX_TEXT_CHARS:
                    raise OcrError("This PDF contains too much text to process.")
        except OcrError:
            raise
        except Exception as error:
            raise OcrError("This PDF could not be rendered for local OCR.") from error
        finally:
            if document is not None:
                document.close()
        return "\n".join(piece for piece in pieces if piece.strip())[:MAX_TEXT_CHARS]


_PROVIDER = None


def get_provider() -> LocalTesseractProvider:
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = LocalTesseractProvider()
    return _PROVIDER


def is_available() -> bool:
    try:
        get_provider()
        return True
    except OcrUnavailable:
        return False
