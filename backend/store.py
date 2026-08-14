"""
store.py — SQLite tabanlı kalıcı depolama.

main.py'deki DOCS sözlüğü artık sadece bir "önbellek" — gerçek veri
burada, SQLite dosyasında (atmaca.db) kalıcı olarak duruyor. Backend
yeniden başlasa, bilgisayar kapansa bile yüklenen belgeler kaybolmaz.

Not: embedding vektörleri (doc["vectors"]) kalıcı olarak SAKLANMIYOR —
bunlar zaten "tembel yükleme" ile ilk soru sorulduğunda hesaplanıyordu,
belge yeniden açıldığında da aynı şekilde otomatik yeniden hesaplanır.
Bu, veritabanı dosyasını küçük ve hızlı tutar.

Ayrıca daha önce üretilmiş sınav soruları / kartlar / özet SAKLANMIYOR —
sadece ham kaynak metin (page_list/text/chunks) kalıcı. Bir belgeyi
tekrar açtığında OCR/transkript tekrar çalışmaz (en yavaş kısım), ama
AI analizi (özet/soru/kart) o an için yeniden üretilir.
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path("atmaca.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id       TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            kind         TEXT NOT NULL DEFAULT 'pdf',
            course_id    TEXT NOT NULL DEFAULT '',
            course_name  TEXT NOT NULL DEFAULT '',
            pages        INTEGER NOT NULL DEFAULT 0,
            long_flag    INTEGER NOT NULL DEFAULT 0,
            reading_min  INTEGER NOT NULL DEFAULT 1,
            word_count   INTEGER NOT NULL DEFAULT 0,
            duration     REAL,
            page_list    TEXT NOT NULL,
            text         TEXT NOT NULL,
            chunks       TEXT NOT NULL,
            marks        TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def save_document(doc_id: str, doc: dict, course_id: str = "", course_name: str = ""):
    """DOCS[doc_id] sözlüğünü kalıcı depoya yazar (varsa günceller)."""
    conn = _connect()
    conn.execute("""
        INSERT INTO documents
            (doc_id, name, kind, course_id, course_name, pages, long_flag,
             reading_min, word_count, duration, page_list, text, chunks, marks)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(doc_id) DO UPDATE SET
            name=excluded.name, kind=excluded.kind,
            course_id=excluded.course_id, course_name=excluded.course_name,
            pages=excluded.pages, long_flag=excluded.long_flag,
            reading_min=excluded.reading_min, word_count=excluded.word_count,
            duration=excluded.duration, page_list=excluded.page_list,
            text=excluded.text, chunks=excluded.chunks, marks=excluded.marks
    """, (
        doc_id,
        doc.get("name", ""),
        doc.get("kind") or "pdf",
        course_id, course_name,
        doc.get("pages", 0),
        int(bool(doc.get("long"))),
        doc.get("reading_min", 1),
        doc.get("word_count", doc.get("words", 0)),
        doc.get("duration"),
        json.dumps(doc.get("page_list", []), ensure_ascii=False),
        doc.get("text", ""),
        json.dumps(doc.get("chunks", []), ensure_ascii=False),
        json.dumps(doc.get("marks")) if doc.get("marks") is not None else None,
    ))
    conn.commit()
    conn.close()


def load_all() -> dict:
    """Tüm belgeleri DOCS formatında (bellek içi sözlük gibi) döndürür.
    Backend başlarken bunlarla DOCS önbelleği doldurulur."""
    conn = _connect()
    rows = conn.execute("SELECT * FROM documents").fetchall()
    conn.close()

    out = {}
    for r in rows:
        kind = r["kind"]
        out[r["doc_id"]] = {
            "name": r["name"],
            "kind": kind if kind and kind != "pdf" else None,
            "pages": r["pages"],
            "page_list": json.loads(r["page_list"]),
            "text": r["text"],
            "chunks": json.loads(r["chunks"]),
            "vectors": None,
            "long": bool(r["long_flag"]),
            "word_count": r["word_count"],
            "reading_min": r["reading_min"],
            "duration": r["duration"],
            "marks": json.loads(r["marks"]) if r["marks"] else None,
        }
    return out


def list_documents() -> list:
    """Kütüphane ekranı için hafif bir liste — frontend açılışta bunu çeker."""
    conn = _connect()
    rows = conn.execute("""
        SELECT doc_id, name, kind, course_id, course_name, pages,
               duration, created_at
        FROM documents ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
