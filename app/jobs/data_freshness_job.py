"""
Neden: 2026-08-03 09:00 koşusu iSolar tarayıcısının kapanışında asıldı. Süreç YAŞADIĞI
için istisna oluşmadı; S2'de eklenen sessiz-ölüm uyarısı (system_alert) main.py'nin
except dallarından tetiklendiğinden devreye giremedi ve 2 Ağustos verisi kimsenin haberi
olmadan eksik kaldı. 1 Ağustos'ta en azından hata maili gelmişti — bu sefer hiçbir sinyal
çıkmadı.

Mevcut alarmların tamamı bir MEKANİZMAYA bağlı (istisna yakalandı mı, exit kodu ne oldu).
Bu kontrol SONUCA bakar: dün için veri var mı, tam mı? Böylece tek yerden yakalanır —
asılma, Task Scheduler'ın IgnoreNew ile atladığı tetik, oturum kapanmasıyla ölen süreç,
çökme ve portal arızası.

Kasıtlı sınırlar:
- Tarayıcı KULLANMAZ, yalnızca DB okur → kendisi asılamaz.
- ETL'den AYRI zamanlanmış görevdir → asılı bir ETL instance'ı (IgnoreNew) bunu bloklamaz.
- Değer makullüğü (bozuk/şişmiş kWh değerleri) kapsam DIŞI; o ayrı bir araştırma maddesi.
  Buradaki soru yalnızca "veri var mı ve tam mı".
"""
import datetime
from dataclasses import dataclass
from typing import Callable, Optional

from app.core.logger import setup_logger
from app.database.settlement_repository import SettlementRepository
from app.notifications.system_alert import send_job_failure_alert

logger = setup_logger("DataFreshnessJob")

JOB_NAME = "Günlük Veri Kontrolü"

# Neden: Türkiye 2016'dan beri sabit UTC+3 kullanıyor, yaz saati uygulaması yok — bu yüzden
# tam gün her zaman 24 saattir. Yaz saati geri gelirse bu sabit yeniden değerlendirilmeli
# (geçiş günlerinde 23/25 saat olur ve kontrol yanlış pozitif üretir).
EXPECTED_HOURS = 24

LEVEL_OK = "OK"
LEVEL_PARTIAL = "PARTIAL"
LEVEL_MISSING = "MISSING"


@dataclass(frozen=True)
class FreshnessResult:
    """Kontrolün sonucu; main.py çıkış kodunu buradan türetir."""
    level: str
    target_date: str
    hours: int
    message: str

    @property
    def is_problem(self) -> bool:
        return self.level != LEVEL_OK


class DataFreshnessJob:
    """
    Neden: Günlük mahsuplaşma verisinin gerçekten yazılıp yazılmadığını ETL'den bağımsız
    olarak doğrular ve eksikse uyarı maili atar.
    """

    def __init__(self, repository=None, alert_sender: Optional[Callable] = None):
        # Neden: Testlerde gerçek DB ve SMTP'ye çıkmadan üç seviyenin de sınanabilmesi için
        # bağımlılıklar dışarıdan verilebilir (üretimde varsayılanlar kullanılır).
        self._repository = repository
        self._alert_sender = alert_sender or send_job_failure_alert

    @property
    def repository(self):
        # Neden: SettlementRepository kurulumunda create_tables() çağırıyor; testlerde sahte
        # repository verildiyse gerçek DB'ye hiç dokunulmasın diye geç oluşturulur.
        if self._repository is None:
            self._repository = SettlementRepository()
        return self._repository

    def run(self, target_date: Optional[str] = None) -> FreshnessResult:
        """
        Belirtilen gün (yoksa dün) için settlement verisinin varlığını ve tamlığını
        kontrol eder; sorun varsa uyarı maili gönderir.
        """
        if not target_date:
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            target_date = yesterday.strftime("%Y-%m-%d")

        logger.info("Veri kontrolü BAŞLADI. Hedef Tarih: %s", target_date)

        has_daily = self.repository.has_daily_data(target_date)
        hours = self.repository.count_hourly(target_date)

        result = self._evaluate(target_date, has_daily, hours)

        if result.is_problem:
            logger.error("Veri kontrolü SORUNLU (%s): %s", result.level, result.message)
            self._send_alert(result)
        else:
            # Neden: Normal gün mail üretmemeli; ama koşunun gerçekleştiği log'dan
            # görülebilmeli — kontrolün kendisi sessizce ölürse bu satırın yokluğu ipucudur.
            logger.info("Veri kontrolü TAMAM: %s", result.message)

        return result

    def _evaluate(self, target_date: str, has_daily: bool, hours: int) -> FreshnessResult:
        """Üç seviyeli karar; ayrı metot olmasının nedeni testlerde DB'siz sınanabilmesi."""
        if not has_daily:
            return FreshnessResult(
                level=LEVEL_MISSING,
                target_date=target_date,
                hours=hours,
                message=(
                    f"{target_date} için settlement_daily satırı YOK "
                    f"(settlement_hourly'de {hours} saat var). Günlük mahsuplaşma işi "
                    f"hiç koşmamış, asılmış veya veri yazmadan başarısız olmuş olabilir."
                ),
            )
        if hours < EXPECTED_HOURS:
            return FreshnessResult(
                level=LEVEL_PARTIAL,
                target_date=target_date,
                hours=hours,
                message=(
                    f"{target_date} günü EKSİK: settlement_daily satırı var ama "
                    f"settlement_hourly {hours}/{EXPECTED_HOURS} saat içeriyor. "
                    f"Günlük toplamlar eksik saatlerle hesaplanmış olabilir."
                ),
            )
        return FreshnessResult(
            level=LEVEL_OK,
            target_date=target_date,
            hours=hours,
            message=f"{target_date} günü tam ({hours}/{EXPECTED_HOURS} saat).",
        )

    def _send_alert(self, result: FreshnessResult) -> None:
        """
        Neden: Mevcut system_alert yolu yeniden kullanılır (SMTP_TO_SYSTEM alıcısı, son 40
        log satırı ekli). Ama varsayılan gövde metni "yakalanmamış istisna" diyor — burada
        neden o değil, o yüzden başlık/açıklama açıkça geçilir.
        """
        if result.level == LEVEL_MISSING:
            headline = f"{result.target_date} günü için mahsuplaşma verisi YOK."
            explanation = (
                "Bu kontrol günlük ETL'den bağımsız koşar ve yalnızca sonuca bakar: "
                "dünün verisi veritabanına yazılmamış. İş hiç başlamamış, asılmış veya "
                "veri yazmadan düşmüş olabilir — logların son satırları aşağıdadır."
            )
        else:
            headline = f"{result.target_date} günü eksik veriyle kapanmış."
            explanation = (
                "Günün satırı var ancak saatlerin tamamı yazılmamış. Günlük toplamlar "
                "eksik saatlerle hesaplandığı için rapor ve faturalama değerleri "
                "olduğundan düşük olabilir."
            )
        self._alert_sender(JOB_NAME, result.message, headline=headline, explanation=explanation)
