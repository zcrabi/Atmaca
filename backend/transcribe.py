"""
transcribe.py — Ders kaydından not çıkarma.

Ana fikir: sesin "sayfası" yoktur, ama zamanı vardır. Bu yüzden
transkripti ~2 dakikalık bloklara bölüp her bloğa bir sahte sayfa
numarası veriyoruz.

Böylece analyze.py, longdoc.py ve verify.py'de TEK SATIR değişmiyor —
hepsi zaten [{"page": n, "text": "..."}] bekliyor. Arayüzde sadece
"s.12" yerine "12:40" yazacağız.

Whisper modeli kendi makinende çalışır, API maliyeti yoktur.

Hız notu: model "base"e düşürüldü, tüm CPU çekirdekleri kullanılıyor
(cpu_threads) ve beam_size=1 (greedy decode) ile çalışıyor. Bu üçü
birlikte "small" + varsayılan ayarlara göre belirgin şekilde hızlanma
sağlar. Doğruluk biraz düşer ama ders kaydı transkripti için genelde
yeterli kalır. Daha yüksek doğruluk istersen MODEL_SIZE="small" yap,
daha da hız istersen "tiny" dene.
"""
from __future__ import annotations
import os

BLOCK_SECONDS = 120  # bir "sayfa" = 2 dakika konuşma

# Ortam değişkeniyle override edilebilir: set WHISPER_MODEL=small
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")
BEAM_SIZE = int(os.environ.get("WHISPER_BEAM_SIZE", "1"))

_model = None


def model(size: str = MODEL_SIZE):
    """faster-whisper modeli. 'base' CPU'da hızlı ve Türkçede makul
    sonuç verir. Daha iyi doğruluk için 'small'/'medium', daha hızlısı
    için 'tiny' kullanabilirsin (WHISPER_MODEL ortam değişkeniyle)."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        cpu_threads = os.cpu_count() or 4
        _model = WhisperModel(
            size,
            device="cpu",
            compute_type="int8",
            cpu_threads=cpu_threads,
        )
    return _model


def mmss(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def transcribe(path: str, language: str = "tr") -> dict:
    """Ses dosyasını bloklara ayrılmış transkripte çevirir.

    Döner:
      {
        "pages":  [{"page": 1, "text": "..."}, ...],   # analiz zinciri bunu bekliyor
        "marks":  {1: "0:00", 2: "2:00", ...},         # sayfa → zaman damgası
        "duration": 3120.4,
        "full": "tüm transkript"
      }
    """
    segments, info = model().transcribe(
        path,
        language=language,
        vad_filter=True,        # sessizlikleri atla — hem hızlandırır hem temizler
        beam_size=BEAM_SIZE,    # 1 = greedy, varsayılan 5'ten çok daha hızlı
    )
    pages: list[dict] = []
    marks: dict[int, str] = {}
    buf: list[str] = []
    block_start = 0.0
    page_no = 1
    end = 0.0

    def flush():
        nonlocal buf
        if buf:
            pages.append({"page": page_no, "text": " ".join(buf).strip()})
            marks[page_no] = mmss(block_start)
            buf = []

    for seg in segments:
        end = seg.end
        if seg.start - block_start >= BLOCK_SECONDS and buf:
            flush()
            page_no += 1
            block_start = seg.start
        buf.append(seg.text.strip())
    flush()

    return {
        "pages": pages,
        "marks": marks,
        "duration": end,
        "full": " ".join(p["text"] for p in pages),
    }


def label_pages(result: dict, marks: dict[int, str]) -> dict:
    """Analiz çıktısındaki sayfa numaralarını zaman damgasına çevirir.
    Arayüz 's.7' yerine '14:00' göstersin diye. Sayfa numaralarını
    silmiyoruz, yanına etiket ekliyoruz — kuşbakışı şeridi hâlâ çalışır.
    """
    def conv(items):
        out = []
        for it in items:
            it = dict(it)
            it["marks"] = [marks.get(p, "") for p in it.get("pages", [])]
            out.append(it)
        return out

    for key in ("summary", "concepts", "likely"):
        if key in result:
            result[key] = conv(result[key])
    return result


if __name__ == "__main__":
    import sys
    import time
    if len(sys.argv) < 2:
        print("kullanım: python transcribe.py ders.mp3")
        raise SystemExit(1)
    t0 = time.time()
    r = transcribe(sys.argv[1])
    print(f"süre        : {mmss(r['duration'])}")
    print(f"blok sayısı : {len(r['pages'])}")
    print(f"kelime      : {len(r['full'].split())}")
    print(f"işlem süresi: {time.time()-t0:.1f}s  (model={MODEL_SIZE}, beam={BEAM_SIZE})")
    print("\n--- ilk blok ---")
    print(r["pages"][0]["text"][:400] if r["pages"] else "(boş)")
