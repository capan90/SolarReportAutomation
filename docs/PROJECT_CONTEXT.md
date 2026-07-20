# SolarReportAutomation — Master Project Context (v3)

## 1. Proje Nedir?

SolarReportAutomation yalnızca bir Playwright scraper değildir.

Bu proje; güneş enerji santrali üretim verileri ile elektrik tüketim/sayaç verilerini farklı portallardan toplayan, bunları ortak bir veri modelinde birleştiren, mahsuplaştıran, analiz eden ve raporlayan kurumsal bir Energy Intelligence Platform'dur.

Projenin temel amacı:

• Üretim verisini iSolar'dan almak
• Tüketim (şebeke/sayaç) verisini GAOSB portalından almak
• Saatlik mahsuplaşma yapmak
• Günlük / Haftalık / Aylık analiz üretmek
• Dashboard ve profesyonel PDF raporları oluşturmak
• Ham veriyi arşivlemek
• Tam izlenebilir (Audit) ve sürdürülebilir bir platform oluşturmak

Bu proje bir scraper değil;

Enterprise ETL + Analytics + Settlement Platformudur.

------------------------------------------------------------

## 2. Projenin Temel Veri Kaynakları

### iSolar

Görev:

GES üretim verileri

Alınacak veriler:

• Günlük üretim
• Saatlik üretim
• Santral bazlı üretim
• Excel Export

Önemli:

Saatlik raporlar kümülatif gelir.

Gerçek saatlik üretim Delta hesaplanarak elde edilir.

------------------------------------------------------------

### GAOSB Portalı

Görev:

Elektrik tüketim ve sayaç verileri

Alınacak veriler:

• Saatlik tüketim
• Günlük sayaç endeksi
• Günlük tüketim
• Haftalık tüketim
• Aylık tüketim

GAOSB verileri mahsuplaşmanın temelidir.

------------------------------------------------------------

## 3. Projenin Nihai Amacı

iSolar

↓

Production

+

GAOSB

↓

Consumption

↓

Canonical Layer

↓

Settlement Engine

↓

Analytics Engine

↓

Dashboard

↓

PDF Reports

↓

Management Reports

Platformın gerçek amacı;

Üretim ve tüketimi ortak veri modelinde birleştirerek saatlik mahsuplaşma hesaplamaktır.

------------------------------------------------------------

## 4. Çalışma Felsefesi

Önce doğruluk.

Sonra otomasyon.

Kod yazmak ilk adım değildir.

Her geliştirme şu sırayı takip eder:

Analiz

↓

Mimari

↓

Plan

↓

Kod

↓

Test

↓

Review

↓

Commit

------------------------------------------------------------

## 5. Mimari İlkeler

• Clean Architecture
• SOLID
• SRP
• OCP
• DIP

Portal bağımlı kod mümkün olduğunca adapter içinde kalmalıdır.

Platform katmanı portal bağımsız olmalıdır.

------------------------------------------------------------

## 6. Portal Framework

Portal Framework;

Portal farklılıklarını izole etmek için oluşturulmaktadır.

Framework;

• Login
• Navigation
• Download
• Export
• Retry
• Session
• Audit

gibi işlemleri ortaklaştıracaktır.

Her portal yalnızca kendi adapterini yazacaktır.

------------------------------------------------------------

## 7. Adapter Yapısı

Şu an aktif hedefler:

✓ iSolar Adapter

✓ GAOSB Adapter

Beklemede:

• SMA Adapter

Kapsam dışı:

Huawei
Growatt
GoodWe
Fronius

Bu portallar için şu an kod geliştirilmeyecektir.

------------------------------------------------------------

## 8. Strategy Layer

Portal davranışları Strategy ile çözülecektir.

Örneğin;

Login Strategy

Export Strategy

Date Selection Strategy

Download Strategy

Polling Strategy

Navigation Strategy

Bu sprintte yalnızca Strategy Contracts oluşturulmaktadır.

Gerçek implementasyon daha sonra gelecektir.

------------------------------------------------------------

## 9. Canonical Layer

En kritik katmandır.

Portal verileri burada ortak dile çevrilir.

Portal

↓

Canonical Record

↓

Validation

↓

Transformation

↓

Settlement

↓

Analytics

↓

Storage

Storage hiçbir zaman portal formatını bilmez.

------------------------------------------------------------

## 10. Settlement Engine

Platformun iş mantığıdır.

Saatlik;

Production

-

Consumption

=

Settlement

hesaplanacaktır.

Buradan;

• Günlük

• Haftalık

• Aylık

• Yıllık

özetler üretilecektir.

------------------------------------------------------------

## 11. Analytics

Analytics;

Dashboard değildir.

Analytics;

Platformun hesaplama servisidir.

Besleyeceği katmanlar:

Dashboard

PDF

REST API

Alarm

AI

------------------------------------------------------------

## 12. Dashboard

Dashboard;

Read Only olacaktır.

Hiçbir zaman;

• ETL çalıştırmaz

• Portal açmaz

• Database yazmaz

Sadece servislerden veri okur.

------------------------------------------------------------

## 13. Raw Archive

İndirilen tüm ham dosyalar saklanacaktır.

Amaç:

Replay

Audit

Debug

Regülasyon

Geçmiş doğrulama

------------------------------------------------------------

## 14. AI Çalışma Modeli

Product Owner

↓

ChatGPT

↓

Claude Code

↓

Antigravity

↓

Review

↓

Test

↓

Commit

ChatGPT:

Software Architect

Claude:

Technical Lead

Antigravity:

Implementation Agent

Kod doğrudan yazılmaz.

Önce mimari oluşturulur.

------------------------------------------------------------

## 15. Güncel Roadmap

AD-5A

Strategy Contracts

↓

AD-5B

Framework Review

↓

AD-6

GAOSB Adapter

↓

AD-7

Canonical Layer

↓

AD-8

iSolar Adapter

↓

AD-9

SMA Adapter (Beklemede)

↓

AD-10

Settlement Engine

------------------------------------------------------------

## 16. Çalışma Kuralları

Kod yazmadan önce plan.

Tek task:

• Maksimum 10 dosya

• Yaklaşık 300 satır

Git işlemleri kullanıcı onayı olmadan yapılmaz.

Mevcut çalışan ETL bozulmaz.

Discovery scriptleri production kodu olmaz.

Yeni teknoloji gerekiyorsa önce ADR hazırlanır.

------------------------------------------------------------

## 17. Nihai Hedef

Platform;

Yeni portal eklendiğinde yalnızca yeni Adapter geliştirilmesini gerektirmelidir.

Platform katmanı değişmemelidir.

Amaç;

Bakımı kolay,

genişletilebilir,

uzun ömürlü,

kurumsal seviyede bir Energy Intelligence Platform oluşturmaktır.