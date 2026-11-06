"""Unit tests for local, offline rota OCR."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw, ImageFont

import rota_ocr_provider


class LocalOcrProviderTests(unittest.TestCase):
    def provider(self):
        # The OCR executable is not invoked in these tests; only the Python
        # adapter is exercised with a mocked OCR call.
        return rota_ocr_provider.LocalTesseractProvider(command=sys.executable)

    def test_photo_is_processed_locally_and_text_is_returned(self):
        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "rota.png"
            Image.new("RGB", (500, 300), "white").save(image_path)
            provider = self.provider()
            with mock.patch.object(provider._pytesseract, "image_to_string", return_value="2026-11-09 08:00-16:00 Ward"):
                result = provider.extract_text(image_path, "image/png")
        self.assertIn("2026-11-09", result)

    def test_scanned_pdf_pages_are_rendered_and_ocrd(self):
        import fitz
        with tempfile.TemporaryDirectory() as folder:
            pdf_path = Path(folder) / "scanned.pdf"
            document = fitz.open()
            document.new_page(width=595, height=842)
            document.save(pdf_path)
            document.close()
            provider = self.provider()
            with mock.patch.object(provider._pytesseract, "image_to_string", return_value="2026-11-09 08:00-16:00 Ward") as ocr:
                result = provider.extract_pdf_text(pdf_path)
        self.assertIn("2026-11-09", result)
        ocr.assert_called_once()

    def test_native_pdf_text_is_kept_without_running_ocr(self):
        import fitz
        with tempfile.TemporaryDirectory() as folder:
            pdf_path = Path(folder) / "native.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "2026-11-09 08:00-16:00 Ward")
            document.save(pdf_path)
            document.close()
            provider = self.provider()
            with mock.patch.object(provider._pytesseract, "image_to_string") as ocr:
                result = provider.extract_pdf_text(pdf_path)
        self.assertIn("2026-11-09", result)
        ocr.assert_not_called()

    @unittest.skipUnless(rota_ocr_provider.is_available(), "Local Tesseract is not installed")
    def test_installed_tesseract_reads_a_clear_rota_photo(self):
        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "rota-photo.png"
            image = Image.new("RGB", (2200, 420), "white")
            draw = ImageDraw.Draw(image)
            font_path = Path("C:/Windows/Fonts/arial.ttf")
            if not font_path.is_file():
                self.skipTest("Windows Arial font is not available")
            font = ImageFont.truetype(str(font_path), 110)
            draw.text((60, 120), "2026-11-09 08:00-16:00 Ward", fill="black", font=font)
            image.save(image_path)
            text = rota_ocr_provider.get_provider().extract_text(image_path, "image/png")
        self.assertIn("2026", text)
        self.assertIn("08:00", text)

    def test_missing_tesseract_is_reported_as_unavailable(self):
        with self.assertRaises(rota_ocr_provider.OcrUnavailable):
            rota_ocr_provider.LocalTesseractProvider(command="/missing/tesseract")

    def test_oversized_photo_is_rejected_before_ocr(self):
        provider = self.provider()
        image = Image.new("RGB", (rota_ocr_provider.MAX_IMAGE_EDGE + 1, 1), "white")
        with mock.patch.object(provider._pytesseract, "image_to_string") as ocr:
            with self.assertRaises(rota_ocr_provider.OcrError):
                provider._ocr_image(image)
        ocr.assert_not_called()


if __name__ == "__main__":
    unittest.main()
