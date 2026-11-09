FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng fonts-dejavu-core tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py *.sql merseyside_stops.json ./
COPY desktop/*.py ./desktop/
COPY static ./static
COPY migrations ./migrations
RUN useradd --create-home --uid 10001 align && chown -R align:align /app
USER align

# Fail the image build if the real OCR engine cannot import a photo and scanned PDF.
RUN python -c "from pathlib import Path; import rota_ocr_provider; assert rota_ocr_provider.is_available(), 'Tesseract is unavailable'; assert Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').is_file(), 'Test font is unavailable'" \
    && python -m unittest -v test_work_rota_import.RotaImportTests.test_real_ocr_imports_synthetic_photo_and_scanned_pdf_for_review

CMD ["python", "render_start.py"]
