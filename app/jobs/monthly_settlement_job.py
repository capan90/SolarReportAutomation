import datetime
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

import pandas as pd

from app.infrastructure.browser.playwright_client import PlaywrightClient
from app.extractors.isolar.extractor import IsolarExtractor
from app.sources.gaosb.extractor import (
    GaosbExtractor,
    GaosbCaptchaRequiredError,
    CAPTCHA_FLAG_PATH,
)
from app.settlement.engine import SettlementEngine
from app.settlement.models import HourlySettlement
from app.notifications.notification_service import NotificationService
from app.core.logger import setup_logger
from app.core.config import settings

logger = setup_logger("MonthlySettlementJob")

AY_ADLARI = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


class MonthlySettlementJob:
    """
    Neden: DailySettlementJob'un aylık versiyonu — bir takvim ayının tamamı için
    iSolar Curve (mode="month", saatlik seri) ve GAOSB verilerini çekip saatlik
    mahsuplaşma hesaplar, aylık Excel raporu üretir ve e-posta ile bildirir.
    """

    @staticmethod
    def _load_gaosb_month(file_path: Path, target_month: str) -> pd.DataFrame:
        """
        Neden: SettlementEngine.load_gaosb() günlük akış için tasarlanmıştır ve
        veriyi dosyadaki İLK GÜNE filtreler; aylık akışta bu, 744 saatlik veriyi
        24 satıra indirir. Burada aynı okuma/normalizasyon yapılır ancak hedef
        AYA (YYYY-MM) filtrelenir. Kolonlara pozisyonla erişilir (0=Tarih, 5=Endeks değeri).
        """
        import numpy as np

        try:
            df = pd.read_excel(file_path, engine='openpyxl')
        except Exception:
            df = pd.read_excel(file_path, engine='xlrd')

        if df.empty:
            return pd.DataFrame(columns=['timestamp', 'consumption_kwh'])

        date_col = df.columns[0]
        val_col = df.columns[5]
        df = df.dropna(subset=[date_col, val_col])

        # Neden: Excel seri tarih formatını (varsa) standart datetime nesnesine dönüştürmek
        dates = []
        for val in df[date_col]:
            if isinstance(val, (int, float, np.integer, np.floating)) and not isinstance(val, bool):
                dates.append(datetime.datetime(1899, 12, 30) + datetime.timedelta(days=val))
            else:
                dates.append(pd.to_datetime(val))
        df['parsed_date'] = pd.to_datetime(dates)

        df['consumption_kwh'] = pd.to_numeric(df[val_col], errors='coerce').fillna(0.0)
        df['timestamp'] = df['parsed_date'].dt.strftime("%Y-%m-%d %H:00:00")

        result = df[['timestamp', 'consumption_kwh']].groupby('timestamp', as_index=False).sum()
        result = result[result['timestamp'].str.startswith(target_month)].reset_index(drop=True)
        return result

    @staticmethod
    def _calculate_monthly(df_prod: pd.DataFrame, df_cons: pd.DataFrame) -> List[HourlySettlement]:
        """
        Neden: SettlementEngine.calculate() ile aynı saatlik mahsup matematiği,
        ancak aylık (ay filtreli) üretim/tüketim DataFrame'leri üzerinden çalışır.
        """
        merged = pd.merge(df_prod, df_cons, on='timestamp').sort_values('timestamp')

        settlements: List[HourlySettlement] = []
        for _, row in merged.iterrows():
            prod = float(row['production_kwh'])
            cons = float(row['consumption_kwh'])
            settled = min(prod, cons)
            settlements.append(HourlySettlement(
                timestamp=str(row['timestamp']),
                production_kwh=prod,
                consumption_kwh=cons,
                settled_kwh=settled,
                grid_export_kwh=max(0.0, prod - cons),
                grid_import_kwh=max(0.0, cons - prod),
            ))
        return settlements

    @staticmethod
    def _five_metrics(settlements: List[HourlySettlement]) -> Dict[str, float]:
        """Neden: Rapor sayfalarında tekrarlanan beş metrik toplamını tek yerde hesaplamak."""
        return {
            "Üretim (kWh)": sum(s.production_kwh for s in settlements),
            "Tüketim (kWh)": sum(s.consumption_kwh for s in settlements),
            "Mahsup (kWh)": sum(s.settled_kwh for s in settlements),
            "Şebekeden Çekiş (kWh)": sum(s.grid_import_kwh for s in settlements),
            "Fazla Satış (kWh)": sum(s.grid_export_kwh for s in settlements),
        }

    def _write_monthly_report(
        self,
        settlements: List[HourlySettlement],
        output_path: Path,
        month_dt: datetime.datetime,
        prev_totals: Optional[Dict[str, float]],
    ) -> Path:
        """
        Neden: Aylık raporu 4 sayfalı üretmek:
        1) Ay Özeti (+ önceki ay karşılaştırması), 2) Haftalık Kırılım,
        3) Günlük Kırılım, 4) Saatlik Detay (tüm ay, 744 satır).
        Günlük rapordaki SettlementReportWriter formatı yerine aylık format kullanılır.
        """
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        font_header = Font(bold=True)
        fill_gray = PatternFill(start_color="EAEAEA", end_color="EAEAEA", fill_type="solid")

        def _style_header(ws, row_idx: int, n_cols: int):
            for c in range(1, n_cols + 1):
                cell = ws.cell(row=row_idx, column=c)
                cell.font = font_header
                cell.fill = fill_gray
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        metric_keys = ["Üretim (kWh)", "Tüketim (kWh)", "Mahsup (kWh)",
                       "Şebekeden Çekiş (kWh)", "Fazla Satış (kWh)"]
        prev_key_map = {
            "Üretim (kWh)": "production_kwh",
            "Tüketim (kWh)": "consumption_kwh",
            "Mahsup (kWh)": "settled_kwh",
            "Şebekeden Çekiş (kWh)": "grid_import_kwh",
            "Fazla Satış (kWh)": "grid_export_kwh",
        }

        ay_str = f"{AY_ADLARI[month_dt.month - 1]} {month_dt.year}"
        prev_month_dt = (month_dt.replace(day=1) - datetime.timedelta(days=1))
        prev_ay_str = f"{AY_ADLARI[prev_month_dt.month - 1]} {prev_month_dt.year}"

        wb = openpyxl.Workbook()

        # ---- Sheet 1: Ay Özeti ----
        ws1 = wb.active
        ws1.title = "Ay Özeti"
        totals = self._five_metrics(settlements)
        ws1.append(["METRİK", f"{ay_str}", f"Önceki Ay ({prev_ay_str})", "DEĞİŞİM (%)"])
        _style_header(ws1, 1, 4)
        for key in metric_keys:
            cur = round(totals[key], 1)
            if prev_totals:
                prev = round(prev_totals[prev_key_map[key]], 1)
                degisim = round((cur - prev) / prev * 100, 1) if prev else None
            else:
                prev, degisim = None, None
            ws1.append([f"Toplam {key}", cur, prev if prev is not None else "-",
                        degisim if degisim is not None else "-"])
        ws1.column_dimensions["A"].width = 30
        for col in ("B", "C", "D"):
            ws1.column_dimensions[col].width = 22

        # Saatlik kayıtları güne göre grupla (Sheet 2 ve 3 için ortak)
        by_day: Dict[str, List[HourlySettlement]] = {}
        for s in settlements:
            by_day.setdefault(str(s.timestamp)[:10], []).append(s)
        days_sorted = sorted(by_day.keys())

        # ---- Sheet 2: Haftalık Kırılım (gün 1-7, 8-14, 15-21, 22-28, 29-son) ----
        ws2 = wb.create_sheet("Haftalık Kırılım")
        ws2.append(["HAFTA", "TARİH ARALIĞI"] + [k.upper() for k in metric_keys])
        _style_header(ws2, 1, 7)
        for week_idx in range(5):
            start_day = week_idx * 7 + 1
            week_days = [d for d in days_sorted if start_day <= int(d[8:10]) <= start_day + 6]
            if not week_days:
                continue
            week_settlements = [s for d in week_days for s in by_day[d]]
            wt = self._five_metrics(week_settlements)
            ws2.append(
                [f"Hafta {week_idx + 1}", f"{week_days[0]} - {week_days[-1]}"]
                + [round(wt[k], 1) for k in metric_keys]
            )
        for col in ("A", "B", "C", "D", "E", "F", "G"):
            ws2.column_dimensions[col].width = 24

        # ---- Sheet 3: Günlük Kırılım ----
        ws3 = wb.create_sheet("Günlük Kırılım")
        ws3.append(["TARİH"] + [k.upper() for k in metric_keys])
        _style_header(ws3, 1, 6)
        for d in days_sorted:
            dt_metrics = self._five_metrics(by_day[d])
            ws3.append([d] + [round(dt_metrics[k], 1) for k in metric_keys])
        for col in ("A", "B", "C", "D", "E", "F"):
            ws3.column_dimensions[col].width = 22

        # ---- Sheet 4: Saatlik Detay (tüm ay) ----
        ws4 = wb.create_sheet("Saatlik Detay")
        ws4.append(["TARİH", "SAAT ARALIĞI"] + [k.upper() for k in metric_keys])
        _style_header(ws4, 1, 7)
        for s in settlements:
            ts = str(s.timestamp)
            hour = int(ts[11:13])
            ws4.append([
                ts[:10],
                f"{hour:02d}:00-{(hour + 1) % 24:02d}:00",
                round(s.production_kwh, 1),
                round(s.consumption_kwh, 1),
                round(s.settled_kwh, 1),
                round(s.grid_import_kwh, 1),
                round(s.grid_export_kwh, 1),
            ])
        for col in ("A", "B", "C", "D", "E", "F", "G"):
            ws4.column_dimensions[col].width = 20

        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        wb.close()
        logger.info(f"4 sayfalı aylık rapor kaydedildi: {output_path}")
        return output_path

    def run(
        self,
        target_month: Optional[str] = None,
        isolar_file: Optional[Path] = None,
        gaosb_file: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        target_month: "YYYY-MM" formatında; None ise geçen ay.
        isolar_file / gaosb_file: verilirse indirme atlanır, mevcut dosya kullanılır
        (test ve yeniden koşum senaryoları için).
        """
        start_time = datetime.datetime.now()

        # 1. target_month hesapla (None -> geçen ay)
        if not target_month:
            first_of_month = datetime.date.today().replace(day=1)
            prev_month = first_of_month - datetime.timedelta(days=1)
            target_month = prev_month.strftime("%Y-%m")

        logger.info(f"Monthly Settlement Job BAŞLADI. Hedef Ay: {target_month}")

        try:
            month_dt = datetime.datetime.strptime(target_month, "%Y-%m")
        except ValueError as e:
            logger.error(f"Geçersiz ay formatı (YYYY-MM olmalı): {target_month}")
            return {
                "status": "FAILED",
                "month": target_month,
                "report_path": None,
                "settlement_count": 0,
                "error": f"Geçersiz ay formatı: {e}",
            }

        # 2. Tarih aralığı: ayın ilk günü -> sonraki ayın ilk günü (GAOSB açık aralık)
        date_from = month_dt.strftime("%Y-%m-01")
        if month_dt.month == 12:
            next_month = month_dt.replace(year=month_dt.year + 1, month=1)
        else:
            next_month = month_dt.replace(month=month_dt.month + 1)
        date_to = next_month.strftime("%Y-%m-01")

        output_dir = Path("outputs/reports") / target_month
        output_dir.mkdir(parents=True, exist_ok=True)

        run_id = f"job-settlement-monthly-{target_month}-{int(time.time())}"
        headless = settings.headless

        isolar_path: Optional[Path] = Path(isolar_file) if isolar_file else None
        gaosb_path: Optional[Path] = Path(gaosb_file) if gaosb_file else None
        rapor_path: Optional[Path] = None
        settlements = []
        settlement_count = 0
        prev_totals: Optional[Dict[str, float]] = None
        error_msg: Optional[str] = None

        # 3. iSolar Curve indir — mode="month" (Best-effort)
        if isolar_path:
            logger.info(f"1. Aşama ATLANDI: mevcut iSolar dosyası kullanılıyor: {isolar_path}")
        else:
            try:
                logger.info(f"1. Aşama: iSolar Curve (month) indirme başlatılıyor (Ay: {target_month})...")
                with PlaywrightClient(headless=headless) as client:
                    page = client.create_page()
                    extractor = IsolarExtractor(page, run_id=run_id)
                    extractor.login_and_verify()
                    extractor.navigate_to_curve_page()
                    isolar_path = extractor.download_hourly_curve_report(
                        date_str=target_month, mode="month"
                    )
                logger.info(f"1. Aşama BAŞARILI. İndirilen dosya: {isolar_path}")
            except Exception as e:
                err_txt = f"iSolar Curve (month) indirme aşaması başarısız: {e}"
                logger.error(err_txt)
                error_msg = err_txt

        # 4. GAOSB indir (Best-effort)
        if gaosb_path:
            logger.info(f"2. Aşama ATLANDI: mevcut GAOSB dosyası kullanılıyor: {gaosb_path}")
        else:
            try:
                logger.info(f"2. Aşama: GAOSB raporu indirme başlatılıyor ({date_from} -> {date_to})...")
                extractor = GaosbExtractor()
                gaosb_path = extractor.download_report(
                    output_dir=output_dir,
                    date_from=date_from,
                    date_to=date_to,
                    headless=headless,
                )
                logger.info(f"2. Aşama BAŞARILI. İndirilen dosya: {gaosb_path}")
            except GaosbCaptchaRequiredError:
                # Neden: Captcha manuel doğrulama ister; job duraklatılır, yönetici
                # e-posta ile bilgilendirilir ve dashboard doğrulama akışı devreye girer.
                logger.warning("GAOSB captcha doğrulaması gerekiyor; aylık job duraklatılıyor.")
                try:
                    import json as _json
                    flag_info = {}
                    if CAPTCHA_FLAG_PATH.exists():
                        try:
                            flag_info = _json.loads(CAPTCHA_FLAG_PATH.read_text(encoding="utf-8-sig"))
                        except Exception:
                            flag_info = {}
                    flag_info.update({"job_type": "monthly", "target": target_month})
                    CAPTCHA_FLAG_PATH.write_text(_json.dumps(flag_info), encoding="utf-8")
                except Exception as flag_err:
                    logger.error(f"Captcha flag güncellenemedi (best-effort): {flag_err}")

                try:
                    notifier = NotificationService()
                    notifier.notify_pipeline(
                        run_id=run_id,
                        exit_code=2,
                        duration_ms=int((datetime.datetime.now() - start_time).total_seconds() * 1000),
                        stage_summary=(
                            f"{target_month} ayına ait aylık mahsuplaşma için GAOSB "
                            f"güvenlik doğrulaması gerekiyor.\n\n"
                            f"Lütfen dashboard'a girin ve "
                            f"'GAOSB Doğrulamasını Tamamla' butonuna tıklayın.\n"
                            f"Doğrulama sonrası rapor otomatik yeniden hazırlanacak."
                        ),
                        event_type="CAPTCHA_REQUIRED",
                        force=True,
                        email_profile="monthly"
                    )
                except Exception as mail_err:
                    logger.error(f"Captcha bildirimi gönderilemedi (best-effort): {mail_err}")

                return {
                    "status": "CAPTCHA_REQUIRED",
                    "month": target_month,
                    "report_path": None,
                    "settlement_count": 0,
                    "error": "GAOSB captcha doğrulaması gerekiyor",
                }
            except Exception as e:
                err_txt = f"GAOSB raporu indirme aşaması başarısız: {e}"
                logger.error(err_txt)
                error_msg = f"{error_msg} | {err_txt}" if error_msg else err_txt

        # 5. Settlement hesapla ve Excel rapor üret (Best-effort)
        try:
            if not isolar_path or not gaosb_path:
                raise ValueError(
                    "iSolar veya GAOSB dosya yollarından en az biri eksik olduğu için mahsuplaşma hesaplanamaz."
                )

            logger.info("3. Aşama: Aylık mahsuplaşma hesabı başlatılıyor...")
            engine = SettlementEngine()
            isolar_df = engine.load_isolar_curve(isolar_path)
            gaosb_df = self._load_gaosb_month(gaosb_path, target_month)
            settlements = self._calculate_monthly(isolar_df, gaosb_df)
            settlement_count = len(settlements)
            logger.info(f"Mahsuplaşma hesabı tamamlandı. Kayıt sayısı: {settlement_count}")

            # 3b. Önceki ay karşılaştırması için DB'den oku, sonra bu ayın
            # sonuçlarını yaz (Best-effort: DB hatası rapor üretimini engellemez).
            try:
                from app.database.settlement_repository import SettlementRepository
                repo = SettlementRepository()

                prev_month_dt = month_dt.replace(day=1) - datetime.timedelta(days=1)
                prev_totals = repo.get_monthly(prev_month_dt.year, prev_month_dt.month)

                repo.upsert_hourly(settlements)  # tüm ay saatlik
                repo.upsert_monthly(month_dt.year, month_dt.month, settlements)
                logger.info("Mahsuplaşma sonuçları veritabanına yazıldı (hourly + monthly).")
            except Exception as db_err:
                logger.error(f"Mahsuplaşma DB yazımı başarısız (rapor üretimine devam ediliyor): {db_err}")

            logger.info("4. Aşama: Excel raporu (4 sayfa) yazılıyor...")
            rapor_path = output_dir / f"mahsup_{month_dt.strftime('%Y%m')}_aylik.xlsx"
            self._write_monthly_report(settlements, rapor_path, month_dt, prev_totals)
            logger.info(f"4. Aşama BAŞARILI. Rapor üretildi: {rapor_path}")
        except Exception as e:
            err_txt = f"Mahsuplaşma veya rapor yazma aşaması başarısız: {e}"
            logger.error(err_txt)
            error_msg = f"{error_msg} | {err_txt}" if error_msg else err_txt

        # 6. E-Posta bildirimi gönder (Best-effort)
        try:
            logger.info("5. Aşama: E-Posta bildirimi gönderiliyor...")
            notifier = NotificationService()

            if rapor_path and rapor_path.exists():
                # Neden: E-posta yöneticiye gider; teknik detay yerine Türkçe ay adı
                # ve mahsup istatistikleri gösterilir (DailySettlementJob ile aynı kalıp).
                ay_str = f"{AY_ADLARI[month_dt.month - 1]} {month_dt.year}"

                def _fmt_kwh(value: float) -> str:
                    # Neden: Türkçe sayı biçimi (binlik ayracı nokta, ondalık virgül).
                    return f"{value:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")

                toplam_uretim = sum(s.production_kwh for s in settlements)
                toplam_tuketim = sum(s.consumption_kwh for s in settlements)
                toplam_mahsup = sum(s.settled_kwh for s in settlements)
                toplam_cekis = sum(s.grid_import_kwh for s in settlements)
                toplam_satis = sum(s.grid_export_kwh for s in settlements)

                stage_summary = (
                    f"{ay_str} ayına ait aylık mahsuplaşma raporu otomatik olarak hazırlanmıştır.\n\n"
                    f"Toplam Üretim: {_fmt_kwh(toplam_uretim)} kWh\n"
                    f"Toplam Tüketim: {_fmt_kwh(toplam_tuketim)} kWh\n"
                    f"Toplam Mahsup: {_fmt_kwh(toplam_mahsup)} kWh\n"
                    f"Şebekeden Çekiş: {_fmt_kwh(toplam_cekis)} kWh\n"
                    f"Fazla Satış: {_fmt_kwh(toplam_satis)} kWh"
                )

                # Neden: Önceki ay DB'de kayıtlıysa yönetici özetine karşılaştırma eklenir.
                if prev_totals:
                    prev_month_dt = month_dt.replace(day=1) - datetime.timedelta(days=1)
                    prev_ay_str = f"{AY_ADLARI[prev_month_dt.month - 1]} {prev_month_dt.year}"
                    prev_uretim = prev_totals["production_kwh"]
                    degisim = ((toplam_uretim - prev_uretim) / prev_uretim * 100) if prev_uretim else 0.0
                    yon = "artış" if degisim >= 0 else "azalış"
                    stage_summary += (
                        f"\n\nÖnceki ay ({prev_ay_str}) üretimi {_fmt_kwh(prev_uretim)} kWh idi; "
                        f"%{abs(degisim):.1f} {yon} gerçekleşti."
                    )
                notifier.notify_pipeline(
                    run_id=run_id,
                    exit_code=0,
                    duration_ms=int((datetime.datetime.now() - start_time).total_seconds() * 1000),
                    stage_summary=stage_summary,
                    event_type="SUCCESS",
                    attachment_path=str(rapor_path.absolute()),
                    force=True,
                    email_profile="monthly"
                )
            else:
                stage_summary = (
                    f"Monthly Settlement Job BAŞARISIZ oldu.\n"
                    f"Hedef Ay: {target_month}\n"
                    f"iSolar Raporu: {'İndirildi' if isolar_path else 'BAŞARISIZ'}\n"
                    f"GAOSB Raporu: {'İndirildi' if gaosb_path else 'BAŞARISIZ'}\n"
                    f"Hata Detayları: {error_msg}"
                )
                notifier.notify_pipeline(
                    run_id=run_id,
                    exit_code=1,
                    duration_ms=int((datetime.datetime.now() - start_time).total_seconds() * 1000),
                    stage_summary=stage_summary,
                    email_profile="monthly",
                )
            logger.info("5. Aşama BAŞARILI. Bildirim tamamlandı.")
        except Exception as e:
            logger.error(f"E-Posta bildirimi gönderilirken hata oluştu: {e}")

        # 7. Sonuç döndür
        is_success = (rapor_path is not None and rapor_path.exists())
        logger.info(f"Monthly Settlement Job TAMAMLANDI. Durum: {'SUCCESS' if is_success else 'FAILED'}")

        return {
            "status": "SUCCESS" if is_success else "FAILED",
            "month": target_month,
            "report_path": str(rapor_path) if rapor_path else None,
            "settlement_count": settlement_count,
            "error": error_msg if not is_success else None,
        }
