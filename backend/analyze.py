"""
analyze.py — Groq + Llama 3.3 70B ile analiz.

Neden Groq: ücretsiz kotası cömert, hızı inanılmaz (saniyede 800 token),
Türkçe desteği güçlü. Gemini'nin 429 kota sorununu çözer.

Hız/kota notu: uzun kitaplarda (longdoc map-reduce) çok sayıda istek
kısa sürede gidiyor ve Groq'un dakikalık token limitine (TPM) takılıp
429 RateLimitError dönebiliyor. _call artık bu hatayı otomatik
yakalayıp Groq'un söylediği süre kadar bekleyip yeniden deniyor —
kullanıcıya "Veri alma işlemi başarısız oldu" hatası göstermek yerine
sessizce bekleyip devam ediyor.
"""

import json
import os
import re
import time
from groq import Groq

try:
    from groq import RateLimitError, APIStatusError
except ImportError:
    # Kurulu groq sürümü bu sınıfları farklı yerden export ediyor olabilir —
    # o zaman generic Exception + mesaj metnine bakarak yakalayacağız.
    RateLimitError = None
    APIStatusError = None

MODEL = "llama-3.3-70b-versatile"

_client = None

MAX_RETRIES = 5
DEFAULT_WAIT = 8.0   # Groq mesajından süre çıkaramazsak bu kadar bekle


def client():
    global _client
    if _client is None:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY tanımlı değil (.env dosyasına ekle)")
        _client = Groq(api_key=key)
    return _client


def _extract_wait_seconds(err) -> float:
    """Groq'un hata mesajından 'Please try again in 16.055s' gibi bir
    süre varsa onu ayıklar, yoksa varsayılan bekleme süresini döner."""
    msg = str(err)
    m = re.search(r"try again in ([\d.]+)s", msg)
    if m:
        try:
            return float(m.group(1)) + 0.5  # küçük bir güvenlik payı
        except ValueError:
            pass
    return DEFAULT_WAIT


def _call(prompt: str) -> dict:
    """Groq'tan JSON cevap ister. Kota (429) hatasında otomatik
    yeniden dener (bekleyerek), diğer hatalarda direkt fırlatır."""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client().chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "Sen bir JSON üreticisin. Sadece geçerli JSON döndür, başka hiçbir şey yazma."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000,
            )
            text = resp.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())

        except Exception as e:
            is_rate_limit = (
                (RateLimitError is not None and isinstance(e, RateLimitError))
                or "429" in str(e)
                or "rate_limit" in str(e).lower()
            )
            is_server_error = (
                (APIStatusError is not None and isinstance(e, APIStatusError)
                 and getattr(e, "status_code", 0) >= 500)
            )

            if is_rate_limit:
                last_err = e
                wait = _extract_wait_seconds(e)
                print(f"[analyze] Kota limiti (429), {wait:.1f}sn bekleniyor "
                      f"(deneme {attempt}/{MAX_RETRIES})...")
                time.sleep(wait)
                continue

            if is_server_error:
                last_err = e
                wait = DEFAULT_WAIT * attempt
                print(f"[analyze] Groq sunucu hatası, {wait:.1f}sn bekleniyor "
                      f"(deneme {attempt}/{MAX_RETRIES})...")
                time.sleep(wait)
                continue

            # Kota/sunucu hatası değilse (örn. JSON parse hatası) direkt fırlat
            raise

    # Tüm denemeler bitti, son hatayı fırlat
    raise last_err


# ------------------------------------------------------------------ #
#  1. Analiz                                                           #
# ------------------------------------------------------------------ #

ANALYZE_PROMPT = """Aşağıdaki ders materyalini analiz et ve SADECE şu JSON formatında cevap ver:

{{
  "title": "materyalin başlığı",
  "difficulty": 2,
  "readingMin": 10,
  "summaryMin": 2,
  "summary": [
    {{"text": "akademik özet cümlesi", "simple": "günlük dilde açıklama", "pages": [1, 2]}}
  ],
  "concepts": [
    {{"text": "kavram adı", "pages": [1]}}
  ],
  "likely": [
    {{"text": "sınavda çıkabilecek konu", "pages": [1]}}
  ]
}}

Kurallar:
- difficulty: 1 (kolay), 2 (orta), 3 (zor)
- summary: 5-7 madde
- concepts: en önemli 8-10 kavram
- likely: sınavda çıkma ihtimali yüksek 3-5 konu
- pages: [SAYFA n] etiketlerinden gelen gerçek sayfa numaraları
- Türkçe yaz
- SADECE JSON döndür

MATERYAL:
{text}"""


def analyze(page_text: str) -> dict:
    return _call(ANALYZE_PROMPT.format(text=page_text[:12000]))


# ------------------------------------------------------------------ #
#  2. Özet birleştirme (uzun belgeler için)                            #
# ------------------------------------------------------------------ #

REDUCE_PROMPT = """Aşağıdaki bölüm özetlerini tek bir bütünlüklü özete birleştir.
SADECE JSON formatında döndür, açıklama ekleme.

{{
  "title": "genel başlık",
  "difficulty": 2,
  "readingMin": 30,
  "summaryMin": 3,
  "summary": [{{"text": "...", "simple": "...", "pages": [1]}}],
  "concepts": [{{"text": "...", "pages": [1]}}],
  "likely": [{{"text": "...", "pages": [1]}}]
}}

BÖLÜM ÖZETLERİ:
{parts}"""


def reduce_summaries(partials: list[dict]) -> dict:
    parts = json.dumps(partials, ensure_ascii=False)[:8000]
    return _call(REDUCE_PROMPT.format(parts=parts))


# ------------------------------------------------------------------ #
#  3. Soru ve kart üretimi                                             #
# ------------------------------------------------------------------ #

QUIZ_PROMPT = """Aşağıdaki ders materyalinden {count} adet sınav sorusu üret.
SADECE JSON formatında döndür:

{{"items": [
  {{"q": "soru metni", "a": "kısa cevap", "page": 1}}
]}}

Kurallar:
- Farklı türde sorular: tanım, karşılaştırma, sayısal, uygulama
- Materyalde olmayan şeyi uydurma
- {count} soru çıkmıyorsa daha az üret
- Türkçe yaz

MATERYAL:
{text}"""

CARDS_PROMPT = """Aşağıdaki ders materyalinden {count} adet çalışma kartı üret.
SADECE JSON formatında döndür:

{{"items": [
  {{"front": "kavram (kısa)", "back": "tanım (tek cümle)"}}
]}}

Kurallar:
- front: en fazla 3 kelime
- back: ezberlenebilir, kısa
- Türkçe yaz

MATERYAL:
{text}"""


def generate(kind: str, page_text: str, count: int, exclude: list[str] | None = None) -> list[dict]:
    if kind == "quiz":
        prompt = QUIZ_PROMPT.format(count=count, text=page_text[:10000])
    elif kind == "cards":
        prompt = CARDS_PROMPT.format(count=count, text=page_text[:10000])
    else:
        raise ValueError("kind 'quiz' veya 'cards' olmalı")

    return _call(prompt).get("items", [])


# ------------------------------------------------------------------ #
#  4. Soru-cevap                                                       #
# ------------------------------------------------------------------ #

ASK_PROMPT = """Aşağıdaki ders materyaline dayanarak soruyu cevapla.
SADECE JSON formatında döndür:

{{"text": "cevap metni", "pages": [1, 2]}}

Kurallar:
- SADECE materyaldeki bilgiyi kullan
- Materyalde yoksa: "Bu ders notunda bu bilgi yok." yaz
- pages: cevabın dayandığı sayfa numaraları
- Türkçe yaz

SORU: {question}

MATERYAL:
{text}"""


def ask(page_text: str, question: str) -> dict:
    return _call(ASK_PROMPT.format(question=question, text=page_text[:10000]))
