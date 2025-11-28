💻 Laptop Recommender (TR)

Türkiye’deki popüler mağazalardan toplanan laptop verileriyle, kullanım senaryona göre en uygun cihazları öneren kural-tabanlı bir öneri sistemi.

✨ Özellikler

Çoklu kaynak veri: scraper çıktıları + birleştirilmiş dataset

Otomatik veri temizleme & normalizasyon (RAM/SSD/Ekran/CPU/GPU)

Kullanım senaryosu bazlı filtreleme ve puanlama:

🎮 Oyun

💼 Taşınabilirlik

📈 Üretkenlik

🎨 Tasarım (çoklu profil)

👨‍💻 Yazılım geliştirme (alt profiller)

Streamlit arayüzü ile interaktif öneri ekranı

📁 Proje Yapısı
laptop_recommender/
├─ core/                # data_io.py, scoring.py vb. çekirdek modüller
├─ data/                # csv / parq vb. veri dosyaları (opsiyonel)
├─ scrapers/            # mağaza scraper'ları
├─ main_recommender.py  # CLI (terminal) sürümü
└─ streamlit_app.py     # Streamlit arayüzü

✅ Kurulum (Local)
1) Repo’yu klonla
git clone <REPO_URL>
cd laptop_recommender

2) Virtual env oluştur ve aktif et (Windows PowerShell)
py -m venv .venv
.\.venv\Scripts\Activate.ps1

3) Bağımlılıkları yükle
pip install -r requirements.txt


Not: requirements.txt boşsa hızlı kurulum için:

pip install streamlit pandas numpy

▶️ Çalıştırma
Streamlit arayüzü
streamlit run streamlit_app.py

CLI sürümü
python main_recommender.py

🧹 Veri / Scraper Akışı

Uygulama “Hiç veri yüklenemedi” diyorsa genelde sebep: data/ veya scraper çıktıları yoktur.

Seçenek A — Scraper çalıştır
python main_recommender.py --run-scrapers

Seçenek B — Hazır veri ekle

data/ klasörüne CSV dosyalarını koy

Ardından Streamlit’i tekrar başlat

Büyük dosyaları repoya koymak yerine .gitignore ile hariç tutup data/README.md üzerinden “veriyi buraya koyun” yönlendirmesi yapmak daha temizdir.

🛡️ Güvenlik

.streamlit/secrets.toml gibi gizli dosyaları commit etme

API key/env değerlerini .env veya secrets ile yönet

🧭 Yol Haritası (Opsiyonel)

 Fiyat/performans grafiklerinin eklenmesi

 Model bazlı GPU/CPU benchmark eşleme (opsiyonel CSV ile)

 Render/Streamlit Cloud deploy dokümantasyonu

 E2E scraper health-check + log dashboard

📄 Lisans

MIT License

🤝 Katkı

Issue/PR açabilirsin. Öneriler ve iyileştirmeler memnuniyetle!
