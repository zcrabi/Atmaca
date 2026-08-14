"""
longdoc.py — Uzun belgeler (100+ sayfa) için.

Kısa ders notunda tüm metni tek seferde modele veriyoruz. 1000 sayfalık
bir kitapta bu üç sebeple çalışmaz:

  1. Bağlam penceresi dolar veya çok pahalıya gelir.
  2. Model 1000 sayfayı "ortalar", özet genelleşir ve işe yaramaz hale gelir.
  3. Öğrenci zaten tüm kitabı değil, bir bölümü çalışıyordur.

Çözüm üç katmanlı:
  - İçindekiler çıkar   → öğrenci bölüm seçsin
  - Parçala + haritala  → her parçayı ayrı özetle, sonra birleştir
  - Getirim (retrieval)  → soru sorulduğunda sadece ilgili parçaları modele ver
"""

from __future__ import annotations

import numpy as np
import fitz

# ~4 karakter ≈ 1 token. Parça başına güvenli bütçe.
CHUNK_CHARS = 24_000      # ~6k token, bir bölüm büyüklüğü
OVERLAP_CHARS = 1_200     # parça sınırında bilgi kopmasın diye bindirme
LONG_DOC_PAGES = 80       # bunun üstü "uzun belge" sayılır


# --------------------------------------------------------------------- #
#  1. İçindekiler                                                        #
# --------------------------------------------------------------------- #

def outline(path) -> list[dict]:
    """PDF'in kendi içindekiler tablosu (varsa).

    Döner: [{"level":1,"title":"3. Nesne Tespiti","page":142,"end":198}, ...]
    Kitapların çoğunda gömülü TOC vardır — bedava bölüm listesi demektir.
    """
    with fitz.open(path) as doc:
        toc = doc.get_toc()
        total = doc.page_count

    items = [{"level": lvl, "title": title.strip(), "page": page} for lvl, title, page in toc if page > 0]

    # her başlığın bittiği sayfayı hesapla
    for i, it in enumerate(items):
        it["end"] = items[i + 1]["page"] - 1 if i + 1 < len(items) else total
        it["pages"] = max(1, it["end"] - it["page"] + 1)

    return items


def slice_pages(pages: list[dict], start: int, end: int) -> list[dict]:
    """Sayfa aralığına göre kırp — öğrenci bölüm seçtiğinde kullanılır."""
    return [p for p in pages if start <= p["page"] <= end]


# --------------------------------------------------------------------- #
#  2. Parçalama                                                          #
# --------------------------------------------------------------------- #

def chunk(pages: list[dict], size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[dict]:
    """Sayfaları karakter bütçesine göre parçalara böler.

    Her parça hangi sayfalardan oluştuğunu taşır — kaynak gösterimi
    bu sayede uzun belgelerde de çalışır.
    """
    chunks: list[dict] = []
    buf: list[str] = []
    buf_pages: list[int] = []
    size_now = 0

    def flush():
        if not buf:
            return
        chunks.append({
            "id": len(chunks),
            "first_page": buf_pages[0],
            "last_page": buf_pages[-1],
            "text": "\n\n".join(buf),
        })

    for p in pages:
        piece = f"[SAYFA {p['page']}]\n{p['text']}"
        if size_now + len(piece) > size and buf:
            flush()
            # bindirme: son parçanın kuyruğunu yeni parçanın başına koy
            tail = "\n\n".join(buf)[-overlap:]
            buf = [tail] if overlap else []
            buf_pages = [buf_pages[-1]]
            size_now = len(tail)
        buf.append(piece)
        buf_pages.append(p["page"])
        size_now += len(piece)

    flush()
    return chunks


# --------------------------------------------------------------------- #
#  3. Getirim — soru sorulduğunda ilgili parçaları bul                   #
# --------------------------------------------------------------------- #
#  Embedding kendi makinende çalışır, API çağrısı yok, maliyet yok.

_model = None


def embedder():
    """Türkçe destekli, küçük ve hızlı model. İlk çağrıda indirilir (~120 MB)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("intfloat/multilingual-e5-small")
    return _model


def embed_chunks(chunks: list[dict]) -> np.ndarray:
    texts = [f"passage: {c['text'][:2000]}" for c in chunks]
    return embedder().encode(texts, normalize_embeddings=True, batch_size=16)


def top_chunks(question: str, chunks: list[dict], vectors: np.ndarray, k: int = 4) -> list[dict]:
    """Soruya en yakın k parçayı döndürür."""
    qv = embedder().encode([f"query: {question}"], normalize_embeddings=True)[0]
    scores = vectors @ qv
    idx = np.argsort(scores)[::-1][:k]
    return [chunks[i] for i in sorted(idx)]


# --------------------------------------------------------------------- #
#  4. Harita-indirgeme özet                                              #
# --------------------------------------------------------------------- #

def map_reduce_analyze(chunks: list[dict], analyze_fn, reduce_fn, progress=None) -> dict:
    """Her parçayı ayrı analiz eder, sonra hepsini tek özete indirger.

    analyze_fn(text) -> dict     (analyze.analyze)
    reduce_fn(list[dict]) -> dict (analyze.reduce_summaries)
    progress(i, total)           (isteğe bağlı — arayüze ilerleme göndermek için)
    """
    partials = []
    for i, c in enumerate(chunks):
        partials.append(analyze_fn(c["text"]))
        if progress:
            progress(i + 1, len(chunks))

    if len(partials) == 1:
        return partials[0]

    return reduce_fn(partials)


def merge_items(partials: list[dict], key: str, limit: int = 40) -> list[dict]:
    """Parçalardan gelen kavram/ipucu listelerini birleştirir, tekrarı temizler."""
    seen: dict[str, dict] = {}
    for part in partials:
        for it in part.get(key, []):
            name = it["text"].strip().lower()
            if name in seen:
                seen[name]["pages"] = sorted(set(seen[name]["pages"] + it.get("pages", [])))[:6]
            else:
                seen[name] = {"text": it["text"].strip(), "pages": it.get("pages", [])[:6]}
    return list(seen.values())[:limit]


# --------------------------------------------------------------------- #
#  5. Maliyet / süre tahmini — kullanıcıya baştan söylemek için          #
# --------------------------------------------------------------------- #

def estimate(chunks: list[dict]) -> dict:
    chars = sum(len(c["text"]) for c in chunks)
    return {
        "chunks": len(chunks),
        "approx_tokens": chars // 4,
        # parça başına ~4 sn, paralel değil
        "approx_seconds": len(chunks) * 4,
    }
