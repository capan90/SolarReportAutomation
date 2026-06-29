# SolarReportAutomation

Şirketin İsOlar sistemi üzerinden günlük üretim verilerini güvenli şekilde toplayıp, veritabanına kaydetmek, analiz etmek, dashboard üretmek ve profesyonel PDF raporlar hazırlamak için geliştirilen kurumsal otomasyon projesidir.

## Temel Hedefler

- İsOlar sistemine kontrollü giriş yapmak
- Günlük üretim verilerini çekmek
- Verileri doğrulamak ve saklamak
- Yönetici raporları oluşturmak
- Grafik destekli PDF çıktılar üretmek
- Dashboard üzerinden geçmiş verileri izlemek
- Hataları loglamak ve izlenebilir hale getirmek

## Teknoloji

- Python
- Playwright
- PostgreSQL / SQLite
- Pandas
- Plotly
- Streamlit
- HTML to PDF raporlama
- Git
- Antigravity kontrollü agent geliştirme

## Güvenlik İlkeleri

- Şifreler kod içine yazılmaz.
- `.env` dosyası Git'e eklenmez.
- Antigravity otomatik terminal komutları onaysız çalıştırılmaz.
- Scraping işlemleri kontrollü ve düşük frekansta yapılır.
- Captcha veya güvenlik sistemleri aşılmaya çalışılmaz.