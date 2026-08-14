# Atmaca

Ders çalışırken PDF, sunum ya da ders kaydını atıyorsun, Atmaca senin yerine özetliyor, kavram haritası çıkarıyor, sınav sorusu ve kart hazırlıyor. Her şeyin kaynağı belli — hangi bilgi hangi sayfadan/dakikadan geldiğini gösteriyor, uydurmuyor.

Taranmış/fotoğraf PDF'ler de çalışıyor (OCR var), ders kaydı yüklersen kendi bilgisayarında ücretsiz olarak yazıya çeviriyor (Whisper).

## Kullanılan teknolojiler

- Backend: FastAPI, PyMuPDF, Tesseract OCR, faster-whisper, Groq (Llama 3.3 70B)
- Frontend: React + Vite

## Çalıştırmak için

Backend:
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload

Frontend:
cd frontend
npm install
npm run dev

.env dosyasına kendi GROQ_API_KEY'ini eklemen gerekiyor (bu repoda yok, güvenlik için).

## Şu an nerede

Hâlâ geliştiriyorum, kendi bilgisayarımda çalışıyor, henüz bir siteye/sunucuya taşımadım.
