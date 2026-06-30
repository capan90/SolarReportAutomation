from datetime import timedelta, datetime
from typing import List, Dict, Optional
from collections import defaultdict

from app.analytics.repository import AnalyticsRepository
from app.analytics.dto import (
    AnalyticsOverviewDto,
    DailyProductionSummaryDto,
    WeeklyProductionSummaryDto,
    MonthlyProductionSummaryDto,
    MissingDayDto,
    ProductionTrendDto
)
from app.core.logger import setup_logger

logger = setup_logger("AnalyticsService")

class AnalyticsService:
    """
    Neden: Repository katmanından gelen ham üretim verilerini işleyip
    günlük/haftalık/aylık bazda analiz etmek, eksik gün tespiti (Missing Day) yapmak 
    ve son 7/30 gün trendlerini hesaplamak (SOLID - SRP).
    """
    def __init__(self, repository: Optional[AnalyticsRepository] = None):
        self.repository = repository or AnalyticsRepository()

    def get_overview(self) -> AnalyticsOverviewDto:
        generations = self.repository.get_all_generations_ordered()
        if not generations:
            return AnalyticsOverviewDto(0.0, 0.0, None, 0.0, None, 0.0, 0)

        total_yield = 0.0
        daily_sums = defaultdict(float)
        
        for g in generations:
            val = float(g.yield_today_kwh)
            total_yield += val
            daily_sums[g.date] += val

        # Günlük ortalamayı hesapla
        unique_days_count = len(daily_sums)
        avg_daily = total_yield / unique_days_count if unique_days_count > 0 else 0.0

        # En yüksek ve en düşük üretim günlerini tespit et
        peak_day = max(daily_sums, key=daily_sums.get)
        peak_val = daily_sums[peak_day]
        lowest_day = min(daily_sums, key=daily_sums.get)
        lowest_val = daily_sums[lowest_day]

        # Eksik gün adedi
        missing_days = self.get_missing_days()

        return AnalyticsOverviewDto(
            total_yield_kwh=round(total_yield, 2),
            avg_daily_yield_kwh=round(avg_daily, 2),
            peak_production_day=peak_day.isoformat(),
            peak_production_kwh=round(peak_val, 2),
            lowest_production_day=lowest_day.isoformat(),
            lowest_production_kwh=round(lowest_val, 2),
            missing_days_count=len(missing_days)
        )

    def get_daily_summary(self) -> List[DailyProductionSummaryDto]:
        generations = self.repository.get_all_generations_ordered()
        return [
            DailyProductionSummaryDto(
                date=g.date.isoformat(),
                yield_kwh=float(g.yield_today_kwh),
                co2_reduction_kg=float(g.co2_reduction_kg),
                revenue=float(g.revenue_today) if g.revenue_today is not None else 0.0,
                plant_name=g.plant.name
            )
            for g in generations
        ]

    def get_weekly_summary(self) -> List[WeeklyProductionSummaryDto]:
        generations = self.repository.get_all_generations_ordered()
        # Hafta numarası bazlı grupla
        weekly_data = defaultdict(float)
        weekly_plants = defaultdict(set)
        
        for g in generations:
            # ISO hafta numarası ve yılını al
            year, week_num, _ = g.date.isocalendar()
            key = (year, week_num)
            weekly_data[key] += float(g.yield_today_kwh)
            weekly_plants[key].add(g.plant_id)

        summaries = []
        for key, yield_val in weekly_data.items():
            year, week_num = key
            summaries.append(
                WeeklyProductionSummaryDto(
                    week_number=week_num,
                    year=year,
                    yield_kwh=round(yield_val, 2),
                    plant_count=len(weekly_plants[key])
                )
            )
        # Yıl ve hafta sırasına göre sırala
        summaries.sort(key=lambda w: (w.year, w.week_number))
        return summaries

    def get_monthly_summary(self) -> List[MonthlyProductionSummaryDto]:
        generations = self.repository.get_all_generations_ordered()
        monthly_data = defaultdict(float)
        monthly_plants = defaultdict(set)

        for g in generations:
            key = g.date.strftime("%Y-%m")
            monthly_data[key] += float(g.yield_today_kwh)
            monthly_plants[key].add(g.plant_id)

        summaries = []
        for key, yield_val in monthly_data.items():
            summaries.append(
                MonthlyProductionSummaryDto(
                    year_month=key,
                    yield_kwh=round(yield_val, 2),
                    plant_count=len(monthly_plants[key])
                )
            )
        summaries.sort(key=lambda m: m.year_month)
        return summaries

    def get_missing_days(self) -> List[MissingDayDto]:
        """
        Neden: Her tesis için veritabanındaki minimum ve maksimum tarihler arasındaki 
        tüm günleri tarayarak kaydı olmayan (eksik) günleri tespit etmek.
        """
        plants = self.repository.get_all_plants()
        generations = self.repository.get_all_generations_ordered()
        if not plants or not generations:
            return []

        # Tesis bazında girilmiş tarihleri set olarak çıkar
        plant_dates = defaultdict(set)
        for g in generations:
            plant_dates[g.plant_id].add(g.date)

        # Genel min ve max tarih aralığını bul
        all_dates = [g.date for g in generations]
        min_date = min(all_dates)
        max_date = max(all_dates)
        
        missing_days = []
        
        # Her tesis için gün gün tara
        for plant in plants:
            current_date = min_date
            while current_date <= max_date:
                if current_date not in plant_dates[plant.id]:
                    missing_days.append(
                        MissingDayDto(
                            date=current_date.isoformat(),
                            plant_name=plant.name
                        )
                    )
                current_date += timedelta(days=1)
                
        return missing_days

    def get_trend(self, limit_days: int = 30) -> ProductionTrendDto:
        """
        Neden: Son limit_days günlük üretim trendinin eğilimini 
        (Artan, Azalan veya Sabit) ve yüzdelik değişimini hesaplamak.
        """
        generations = self.repository.get_all_generations_ordered()
        if not generations:
            return ProductionTrendDto([], [], "FLAT", 0.0)

        # Günlük toplamları hesapla
        daily_sums = defaultdict(float)
        for g in generations:
            daily_sums[g.date] += float(g.yield_today_kwh)

        sorted_dates = sorted(daily_sums.keys())
        # Son N günün verisini filtrele
        trend_dates = sorted_dates[-limit_days:]
        
        labels = [d.strftime("%Y-%m-%d") for d in trend_dates]
        values = [round(daily_sums[d], 2) for d in trend_dates]

        if len(values) < 2:
            return ProductionTrendDto(labels, values, "FLAT", 0.0)

        # Basit trend yönü hesaplama (İlk yarı ortalaması vs İkinci yarı ortalaması)
        mid = len(values) // 2
        first_half_avg = sum(values[:mid]) / mid if mid > 0 else 0.0
        second_half_avg = sum(values[mid:]) / (len(values) - mid)

        change_percent = 0.0
        if first_half_avg > 0:
            change_percent = round(((second_half_avg - first_half_avg) / first_half_avg) * 100, 2)

        # Eşik değeri %2 kabul et
        if change_percent > 2.0:
            direction = "INCREASING"
        elif change_percent < -2.0:
            direction = "DECREASING"
        else:
            direction = "FLAT"

        return ProductionTrendDto(
            labels=labels,
            values=values,
            direction=direction,
            change_percent=change_percent
        )
