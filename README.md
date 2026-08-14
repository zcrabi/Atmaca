# Atmaca

Ders çalışırken PDF, sunum ya da ders kaydını atıyorsun, Atmaca senin yerine özetliyor, kavram haritası çıkarıyor, sınav sorusu ve kart hazırlıyor. Her şeyin kaynağı belli — hangi bilgi hangi sayfadan/dakikadan geldiğini gösteriyor, uydurmuyor.

Taranmış/fotoğraf PDF'ler de çalışıyor (OCR var), ders kaydı yüklersen kendi bilgisayarında ücretsiz olarak yazıya çeviriyor (Whisper).
<img width="1919" height="968" alt="Ekran görüntüsü 2026-08-14 123330" src="https://github.com/user-attachments/assets/6c1c7280-7bbc-4c21-b9c6-e83978ec1023" />
<img width="1919" height="987" alt="Ekran görüntüsü 2026-08-14 123418" src="https://github.com/user-attachments/assets/c5c39123-2563-4229-976d-10b72acf4de2" />
<img width="1919" height="972" alt="Ekran görüntüsü 2026-08-14 123453" src="https://github.com/user-attachments/assets/ca3462ca-334f-4606-9790-8d51ef469534" />
<img width="1907" height="963" alt="Ekran görüntüsü 2026-08-14 123648" src="https://github.com/user-attachments/assets/e771ea0f-a382-4bfe-93ae-95f7482e5390" />
<img width="1916" height="908" alt="Ekran görüntüsü 2026-08-14 123702" src="https://github.com/user-attachments/assets/dead5e30-6f4e-49d4-8c9f-f2e83fe345b0" />
<img width="1919" height="915" alt="Ekran görüntüsü 2026-08-14 123746" src="https://github.com/user-attachments/assets/884b2a99-d85e-44e4-9a7b-cf5dca4e2651" />
<img width="1916" height="909" alt="Ekran görüntüsü 2026-08-14 123915" src="https://github.com/user-attachments/assets/c5a349ec-3e3f-462d-bc6b-7464c7862614" />
<img width="1899" height="905" alt="Ekran görüntüsü 2026-08-14 123929" src="https://github.com/user-attachments/assets/ed076d29-02e3-4e8c-b9bf-378b5713fed4" />

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


