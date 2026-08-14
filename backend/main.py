"""
main.py — FastAPI uygulaması.

Çalıştır:  uvicorn main:app --reload
Belgeler:  http://127.0.0.1:8000/docs
"""

import shutil
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import analyze as ai
import extract
import longdoc
import store
import verify
import transcribe as tr

load_dotenv()

UPLOADS = Path("uploads")
UPLOADS.mkdir(exist_ok=True)

app = FastAPI(title="Atmaca")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# DOCS artık bir "önbellek" — kalıcı veri store.py (SQLite) üzerinden
# atmaca.db dosyasında tutuluyor. Backend başlarken orada ne varsa
# buraya yükleniyor, böylece yeniden başlatma/bilgisayar kapatma
# belgeleri silmiyor.
store.init_db()
DOCS: dict[str, dict] = {}
DOCS.update(store.load_all())


class AnalyzeIn(BaseModel):
    start: int | None = None   # bölüm seçildiyse sayfa aralığı
    end: int | None = None


class GenerateIn(BaseModel):
    doc_id: str
    type: str          # "quiz" | "cards"
    count: int = 10
    exclude: list[str] = []


class AskIn(BaseModel):
    doc_id: str
    question: str


@app.get("/health")
def health():
    return {"ok": True, "docs": len(DOCS)}


@app.get("/documents")
def list_documents():
    """Kayıtlı tüm belgelerin hafif listesi — frontend açılışta bunu
    çekip ders/kütüphane ekranını yeniden kurar."""
    return {"items": store.list_documents()}


@app.post("/upload")
async def upload(file: UploadFile, course_id: str = Form(""), course_name: str = Form("")):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Şimdilik sadece PDF destekleniyor.")

    doc_id = uuid.uuid4().hex[:8]
    path = UPLOADS / f"{doc_id}.pdf"
    with path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    pages = extract.extract_pdf(path)
    total = extract.page_count(path)

    if extract.is_scanned(pages, total):
        raise HTTPException(
            422, "Bu PDF taranmış görünüyor, metin çıkarılamadı. "
                 "Fotoğraf/OCR desteği henüz eklenmedi."
        )

    chunks = longdoc.chunk(pages)
    long = total >= longdoc.LONG_DOC_PAGES

    DOCS[doc_id] = {
        "name": file.filename,
        "pages": total,
        "page_list": pages,
        "text": extract.full_text(pages),
        "chunks": chunks,
        "vectors": None,          # ilk soruda hesaplanır (tembel yükleme)
        "long": long,
        **extract.stats(pages),
    }
    store.save_document(doc_id, DOCS[doc_id], course_id, course_name)

    return {
        "doc_id": doc_id,
        "name": file.filename,
        "pages": total,
        "long": long,
        # uzun belgede öğrenci önce bölüm seçsin
        "outline": longdoc.outline(path) if long else [],
        "estimate": longdoc.estimate(chunks) if long else None,
    }


AUDIO_EXT = (".mp3", ".m4a", ".wav", ".ogg", ".webm", ".mp4")


@app.post("/upload-audio")
async def upload_audio(file: UploadFile, course_id: str = Form(""), course_name: str = Form("")):
    """Ders kaydı yükle. Transkript bloklara bölünür, blok = sahte sayfa."""
    if not file.filename.lower().endswith(AUDIO_EXT):
        raise HTTPException(400, "Desteklenen ses biçimleri: mp3, m4a, wav, ogg, webm, mp4")

    doc_id = uuid.uuid4().hex[:8]
    path = UPLOADS / f"{doc_id}{Path(file.filename).suffix}"
    with path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    result = tr.transcribe(str(path))
    pages = result["pages"]

    if not pages:
        raise HTTPException(422, "Kayıttan konuşma çıkarılamadı. Ses çok kısık veya boş olabilir.")

    chunks = longdoc.chunk(pages)

    DOCS[doc_id] = {
        "name": file.filename,
        "kind": "audio",
        "pages": len(pages),
        "page_list": pages,
        "text": extract.full_text(pages),
        "chunks": chunks,
        "vectors": None,
        "long": len(chunks) > 1,
        "marks": result["marks"],
        "duration": result["duration"],
        "words": len(result["full"].split()),
        "reading_min": max(1, round(result["duration"] / 60)),
    }
    store.save_document(doc_id, DOCS[doc_id], course_id, course_name)

    return {
        "doc_id": doc_id,
        "name": file.filename,
        "kind": "audio",
        "blocks": len(pages),
        "duration": tr.mmss(result["duration"]),
    }


@app.post("/analyze/{doc_id}")
def do_analyze(doc_id: str, body: AnalyzeIn | None = None):
    doc = DOCS.get(doc_id)
    if not doc:
        raise HTTPException(404, "Belge bulunamadı.")

    pages = doc["page_list"]

    # bölüm seçildiyse sadece o aralığı çalış
    if body and body.start and body.end:
        pages = longdoc.slice_pages(pages, body.start, body.end)
        if not pages:
            raise HTTPException(400, "Bu sayfa aralığında metin yok.")

    chunks = longdoc.chunk(pages)

    if len(chunks) == 1:
        result = ai.analyze(chunks[0]["text"])
    else:
        result = longdoc.map_reduce_analyze(chunks, ai.analyze, ai.reduce_summaries)

    # model uydurmuş olabilir — sayfa numaralarını metinle doğrula
    result = verify.verify_analysis(result, pages)

    # ses kaydıysa sayfa numaralarının yanına zaman damgası koy
    if doc.get("kind") == "audio":
        result = tr.label_pages(result, doc["marks"])

    # Frontend'deki DOC nesnesinin birebir karşılığı
    return {
        "name": doc["name"],
        "pages": doc["pages"],
        "readingMin": doc["reading_min"],
        "summaryMin": 2,
        **result,
    }


@app.post("/generate")
def do_generate(body: GenerateIn):
    doc = DOCS.get(body.doc_id)
    if not doc:
        raise HTTPException(404, "Belge bulunamadı.")
    if body.count < 1 or body.count > 100:
        raise HTTPException(400, "count 1-100 arasında olmalı.")

    if doc["long"]:
        # tüm kitaptan değil, dengeli biçimde seçilmiş parçalardan üret
        step = max(1, len(doc["chunks"]) // 6)
        picked = doc["chunks"][::step][:6]
        source = "\n\n".join(c["text"] for c in picked)
    else:
        source = doc["text"]

    items = ai.generate(body.type, source, body.count, body.exclude)

    if body.type == "quiz":
        items, _ = verify.filter_single(items, verify.page_index(doc["page_list"]), "q")

    # İstenen sayı ile üretilen sayı farklıysa frontend bunu kullanıcıya söylüyor
    return {"items": items, "requested": body.count, "produced": len(items)}


@app.post("/ask")
def do_ask(body: AskIn):
    doc = DOCS.get(body.doc_id)
    if not doc:
        raise HTTPException(404, "Belge bulunamadı.")

    if doc["long"]:
        if doc["vectors"] is None:
            doc["vectors"] = longdoc.embed_chunks(doc["chunks"])
        picked = longdoc.top_chunks(body.question, doc["chunks"], doc["vectors"])
        context = "\n\n".join(c["text"] for c in picked)
    else:
        context = doc["text"]

    result = ai.ask(context, body.question)
    return {
        "text": result["text"],
        "sources": [{"page": p} for p in result["pages"]],
    }
