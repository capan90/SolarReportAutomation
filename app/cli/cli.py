import argparse
import re
from typing import List, Optional
from app.cli.cli_models import CliArgs

def str2bool(v: str) -> bool:
    """
    Neden: Komut satırından gelen 'true'/'false' metinsel ifadelerini
    boole tipine güvenli şekilde çevirmek.
    """
    if isinstance(v, bool):
         return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('True veya False değeri bekleniyor.')

def parse_args(args_list: Optional[List[str]] = None) -> CliArgs:
    """
    Neden: Komut satırı argümanlarını tanımlamak, ayrıştırmak ve doğrulamak.
    """
    parser = argparse.ArgumentParser(description="SolarReportAutomation ETL Pipeline CLI")
    
    parser.add_argument(
        "--mode",
        choices=["daily", "dry-run"],
        default="daily",
        help="Pipeline çalışma modu. dry-run modunda veritabanı yüklemesi yapılmaz."
    )
    
    parser.add_argument(
        "--date",
        default=None,
        help="Analiz edilecek hedef tarih (Format: YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--skip-download",
        type=str2bool,
        default=False,
        help="True verilirse internetten indirme atlanır, en son raw arşiv dosyası kullanılır."
    )
    
    parser.add_argument(
        "--skip-db-load",
        type=str2bool,
        default=False,
        help="True verilirse veritabanına yükleme aşaması atlanır."
    )
    
    parser.add_argument(
        "--headless",
        type=str2bool,
        default=True,
        help="True verilirse Playwright tarayıcıyı arka planda (headless) çalıştırır."
    )
    
    parser.add_argument(
        "--health",
        action="store_true",
        default=False,
        help="Sistem sağlık kontrollerini çalıştırır ve rapor üretir."
    )

    parser.add_argument(
        "--source",
        default=None,
        help="Veri kaynağı adı (isolarcloud, huawei vb.). Belirtilmezse varsayılan kaynak kullanılır."
    )

    parsed = parser.parse_args(args_list)

    # Neden: Tarih parametresinin YYYY-MM-DD formatında olmasını zorunlu kılmak (Fail-Fast)
    if parsed.date and not parsed.health:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", parsed.date):
            raise ValueError(f"Hatalı tarih formatı: '{parsed.date}'. Beklenen format: YYYY-MM-DD")
            
        # Geçerli tarih nesnesine dönüştürmeyi dene (örn: 2026-02-31 gibi hataları önlemek için)
        try:
            from datetime import datetime
            datetime.strptime(parsed.date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Geçersiz tarih değeri: '{parsed.date}'")

    return CliArgs(
        mode=parsed.mode,
        date=parsed.date,
        skip_download=parsed.skip_download,
        skip_db_load=parsed.skip_db_load,
        headless=parsed.headless,
        health=parsed.health,
        source=parsed.source
    )
