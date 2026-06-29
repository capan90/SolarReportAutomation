import re
from datetime import datetime, date
from typing import Any, Tuple, Optional

def trim_text(val: Any) -> Optional[str]:
    """
    Neden: Metin değerlerinin başındaki ve sonundaki boşlukları temizlemek.
    """
    if val is None:
        return None
    return str(val).strip()

def parse_float(val: Any) -> Optional[float]:
    """
    Neden: Sayısal değerleri güvenli bir şekilde float tipine dönüştürmek.
    """
    if val is None or str(val).strip() == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    # Temizleme
    val_str = str(val).replace(",", "").replace(" ", "").strip()
    try:
        return float(val_str)
    except ValueError:
        raise ValueError(f"Sayısal değere dönüştürülemedi: '{val}'")

def parse_date(val: Any) -> Optional[date]:
    """
    Neden: Excel hücresinden gelen tarihi (datetime, date veya string formatını)
    standart date tipine dönüştürmek.
    """
    if val is None or str(val).strip() == "":
        return None
    if isinstance(val, (datetime, date)):
        return val.date() if isinstance(val, datetime) else val
    
    val_str = str(val).strip()
    # YYYY-MM-DD kontrolü
    match = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})", val_str)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
            
    # Diğer standart formatlar
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue
            
    raise ValueError(f"Tarih formatı çözülemedi: '{val}'")

def parse_revenue_currency(val: Any) -> Tuple[Optional[float], Optional[str]]:
    """
    Neden: '23555.70(TRY)' formatındaki parasal değeri değer ve para birimi olarak ayırmak.
    """
    if val is None or str(val).strip() == "":
        return None, None
    if isinstance(val, (int, float)):
        return float(val), None
        
    val_str = str(val).strip()
    # Regex ile ayıkla
    match = re.match(r"([\d\.\,\s]+)\(([^)]+)\)", val_str)
    if match:
        num_part = match.group(1).replace(",", "").replace(" ", "").strip()
        currency_part = match.group(2).strip()
        try:
            return float(num_part), currency_part
        except ValueError:
            raise ValueError(f"Gelir değeri sayısal kısma dönüştürülemedi: '{num_part}'")
            
    # Düz sayı formatı
    try:
        return float(val_str.replace(",", "").replace(" ", "")), None
    except ValueError:
        raise ValueError(f"Gelir formatı çözülemedi: '{val}'")

def normalize_kwh(val: Any) -> Optional[float]:
    """
    Neden: Üretim birimini standart kWh cinsinden float'a çevirmek.
    """
    return parse_float(val)

def normalize_kwp(val: Any) -> Optional[float]:
    """
    Neden: Kurulu güç birimini standart kWp cinsinden float'a çevirmek.
    """
    return parse_float(val)

def identity(val: Any) -> Any:
    """
    Neden: Herhangi bir dönüşüm uygulamadan değeri olduğu gibi bırakmak.
    """
    return val
