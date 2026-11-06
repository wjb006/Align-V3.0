"""Privacy-first local OCR for rota photographs and scanned PDF pages.

OCR runs on the same computer/server as Align through the Tesseract executable.
No rota content is sent to a hosted OCR or AI service.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path


class OcrUnavailable(RuntimeError):
    """The local OCR runtime or a required decoder is not installed."""


class LocalTesseractProvider:
    name = "local-tesseract"

    def __init__(self):
        self.command = self._find_tesseract()

    @staticmethod
    def _find_tesseract():
        configured = os.environ.get("ALIGN_TESSERACT_CMD", "").strip()
        candidate = configured or shutil.which("tesseract")
        if not candidate and os.name == "nt":
            windows_default = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR" / "tesseract.exe"
            if windows_default.is_file():
                candidate = str(windows_default)
        if not candidate:
            return None
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path)
        if configured:
            return None
        return candidate

    def available(self) -> bool:
        if not self.command:
            return False
        try:
            import pytesseract
            from PIL import Image
            pytesseract.pytesseract.tesseract_cmd = self.command
            pytesseract.get_tesseract_version()
            return Image is not None and "eng" in pytesseract.get_languages(config="")
        except Exception:
            return False

    def capabilities(self) -> dict:
        image = self.available()
        pdf = image
        if pdf:
            try:
                import fitz  # PyMuPDF, used only to render scanned PDF pages
            except Exception:
                pdf = False
        heic = image
        if heic:
            try:
                import pillow_heif  # noqa: F401
            except Exception:
                heic = False
        return {
            "image_ocr": image,
            "scanned_pdf_ocr": pdf,
            "heic_ocr": heic,
            "provider": self.name if image else "unavailable",
        }

    def extract_text(self, path, media_type: str) -> str:
        if media_type == "application/pdf":
            return self._pdf_text(Path(path))
        if not self.available():
            raise OcrUnavailable(
                "Local photo reading needs Tesseract OCR. Install the Align OCR runtime "
                "or set ALIGN_TESSERACT_CMD to its executable."
            )
        return self._image_text(Path(path), media_type)

    def _image_text(self, path: Path, media_type: str, timeout: int = 30) -> str:
        from PIL import Image
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = self.command
        if media_type in {"image/heic", "image/heif"}:
            try:
                import pillow_heif
                pillow_heif.register_heif_opener()
            except Exception as error:
                raise OcrUnavailable("HEIC photo support is not installed in this Align build.") from error
        try:
            with Image.open(path) as source:
                source.load()
                if source.width < 1 or source.height < 1 or source.width * source.height > 64_000_000:
                    raise OcrUnavailable("This photo is too large to process safely.")
                image = source.convert("RGB")
                image.thumbnail((3200, 3200))
                text = pytesseract.image_to_string(
                    image, lang="eng", config="--oem 1 --psm 6", timeout=timeout
                )
        except OcrUnavailable:
            raise
        except Exception as error:
            raise OcrUnavailable("Align could not read this photo. Try a clearer JPG or PNG.") from error
        if not str(text or "").strip():
            raise OcrUnavailable("No readable rota text was found in this photo.")
        return str(text)[:1_000_000]

    def _pdf_text(self, path: Path) -> str:
        try:
            import fitz
            from PIL import Image
            import pytesseract
        except Exception as error:
            raise OcrUnavailable("PDF reading needs the local PDF runtime.") from error
        pieces = []
        deadline = time.monotonic() + 120
        try:
            with fitz.open(path) as document:
                if document.is_encrypted or document.page_count > 20:
                    raise OcrUnavailable("This PDF is encrypted or has too many pages.")
                for page in document:
                    text = page.get_text("text").strip()
                    if text:
                        pieces.append(text)
                        continue
                    if not self.available():
                        raise OcrUnavailable(
                            "This scanned PDF needs local Tesseract OCR. Install the Align OCR runtime."
                        )
                    pytesseract.pytesseract.tesseract_cmd = self.command
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise OcrUnavailable("This PDF took too long to read. Try fewer pages.")
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                    image.thumbnail((3200, 3200))
                    page_text = pytesseract.image_to_string(
                        image, lang="eng", config="--oem 1 --psm 6",
                        timeout=max(1, min(30, int(remaining)))
                    )
                    if page_text.strip():
                        pieces.append(page_text)
        except OcrUnavailable:
            raise
        except Exception as error:
            raise OcrUnavailable("Align could not read this scanned PDF.") from error
        result = "\n".join(pieces).strip()
        if not result:
            raise OcrUnavailable("No readable rota text was found in this PDF.")
        return result[:1_000_000]


def get_provider() -> LocalTesseractProvider:
    return LocalTesseractProvider()


def capabilities() -> dict:
    return get_provider().capabilities()
