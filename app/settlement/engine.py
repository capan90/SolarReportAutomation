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
        Neden: GAOSB Excel dosyasını okur, Okunan Değer sütunundan
        delta hesaplar, çarpan uygular → saatlik tüketim.
        
        Döndürür: timestamp | consumption_kwh sütunlu DataFrame
        
        Notlar:
        - Dosya OLE2 formatı — xlrd kullan
        - Tarih sütunu Excel serial number — pd.to_datetime ile çevir
        - Okunan Değer kümülatif → delta hesapla
        - delta × 26.400 = consumption_kwh
        - Negatif delta = 0
        - Saatlik gruplama: 15dk varsa resample('h').last() ile saat başına al
        """
        # Neden: GAOSB dosyaları eski Excel (OLE2) biçiminde olduğu için öncelikle xlrd tercih edilir.
        try:
            df = pd.read_excel(file_path, engine='xlrd')
        except Exception:
            df = pd.read_excel(file_path, engine='openpyxl')

        # Neden: Boş veya geçersiz satırları temizleriz.
        df = df.dropna(subset=['Tarih', 'Okunan Değer'])

        # Neden: Excel seri numarası biçimindeki tarihleri datetime formatına dönüştürürüz.
        if pd.api.types.is_numeric_dtype(df['Tarih']):
            df['Tarih'] = pd.to_datetime(df['Tarih'], unit='D', origin='1899-12-30')
        else:
            df['Tarih'] = pd.to_datetime(df['Tarih'])

        # Neden: Değer kolonlarını string ise temizleyip float tipine dönüştürürüz.
        df['Okunan Değer'] = df['Okunan Değer'].astype(str).str.replace(' ', '').str.replace(',', '.')
        df['Okunan Değer'] = pd.to_numeric(df['Okunan Değer'], errors='coerce').fillna(0.0)

        # Neden: Çarpan değerini okuruz, kolonda yoksa 26400 varsayılan değerini atarız.
        if 'Çarpan' in df.columns:
            df['Çarpan'] = df['Çarpan'].astype(str).str.replace(' ', '').str.replace(',', '.')
            df['Çarpan'] = pd.to_numeric(df['Çarpan'], errors='coerce').fillna(26400.0)
        else:
            df['Çarpan'] = 26400.0

        # Neden: Kronolojik sıralama yapar ve Tarih alanını indeks haline getiririz.
        df = df.sort_values('Tarih')
        df_indexed = df.set_index('Tarih')

        # Neden: 15'er dakikalık veri ihtimaline karşı veriyi saatlik resample edip son okunan kümülatif değeri alırız.
        df_hourly = df_indexed.resample('h').last()
        df_hourly['Okunan Değer'] = df_hourly['Okunan Değer'].ffill()
        df_hourly['Çarpan'] = df_hourly['Çarpan'].ffill().fillna(26400.0)

        # Neden: Kümülatif endeks okumasından saatlik delta hesaplarız.
        df_hourly['delta'] = df_hourly['Okunan Değer'].diff().fillna(0.0)
        df_hourly.loc[df_hourly['delta'] < 0, 'delta'] = 0.0

        # Neden: Delta ile çarpan değerini çarparak saatlik tüketim (consumption_kwh) değerini elde ederiz.
        df_hourly['consumption_kwh'] = df_hourly['delta'] * df_hourly['Çarpan']

        # Neden: Timestamp alanını standart formata dönüştürerek temiz dataframe oluştururuz.
        df_hourly = df_hourly.reset_index()
        df_hourly['timestamp'] = df_hourly['Tarih'].dt.strftime("%Y-%m-%d %H:00:00")
        result = df_hourly[['timestamp', 'consumption_kwh']]

        return result

    def calculate(
        self,
        isolar_file: Path,
        gaosb_file: Path
    ) -> List[HourlySettlement]:
        """
        Neden: İki kaynağı timestamp üzerinden birleştirip
        saatlik mahsup hesaplar.
        
        Adımlar:
        1. load_isolar_curve → production df
        2. load_gaosb → consumption df
        3. merge on timestamp (inner join)
        4. Her satır için HourlySettlement hesapla
        5. Liste döndür
        """
        # Neden: Üretim ve tüketim verilerini ilgili yükleme metotları ile çekeriz.
        df_prod = self.load_isolar_curve(isolar_file)
        df_cons = self.load_gaosb(gaosb_file)
        # Neden: Tarih farkını görmezden gelerek sadece SAAT kısmı üzerinden join yaparız.
        df_prod['hour'] = pd.to_datetime(df_prod['timestamp']).dt.strftime("%H")
        df_cons['hour'] = pd.to_datetime(df_cons['timestamp']).dt.strftime("%H")

        # Neden: 'hour' kolonu üzerinden birleştiririz. Böylece farklı günlerin verisi olsa da saatler eşleşir.
        merged = pd.merge(df_prod, df_cons, on='hour', suffixes=('_prod', '_cons'))

        # Neden: Birleştirilmiş veri için timestamp olarak tüketim verisinin asıl tarih/saat bilgisini koruruz.
        merged['timestamp'] = merged['timestamp_cons']

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
