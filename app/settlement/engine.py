import re
from pathlib import Path
from typing import Optional, List
import pandas as pd
from app.settlement.models import HourlySettlement

class SettlementEngine:
    """
    Neden: iSolar ve GAOSB verilerini kullanarak saatlik mahsuplaşma (settlement) hesabı yapar.
    """

    def load_isolar_curve(self, file_path: Path) -> pd.DataFrame:
        """
        Neden: iSolar Curve Excel dosyasını okur, santral sütunlarını
        toplar, kümülatif değerden delta (saatlik üretim) hesaplar.
        
        Döndürür: timestamp | production_kwh sütunlu DataFrame
        
        Notlar:
        - Dosya .xlsx uzantılı ama OLE2 olabilir, openpyxl ve xlrd dene
        - İlk satır etiket (Curve_...), ikinci satır başlık
        - Time sütunu: YYYY-MM-DD HH:MM:SS
        - Değerler string olabilir, float'a çevir
        - Tüm GES sütunlarını topla → toplam üretim
        - Delta: değer[t] - değer[t-1], ilk satır 0
        - Negatif delta = 0 (gece sıfırlanma)
        """
        # Neden: Dosya uzantısı xlsx olsa da OLE2 formatında olabileceğinden hem openpyxl hem de xlrd ile okumayı deneriz.
        try:
            df = pd.read_excel(file_path, header=1, engine='openpyxl')
        except Exception:
            df = pd.read_excel(file_path, header=1, engine='xlrd')

        # Neden: Boş satırları veya Time kolonu boş olan satırları filtreleriz.
        df = df.dropna(subset=['Time'])

        # Neden: Tarih alanını datetime tipine dönüştürürüz.
        df['Time'] = pd.to_datetime(df['Time'])

        # Neden: Time kolonu haricindeki tüm GES/üretim sütunlarını buluruz.
        plant_cols = [col for col in df.columns if col != 'Time' and not str(col).startswith('Unnamed')]

        # Neden: Değerleri string ise temizleyip float tipine dönüştürürüz.
        for col in plant_cols:
            df[col] = df[col].astype(str).str.replace(' ', '').str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        # Neden: Tüm GES santrallerinin saatlik kümülatif değerlerini tek bir üretim serisinde toplarız.
        df['production_cumulative'] = df[plant_cols].sum(axis=1)

        # Neden: Doğru delta hesabı için verileri zamana göre sıralarız.
        df = df.sort_values('Time')

        # Neden: Kümülatif üretim değerlerinden saatlik üretim deltalarını hesaplarız.
        df['production_kwh'] = df['production_cumulative'].diff().fillna(0.0)

        # Neden: Gece sıfırlanması veya sayaç resetlenmesi gibi durumlarda negatif deltayı 0.0 yaparız.
        df.loc[df['production_kwh'] < 0, 'production_kwh'] = 0.0

        # Neden: Çıktıyı istenen formata (YYYY-MM-DD HH:00:00) getirip gruplarız.
        df['timestamp'] = df['Time'].dt.strftime("%Y-%m-%d %H:00:00")
        result = df[['timestamp', 'production_kwh']].groupby('timestamp', as_index=False).sum()

        return result

    def load_gaosb(self, file_path: Path) -> pd.DataFrame:
        """
        Neden: GAOSB Excel dosyasını okur ve Endeks değeri sütununu (index 5)
        doğrudan tüketim (consumption_kwh) olarak alır (herhangi bir fark hesaplamadan).
        
        Döndürür: timestamp | consumption_kwh sütunlu DataFrame
        """
        # 1. Önce openpyxl dene, hata alırsan xlrd kullan
        try:
            df = pd.read_excel(file_path, engine='openpyxl')
        except Exception:
            df = pd.read_excel(file_path, engine='xlrd')

        if df.empty:
            return pd.DataFrame(columns=['timestamp', 'consumption_kwh'])

        # 2. Tarih sütunu (index 0) ve Endeks değeri sütunu (index 5)
        # Neden: Sütun isimleri farklı karakter kodlamalarına sahip olabileceğinden index ile erişim daha güvenlidir.
        date_col = df.columns[0]
        val_col = df.columns[5]

        # Boş satırları filtrele
        df = df.dropna(subset=[date_col, val_col])

        # Neden: Excel seri tarih formatını (varsa) standart datetime nesnesine dönüştürmek
        import numpy as np
        dates = []
        for val in df[date_col]:
            if isinstance(val, (int, float, np.integer, np.floating)) and not isinstance(val, bool):
                from datetime import datetime, timedelta
                base_date = datetime(1899, 12, 30)
                dt_val = base_date + timedelta(days=val)
                dates.append(dt_val)
            else:
                dates.append(pd.to_datetime(val))

        df['parsed_date'] = pd.to_datetime(dates)

        # 3. Endeks değeri sütununu (index 5) doğrudan consumption_kwh al
        df['consumption_kwh'] = pd.to_numeric(df[val_col], errors='coerce').fillna(0.0)

        # 4. timestamp sütununu normalize et: YYYY-MM-DD HH:00:00
        df['timestamp'] = df['parsed_date'].dt.strftime("%Y-%m-%d %H:00:00")

        # 5. timestamp | consumption_kwh sütunlu DataFrame döndür
        result = df[['timestamp', 'consumption_kwh']].copy()
        
        # Neden: Aynı saate birden fazla kayıt gelirse birleştiririz
        result = result.groupby('timestamp', as_index=False).sum()

        return result

    def calculate(
        self,
        isolar_file: Path,
        gaosb_file: Path
    ) -> List[HourlySettlement]:
        """
        Neden: İki kaynağı timestamp üzerinden birebir eşleştirerek (inner join)
        saatlik mahsup hesaplar.
        """
        # Neden: Üretim ve tüketim verilerini ilgili yükleme metotları ile çekeriz.
        df_prod = self.load_isolar_curve(isolar_file)
        df_cons = self.load_gaosb(gaosb_file)

        # Neden: 'timestamp' kolonu üzerinden birebir eşleştirerek birleştiririz (inner join).
        merged = pd.merge(df_prod, df_cons, on='timestamp')

        # Neden: Birleştirilmiş verileri kronolojik olarak sıralarız.
        merged = merged.sort_values('timestamp')

        settlements: List[HourlySettlement] = []

        # Neden: Her saat dilimi için üretim, tüketim, mahsup ve şebekeye verilen/çekilen değerleri hesaplarız.
        for _, row in merged.iterrows():
            prod = float(row['production_kwh'])
            cons = float(row['consumption_kwh'])

            # Neden: Mahsup edilen miktar üretim ve tüketimden küçük veya eşit olanıdır.
            settled = min(prod, cons)

            # Neden: Şebekeye satılan miktar, üretimin tüketimden fazla olan kısmıdır.
            export_val = max(0.0, prod - cons)

            # Neden: Şebekeden çekilen miktar, tüketimin üretimden fazla olan kısmıdır.
            import_val = max(0.0, cons - prod)

            settlements.append(HourlySettlement(
                timestamp=str(row['timestamp']),
                production_kwh=prod,
                consumption_kwh=cons,
                settled_kwh=settled,
                grid_export_kwh=export_val,
                grid_import_kwh=import_val
            ))

        return settlements

    def to_dataframe(
        self, 
        settlements: List[HourlySettlement]
    ) -> pd.DataFrame:
        """Neden: Sonuçları Excel'e yazmak için DataFrame'e çevir."""
        # Neden: Dataclass nesne listesini sözlük formatına çevirip doğrudan pandas DataFrame'ine yükleriz.
        from dataclasses import asdict
        data = [asdict(s) for s in settlements]
        return pd.DataFrame(data)
