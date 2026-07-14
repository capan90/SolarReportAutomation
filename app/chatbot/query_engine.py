import re
from datetime import datetime, date, timedelta
from sqlalchemy import func
from app.database.db_session import SessionLocal
from app.database.models import SettlementDaily, SettlementMonthly, SettlementHourly, PlantStatus

class QueryEngine:

    def query(self, date_info: dict, metric_info: dict) -> dict:
        """
        date_info ve metric_info'ya göre DB'den veri çek.
        
        Returns:
        {
            "data": {...},
            "label": "...",
            "period": "..."
        }
        """
        if not date_info or not metric_info:
            return {
                "data": {},
                "label": "Bilinmeyen",
                "period": "unknown"
            }

        metrics = metric_info.get("metrics", [])
        comparison = metric_info.get("comparison")
        
        # 1. SANTRAL DURUMU
        if "plant_status" in metrics:
            data = self.get_plant_status_summary()
            return {
                "data": data,
                "label": data.get("last_check", date_info.get("label")),
                "period": "plant_status"
            }

        # 2. EN İYİ / EN KÖTÜ KARŞILAŞTIRMASI
        if comparison:
            # En çok/en az sorguları için ilk geçerli metriği seç veya production
            metric = "production"
            for m in metrics:
                if m in ["production", "consumption", "settled", "grid_import", "grid_export"]:
                    metric = m
                    break
            
            if comparison == "best":
                data = self.get_best_day(metric, months=3)
                period = "best"
            else:
                data = self.get_worst_day(metric, months=3)
                period = "worst"
                
            return {
                "data": data,
                "label": date_info.get("label", ""),
                "period": period
            }

        # 3. NORMAL TARİH/DÖNEM SORGULARI
        period_type = date_info.get("type", "day")
        data = {}

        if period_type == "day":
            date_str = date_info.get("date")
            data = self.get_daily_summary(date_str)
        elif period_type == "week":
            date_from = date_info.get("date_from")
            date_to = date_info.get("date_to")
            data = self.get_weekly_summary(date_from, date_to)
        elif period_type == "month":
            # date_from'dan yıl ve ayı çekelim (YYYY-MM-DD)
            date_from = date_info.get("date_from")
            try:
                dt = datetime.strptime(date_from, "%Y-%m-%d")
                data = self.get_monthly_summary(dt.year, dt.month)
            except Exception:
                data = {}
        elif period_type == "range":
            date_from = date_info.get("date_from")
            date_to = date_info.get("date_to")
            data = self.get_weekly_summary(date_from, date_to) # range de haftalık özet gibi aralık toplar

        return {
            "data": data,
            "label": date_info.get("label", ""),
            "period": period_type
        }

    def get_daily_summary(self, date_str: str) -> dict:
        """
        Belirli bir günün özetini getir.
        """
        db = SessionLocal()
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            row = db.query(SettlementDaily).filter(SettlementDaily.date == target_date).first()
            if row:
                return {
                    "production": row.production_kwh,
                    "consumption": row.consumption_kwh,
                    "settled": row.settled_kwh,
                    "grid_import": row.grid_import_kwh,
                    "grid_export": row.grid_export_kwh
                }
            
            # SettlementDaily'de yoksa SettlementHourly'den topla
            hourly_rows = db.query(SettlementHourly).filter(SettlementHourly.date == target_date).all()
            if hourly_rows:
                return {
                    "production": sum(r.production_kwh or 0 for r in hourly_rows),
                    "consumption": sum(r.consumption_kwh or 0 for r in hourly_rows),
                    "settled": sum(r.settled_kwh or 0 for r in hourly_rows),
                    "grid_import": sum(r.grid_import_kwh or 0 for r in hourly_rows),
                    "grid_export": sum(r.grid_export_kwh or 0 for r in hourly_rows)
                }
        except Exception:
            pass
        finally:
            db.close()
        return {}

    def get_weekly_summary(self, date_from: str, date_to: str) -> dict:
        """
        Belirli bir tarih aralığının toplam özetini getir.
        """
        db = SessionLocal()
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            
            # SettlementDaily'den topla
            rows = db.query(SettlementDaily).filter(SettlementDaily.date >= d_from, SettlementDaily.date <= d_to).all()
            if rows:
                return {
                    "production": sum(r.production_kwh or 0 for r in rows),
                    "consumption": sum(r.consumption_kwh or 0 for r in rows),
                    "settled": sum(r.settled_kwh or 0 for r in rows),
                    "grid_import": sum(r.grid_import_kwh or 0 for r in rows),
                    "grid_export": sum(r.grid_export_kwh or 0 for r in rows)
                }
        except Exception:
            pass
        finally:
            db.close()
        return {}

    def get_monthly_summary(self, year: int, month: int) -> dict:
        """
        Belirli bir ayın özetini getir.
        """
        db = SessionLocal()
        try:
            # 1. SettlementMonthly'yi kontrol et
            row = db.query(SettlementMonthly).filter(SettlementMonthly.year == year, SettlementMonthly.month == month).first()
            if row:
                return {
                    "production": row.production_kwh,
                    "consumption": row.consumption_kwh,
                    "settled": row.settled_kwh,
                    "grid_import": row.grid_import_kwh,
                    "grid_export": row.grid_export_kwh
                }
            
            # 2. Yoksa SettlementDaily'den o aya ait günleri topla
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)
                
            rows = db.query(SettlementDaily).filter(SettlementDaily.date >= start_date, SettlementDaily.date <= end_date).all()
            if rows:
                return {
                    "production": sum(r.production_kwh or 0 for r in rows),
                    "consumption": sum(r.consumption_kwh or 0 for r in rows),
                    "settled": sum(r.settled_kwh or 0 for r in rows),
                    "grid_import": sum(r.grid_import_kwh or 0 for r in rows),
                    "grid_export": sum(r.grid_export_kwh or 0 for r in rows)
                }
        except Exception:
            pass
        finally:
            db.close()
        return {}

    def get_best_day(self, metric: str, months: int = 3) -> dict:
        """
        Son X ayın en yüksek metrik değerli gününü getir.
        """
        db = SessionLocal()
        try:
            start_date = date.today() - timedelta(days=months * 30)
            col_map = {
                "production": SettlementDaily.production_kwh,
                "consumption": SettlementDaily.consumption_kwh,
                "settled": SettlementDaily.settled_kwh,
                "grid_import": SettlementDaily.grid_import_kwh,
                "grid_export": SettlementDaily.grid_export_kwh
            }
            col = col_map.get(metric, SettlementDaily.production_kwh)
            
            row = db.query(SettlementDaily).filter(SettlementDaily.date >= start_date).order_by(col.desc()).first()
            if row:
                val = getattr(row, metric + "_kwh" if not metric.endswith("_kwh") else metric)
                # Gün ismini ekleyelim
                days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
                day_name = days[row.date.weekday()]
                return {
                    "date": row.date.isoformat(),
                    "day_name": day_name,
                    "value": val,
                    "metric": metric
                }
        except Exception:
            pass
        finally:
            db.close()
        return {}

    def get_worst_day(self, metric: str, months: int = 3) -> dict:
        """
        Son X ayın en düşük metrik değerli gününü getir.
        """
        db = SessionLocal()
        try:
            start_date = date.today() - timedelta(days=months * 30)
            col_map = {
                "production": SettlementDaily.production_kwh,
                "consumption": SettlementDaily.consumption_kwh,
                "settled": SettlementDaily.settled_kwh,
                "grid_import": SettlementDaily.grid_import_kwh,
                "grid_export": SettlementDaily.grid_export_kwh
            }
            col = col_map.get(metric, SettlementDaily.production_kwh)
            
            # Değeri 0'dan büyük olanları getirmek mantıklı olabilir (veri eksikliği veya çalışmama durumu hariç)
            row = db.query(SettlementDaily).filter(SettlementDaily.date >= start_date, col > 0).order_by(col.asc()).first()
            if row:
                val = getattr(row, metric + "_kwh" if not metric.endswith("_kwh") else metric)
                days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
                day_name = days[row.date.weekday()]
                return {
                    "date": row.date.isoformat(),
                    "day_name": day_name,
                    "value": val,
                    "metric": metric
                }
        except Exception:
            pass
        finally:
            db.close()
        return {}

    def get_plant_status_summary(self) -> dict:
        """
        Santrallerin genel durumunu ve son kontrol vaktini getir.
        """
        import re
        def clean_name(name):
            match = re.search(r'ERDEMSOFT[- _]GES[_-](\d+)', name)
            if match:
                return f"ERDEMSOFT-GES-{match.group(1)}"
            return name.strip()

        db = SessionLocal()
        try:
            # En son güncellenen kayıtları alalım
            records = db.query(PlantStatus).all()
            
            # Temizle ve grupla (en güncelini seçerek)
            latest_by_cleaned_name = {}
            for r in records:
                cleaned = clean_name(r.plant_name)
                existing = latest_by_cleaned_name.get(cleaned)
                if not existing or (r.timestamp and existing.timestamp and r.timestamp > existing.timestamp):
                    latest_by_cleaned_name[cleaned] = r
            
            plants = []
            anomaly_count = 0
            last_check_dt = None
            
            for name in sorted(latest_by_cleaned_name.keys()):
                r = latest_by_cleaned_name[name]
                status_tr = "Bilinmiyor"
                if r.status == "Normal":
                    status_tr = "Normal"
                elif r.status == "Abnormal":
                    status_tr = "HATA"
                elif r.status == "Offline":
                    status_tr = "BAĞLANTI YOK"

                plants.append({
                    "name": name,
                    "status": status_tr,
                    "last_checked": r.timestamp.strftime("%H:%M") if r.timestamp else "-"
                })
                if r.status != "Normal":
                    anomaly_count += 1
                if r.timestamp:
                    if last_check_dt is None or r.timestamp > last_check_dt:
                        last_check_dt = r.timestamp
            
            last_check_str = last_check_dt.strftime("%d.%m.%Y %H:%M") if last_check_dt else "-"
            return {
                "plants": plants,
                "last_check": last_check_str,
                "anomaly_count": anomaly_count
            }
        except Exception:
            pass
        finally:
            db.close()
        return {
            "plants": [],
            "last_check": "-",
            "anomaly_count": 0
        }
