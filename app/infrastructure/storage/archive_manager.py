import shutil
from datetime import datetime
from pathlib import Path
from app.core.config import settings
from app.core.logger import setup_logger
from app.core.exceptions import IsolarInvalidDownloadedFileError, IsolarArchiveError

logger = setup_logger("ArchiveManager")

class ArchiveManager:
    """
    Neden: İndirilen ham verilerin (raw data) kaybolmaması, üzerine yazılmaması ve
    sistemli şekilde arşivlenerek izlenebilirlik sağlanması.
    """
    def __init__(self):
        # Neden: Çalışma dizinine göre mutlak yolları (absolute path) belirlemek
        self.archive_dir = settings.download_directory

    def ensure_archive_directory(self) -> None:
        """
        Neden: Arşiv dizininin çalışma zamanında var olduğundan emin olmak.
        """
        if not self.archive_dir.exists():
            logger.info(f"Arşiv dizini oluşturuluyor: {self.archive_dir}")
            self.archive_dir.mkdir(parents=True, exist_ok=True)

    def archive_raw_file(self, temp_file_path: Path) -> Path:
        """
        Neden: Geçici indirme dizinindeki dosyayı alıp, Level 1 (File) doğrulamasını yaparak
        mikrosaniye çözünürlüklü benzersiz adla raw archive klasörüne taşımak.
        """
        self.ensure_archive_directory()

        # 1. Dosya varlık kontrolü
        if not temp_file_path.exists():
            raise IsolarInvalidDownloadedFileError(f"Arşivlenecek geçici dosya bulunamadı: {temp_file_path}")

        # 2. Dosya boyutu kontrolü
        file_size = temp_file_path.stat().st_size
        if file_size == 0:
            raise IsolarInvalidDownloadedFileError(f"Geçersiz dosya: {temp_file_path} boyutu 0 byte.")

        # 3. Dosya uzantısı kontrolü (xlsx veya xls)
        suffix = temp_file_path.suffix.lower()
        if suffix not in [".xlsx", ".xls"]:
            raise IsolarInvalidDownloadedFileError(
                f"Geçersiz dosya uzantısı: {suffix}. Sadece .xlsx veya .xls dosyaları arşivlenebilir."
            )

        # 4. Benzersiz dosya adı üretme (raw_isolar_YYYYMMDD_HHMMSS_ffffff.xlsx)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        new_filename = f"raw_isolar_{timestamp}{suffix}"
        destination_path = self.archive_dir / new_filename

        # 5. Dosyayı taşıma işlemi
        try:
            logger.info(f"Dosya arşivleniyor: {temp_file_path.name} -> {new_filename}")
            shutil.move(str(temp_file_path), str(destination_path))
        except Exception as e:
            raise IsolarArchiveError(f"Dosya arşiv dizinine taşınırken hata oluştu: {e}")
        
        logger.info(f"Dosya başarıyla raw archive dizinine kaydedildi: {destination_path}")
        return destination_path
