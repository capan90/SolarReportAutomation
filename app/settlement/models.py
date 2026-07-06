from dataclasses import dataclass
from typing import Optional
import pandas as pd

@dataclass
class HourlySettlement:
    timestamp: str          # ISO 8601 — YYYY-MM-DD HH:00:00
    production_kwh: float   # Saatlik üretim (tüm santraller toplamı)
    consumption_kwh: float  # Saatlik tüketim
    settled_kwh: float      # Mahsup edilen
    grid_export_kwh: float  # Fazla satış (şebekeye verilen)
    grid_import_kwh: float  # Şebekeden çekilen
