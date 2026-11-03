"""Provider-independent OCR boundary for rota images and scanned PDFs.

No engine is wired. A concrete local engine may be added only after a separate
privacy, retention, data-region, hosting and cost review. This module must not
transmit rota bytes to an external service.
"""
from __future__ import annotations


class OcrUnavailable(RuntimeError):
    """The file needs OCR and no reviewed local engine is configured."""


class OcrProvider:
    """Local extraction interface. The default implementation reads nothing."""

    name = 'unconfigured'

    def extract_text(self, path, media_type: str) -> str:
        del path, media_type
        raise OcrUnavailable('Image reading is not switched on.')


def get_provider() -> OcrProvider:
    return OcrProvider()
