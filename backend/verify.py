"""
verify.py — Sayfa numarası doğrulama.

Model "IoU sayfa 22'de geçiyor" diyor. Biz buna güvenmiyoruz: o sayfanın
metnine bakıp terim gerçekten orada mı diye kontrol ediyoruz. Yoksa
sayfa numarasını sessizce düşürüyoruz.

Neden önemli: kaynak gösterimi bu ürünün ana iddiası. Yanlış sayfa
göstermek, hiç göstermemekten daha kötüdür — öğrenci gidip bakar,
bulamaz, bir daha güvenmez.
"""

from __future__ import annotations

import re
import unicodedata

# Türkçe büyük/küçük harf ve aksan farklarını eritmek için
_TR = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iisSgGuUoOcC")


def norm(s: str) -> str:
    s = s.translate(_TR).lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def page_index(pages: list[dict]) -> dict[int, str]:
    """{sayfa_no: normalize edilmiş metin}"""
    return {p["page"]: norm(p["text"]) for p in pages}


def _terms(text: str) -> list[str]:
    """Aranacak anahtar parçalar: 3 harften uzun kelimeler."""
    return [w for w in norm(text).split() if len(w) > 3][:6]


def check(text: str, page: int, index: dict[int, str], window: int = 1) -> bool:
    """Verilen metnin anahtar kelimeleri o sayfada (veya komşusunda) geçiyor mu?

    window=1 → 1 sayfa sapmaya izin verilir; PDF sayfa numaraları ile
    fiziksel sayfa sırası çoğu kitapta birebir örtüşmez.
    """
    words = _terms(text)
    if not words:
        return True  # kontrol edilecek bir şey yok, engelleme

    hay = " ".join(index.get(p, "") for p in range(page - window, page + window + 1))
    hits = sum(1 for w in words if w in hay)
    return hits >= max(1, len(words) // 3)


def filter_pages(items: list[dict], index: dict[int, str], key: str = "pages") -> tuple[list[dict], int]:
    """Kavram/özet listelerindeki doğrulanmayan sayfa numaralarını atar.

    Döner: (temizlenmiş liste, atılan sayfa sayısı)
    """
    dropped = 0
    out = []
    for it in items:
        good = [p for p in it.get(key, []) if check(it.get("text", ""), p, index)]
        dropped += len(it.get(key, [])) - len(good)
        out.append({**it, key: good})
    return out, dropped


def filter_single(items: list[dict], index: dict[int, str], text_key: str, page_key: str = "page"):
    """Soru gibi tek sayfalı kayıtlar için. Doğrulanmayanda sayfa None olur."""
    dropped = 0
    out = []
    for it in items:
        p = it.get(page_key)
        if p and not check(it.get(text_key, "") + " " + it.get("a", ""), p, index):
            it = {**it, page_key: None}
            dropped += 1
        out.append(it)
    return out, dropped


def verify_analysis(result: dict, pages: list[dict]) -> dict:
    """Analiz çıktısının tamamını doğrular ve rapor ekler."""
    index = page_index(pages)
    total_dropped = 0

    for key in ("summary", "concepts", "likely"):
        if key in result:
            result[key], d = filter_pages(result[key], index)
            total_dropped += d

    result["_verify"] = {"dropped_pages": total_dropped}
    return result
