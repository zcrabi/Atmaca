"""
extract.py — PDF metin çıkarma + taranmış sayfalar için otomatik OCR.

main.py'nin çağırdığı arayüz DEĞİŞMEDİ:
  extract_pdf(path)        -> list[{"page": n, "text": "..."}]
  page_count(path)         -> int
  is_scanned(pages, total) -> bool
  full_text(pages)         -> str
  stats(pages)             -> dict   (en azından "reading_min" içerir)

Yenilik: extract_pdf artık metin katmanı boş/yetersiz olan her sayfayı
otomatik olarak görsele çevirip Tesseract OCR (Türkçe+İngilizce) ile
okuyor. Böylece taranmış/fotoğraf PDF'ler de normal PDF gibi işleniyor.
is_scanned() artık sadece OCR sonrasında bile hiçbir metin çıkmayan
(örn. gerçekten boş/bozuk) belgeler için True döner.

Kurulum:
  pip install pymupdf pytesseract pillow
  Tesseract-OCR'ı kur: https://github.com/UB-Mannheim/tesseract/wiki
  (kurulumda "Turkish" dil paketini işaretle)

  tesseract.exe PATH'te değilse, ortam değişkeni ile yolu belirt:
  TESSERACT_CMD = "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
"""

import os
import fitz  # PyMuPDF
from PIL import Image
import pytesseract

TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "").strip()
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

OCR_LANG = "tur+eng"
OCR_DPI = 200
MIN_TEXT_CHARS = 20      # bundan az metin varsa sayfa "boş" sayılıp OCR denenir
MIN_TOTAL_CHARS = 40     # belge genelinde bundan az metin kalırsa is_scanned=True


def _ocr_page(page, dpi: int = OCR_DPI, lang: str = OCR_LANG) -> str:
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    try:
        return (pytesseract.image_to_string(img, lang=lang) or "").strip()
    except pytesseract.TesseractNotFoundError:
        # Tesseract kurulu değilse uygulama çökmesin — sayfa boş metin
        # olarak kalır, is_scanned bunu yakalar ve eski hata mesajı döner.
        return ""


def extract_pdf(path) -> list:
    """Her sayfa için {"page": n, "text": "..."} döndürür.
    Metin katmanı yetersizse otomatik OCR uygular."""
    doc = fitz.open(path)
    pages = []
    try:
        for i, page in enumerate(doc):
            text = (page.get_text() or "").strip()
            if len(text) < MIN_TEXT_CHARS:
                ocr_text = _ocr_page(page)
                if len(ocr_text) > len(text):
                    text = ocr_text
            pages.append({"page": i + 1, "text": text})
    finally:
        doc.close()
    return pages


def page_count(path) -> int:
    doc = fitz.open(path)
    n = doc.page_count
    doc.close()
    return n


def is_scanned(pages: list, total: int) -> bool:
    """OCR sonrasında bile metin çıkmadıysa True (gerçekten okunamayan belge)."""
    total_chars = sum(len(p["text"]) for p in pages)
    return total_chars < MIN_TOTAL_CHARS


def full_text(pages: list) -> str:
    return "\n\n".join(f"[SAYFA {p['page']}]\n{p['text']}" for p in pages if p["text"])


def stats(pages: list) -> dict:
    word_count = sum(len(p["text"].split()) for p in pages)
    reading_min = max(1, round(word_count / 200))  # ~200 kelime/dk okuma hızı
    return {
        "word_count": word_count,
        "reading_min": reading_min,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Kullanım: python extract.py dosya.pdf")
        sys.exit(1)
    p = sys.argv[1]
    pages = extract_pdf(p)
    total = page_count(p)
    print(f"Sayfa: {total}  |  Taranmış mı: {is_scanned(pages, total)}")
    print(full_text(pages)[:1000])
