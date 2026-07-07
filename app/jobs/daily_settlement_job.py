import datetime
import time
from pathlib import Path
from typing import Optional, Dict, Any

from app.infrastructure.browser.playwright_client import PlaywrightClient
from app.extractors.isolar.extractor import IsolarExtractor
from app.sources.gaosb.extractor import GaosbExtractor
from app.settlement.engine import SettlementEngine
from app.settlement.report_writer import SettlementReportWriter
from app.notifications.notification_service import NotificationService
from app.core.logger import setup_logger
from app.core.config import settings

# Logger kurulumu
logger = setup_logger("DailySettlementJob")

class DailySettlementJob:
    """
    Neden: Günlük mahsuplaşma akışını (iSolar veri çekme, GAOSB veri çekme, 
    mahsuplaşma hesabı, Excel rapor üretimi ve bildirim gönderme) 
    tek bir iş (job) altında koordine eder.
    """

    def run(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Neden: Belirtilen target_date (YYYY-MM-DD) veya varsayılan olarak dün için 
        tüm mahsuplaşma adımlarını sırayla çalıştırır.
        """
        start_time = datetime.datetime.now()

        # 1. Target date hesapla (None -> dün)
        if not target_date:
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            target_date = yesterday.strftime("%Y-%m-%d")

        logger.info(f"Daily Settlement Job BAŞLADI. Hedef Tarih: {target_date}")

        # Neden: Tarih formatının doğruluğunu teyit etmek ve klasör yapısı için nesneye dönüştürmek.
        try:
            dt = datetime.datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError as e:
            logger.error(f"Geçersiz tarih formatı (YYYY-MM-DD olmalı): {target_date}")
            return {
                "status": "FAILED",
                "date": target_date,
                "report_path": None,
                "settlement_count": 0,
                "error": f"Geçersiz tarih formatı: {e}"
            }

        # 2. output_dir: outputs/reports/YYYY-MM/ oluştur
        month_str = dt.strftime("%Y-%m")
        output_dir = Path("outputs/reports") / month_str
        output_dir.mkdir(parents=True, exist_ok=True)

        run_id = f"job-settlement-{target_date}-{int(time.time())}"
        headless = settings.headless

        isolar_path: Optional[Path] = None
        gaosb_path: Optional[Path] = None
        rapor_path: Optional[Path] = None
        settlement_count = 0
        error_msg: Optional[str] = None

        # 3. iSolar Curve indir (Best-effort)
        try:
            logger.info(f"1. Aşama: iSolar Curve indirme başlatılıyor (Tarih: {target_date})...")
            with PlaywrightClient(headless=headless) as client:
                page = client.create_page()
                extractor = IsolarExtractor(page, run_id=run_id)
                extractor.login_and_verify()
                extractor.navigate_to_curve_page()
                isolar_path = extractor.download_hourly_curve_report(date_str=target_date)
            logger.info(f"1. Aşama BAŞARILI. İndirilen dosya: {isolar_path}")
        except Exception as e:
            err_txt = f"iSolar Curve indirme aşaması başarısız: {e}"
            logger.error(err_txt)
            error_msg = err_txt

        # 4. GAOSB indir (Best-effort)
        try:
            logger.info(f"2. Aşama: GAOSB raporu indirme başlatılıyor (Tarih: {target_date})...")
            extractor = GaosbExtractor()
            # Neden: GAOSB portalı Date1==Date2 sorgusunda boş döndürüyor.
            # Bitiş tarihine +1 gün eklenerek açık aralık sorgusu yapılır.
            gaosb_date_to = (datetime.datetime.strptime(target_date, "%Y-%m-%d")
                             + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            gaosb_path = extractor.download_report(
                output_dir=output_dir,
                date_from=target_date,
                date_to=gaosb_date_to,
                headless=headless
            )
            logger.info(f"2. Aşama BAŞARILI. İndirilen dosya: {gaosb_path}")
        except Exception as e:
            err_txt = f"GAOSB raporu indirme aşaması başarısız: {e}"
            logger.error(err_txt)
            if error_msg:
                error_msg += f" | {err_txt}"
            else:
                error_msg = err_txt

        # 5. Settlement hesapla ve Excel rapor üret (Best-effort)
        try:
            if not isolar_path or not gaosb_path:
                raise ValueError("iSolar veya GAOSB dosya yollarından en az biri eksik olduğu için mahsuplaşma hesaplanamaz.")

            logger.info("3. Aşama: Mahsuplaşma hesabı başlatılıyor...")
            engine = SettlementEngine()
            settlements = engine.calculate(isolar_path, gaosb_path)
            settlement_count = len(settlements)
            logger.info(f"Mahsuplaşma hesabı tamamlandı. Kayıt sayısı: {settlement_count}")

            logger.info("4. Aşama: Excel raporu yazılıyor...")
            formatted_date = dt.strftime("%Y%m%d")
            rapor_path = output_dir / f"mahsup_{formatted_date}.xlsx"

            # Neden: GES bazlı üretim kırılımı sayfası için iSolar DataFrame'i geçilir.
            isolar_df = engine.load_isolar_curve(isolar_path)
            writer = SettlementReportWriter()
            writer.write(settlements, rapor_path, isolar_df=isolar_df)
            logger.info(f"4. Aşama BAŞARILI. Rapor üretildi: {rapor_path}")
        except Exception as e:
            err_txt = f"Mahsuplaşma veya rapor yazma aşaması başarısız: {e}"
            logger.error(err_txt)
            if error_msg:
                error_msg += f" | {err_txt}"
            else:
                error_msg = err_txt

        # 6. E-Posta bildirimi gönder (Best-effort)
        try:
            logger.info("5. Aşama: E-Posta bildirimi gönderiliyor...")
            notifier = NotificationService()
            
            if rapor_path and rapor_path.exists():
                exit_code = 0
                stage_summary = (
                    f"Daily Settlement Job başarıyla tamamlandı.\n"
                    f"Tarih: {target_date} | Mahsup: {settlement_count} saat | Rapor: {rapor_path.name}\n"
                    f"Rapor Yolu: {rapor_path.absolute()}"
                )
                # Neden: Başarılı koşuda mahsup Excel'i ek olarak gönderilir;
                # SUCCESS politikası kapalı olduğundan force=True ile bypass edilir.
                notifier.notify_pipeline(
                    run_id=run_id,
                    exit_code=exit_code,
                    duration_ms=int((datetime.datetime.now() - start_time).total_seconds() * 1000),
                    stage_summary=stage_summary,
                    event_type="SUCCESS",
                    attachment_path=str(rapor_path.absolute()),
                    force=True
                )
            else:
                exit_code = 1
                stage_summary = (
                    f"Daily Settlement Job BAŞARISIZ oldu.\n"
                    f"Hedef Tarih: {target_date}\n"
                    f"iSolar Raporu: {'İndirildi' if isolar_path else 'BAŞARISIZ'}\n"
                    f"GAOSB Raporu: {'İndirildi' if gaosb_path else 'BAŞARISIZ'}\n"
                    f"Hata Detayları: {error_msg}"
                )
                notifier.notify_pipeline(
                    run_id=run_id,
                    exit_code=exit_code,
                    duration_ms=int((datetime.datetime.now() - start_time).total_seconds() * 1000),
                    stage_summary=stage_summary
                )
            logger.info("5. Aşama BAŞARILI. Bildirim tamamlandı.")
        except Exception as e:
            logger.error(f"E-Posta bildirimi gönderilirken hata oluştu: {e}")

        # 7. Sonuç döndür
        is_success = (rapor_path is not None and rapor_path.exists())
        logger.info(f"Daily Settlement Job TAMAMLANDI. Durum: {'SUCCESS' if is_success else 'FAILED'}")
        
        return {
            "status": "SUCCESS" if is_success else "FAILED",
            "date": target_date,
            "report_path": str(rapor_path) if rapor_path else None,
            "settlement_count": settlement_count,
            "error": error_msg if not is_success else None
        }
