import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.sources.interface import ISourceExtractor
from app.sources.models import SourceMetadata
from app.sources.exceptions import SourceAuthenticationError
from app.sources.context import get_source_context
from app.infrastructure.browser.playwright_client import PlaywrightClient
from app.core.logger import setup_logger

logger = setup_logger("GaosbExtractor")

class GaosbExtractor(ISourceExtractor):
    """
    Neden: Gaziantep Organize Sanayi Bölgesi (GAOSB) sayaç sorgulama portalından
    Playwright aracılığıyla kimlik doğrulayıp sayaç sorgu raporunu indiren adaptör sınıfı.
    """
    source_id = "gaosb"
    display_name = "GAOSB Sayaç Sorgu"
    capabilities = ["HOURLY_CONSUMPTION", "DAILY_METER_INDEX"]

    @property
    def metadata(self) -> SourceMetadata:
        """
        Neden: ISourceExtractor arayüzü gereksinimlerini karşılamak amacıyla
        kaynak hakkında değişmez meta verileri döner.
        """
        return SourceMetadata(
            source_name="gaosb",
            vendor="Gaziantep OSB",
            version="1.0.0",
            supported_report_types=["hourly_consumption", "daily_meter_index"],
            authentication_type="credentials",
            capabilities={
                "supports_excel_export": True,
                "supports_api": False,
                "supports_scheduler": True,
                "supports_health_check": True,
                "HOURLY_CONSUMPTION": True,
                "DAILY_METER_INDEX": True
            }
        )

    def download_report(self, output_dir: Path, date_from: Optional[str] = None, date_to: Optional[str] = None, **kwargs) -> Path:
        """
        Neden: Belirtilen tarih aralığı için GAOSB portalından sayaç sorgu excel raporunu indirir.
        """
        # Parametre kontrolü ve kwargs'tan fallback okuma
        date_from = date_from or kwargs.get("date_from")
        date_to = date_to or kwargs.get("date_to")
        if not date_from or not date_to:
            logger.error("date_from veya date_to parametreleri eksik.")
            raise ValueError("date_from ve date_to parametreleri zorunludur.")

        # Yapılandırma ortam değişkenlerinden okunur
        gaosb_url = os.environ.get("GAOSB_URL", "https://elk.gaosb.org/")
        username = os.environ.get("GAOSB_USERNAME")
        password = os.environ.get("GAOSB_PASSWORD")

        if not username or not password:
            logger.error("GAOSB_USERNAME veya GAOSB_PASSWORD ortam değişkenleri eksik.")
            raise ValueError("GAOSB kimlik bilgileri eksik (GAOSB_USERNAME / GAOSB_PASSWORD).")

        # Headless tarayıcı modu çözümlenir
        headless = kwargs.get("headless")
        if headless is None:
            gaosb_headless_env = os.environ.get("GAOSB_HEADLESS")
            if gaosb_headless_env is not None:
                headless = gaosb_headless_env.lower() == "true"
            else:
                headless = True

        # Tarih formatlama yardımcı fonksiyonları (Türkçe portal için DD.MM.YYYY)
        def format_date_tr(date_str: str) -> str:
            if not date_str:
                return ""
            if "-" in date_str:
                try:
                    parts = date_str.split("-")
                    if len(parts) == 3 and len(parts[0]) == 4:  # YYYY-MM-DD
                        return f"{parts[2]}.{parts[1]}.{parts[0]}"
                except Exception:
                    pass
            return date_str

        def get_yyyymmdd(date_str: str) -> str:
            clean = date_str.replace(".", "").replace("-", "")
            if len(clean) == 8:
                if "." in date_str:  # DD.MM.YYYY
                    return clean[4:8] + clean[2:4] + clean[0:2]
                return clean  # YYYYMMDD
            return clean

        formatted_date_from = format_date_tr(date_from)
        formatted_date_to = format_date_tr(date_to)

        # Arama ve doldurma için selector listeleri
        from_selectors = [
            "#ctl00_ContentPlaceHolder1_Date1_I",
            "input[id*='Date1_I']",
            "input[id*='dtFrom']",
            "input[id*='DateFrom']",
            "input[id*='StartDate']",
            "input[name*='dtFrom']",
            "input[name*='DateFrom']",
        ]

        to_selectors = [
            "#ctl00_ContentPlaceHolder1_Date2_I",
            "input[id*='Date2_I']",
            "input[id*='dtTo']",
            "input[id*='DateTo']",
            "input[id*='EndDate']",
            "input[name*='dtTo']",
            "input[name*='DateTo']",
        ]

        query_patterns = [
            "input[value*='Sorgula']",
            "input[value*='Ara']",
            "input[value*='Listele']",
            "input[value*='Query']",
            "input[value*='Search']",
            "input[value*='Filter']",
            "[id*='btnQuery']",
            "[id*='btnSearch']",
            "[id*='btnFilter']",
            "[id*='btnSorgula']",
            ".dxbButton:has-text('Sorgula')",
            ".dxbButton:has-text('Ara')",
        ]

        export_selectors = [
            "#ctl00_ContentPlaceHolder1_ButtonExportExcel_CD",
            "[id*='ButtonExportExcel']",
            "[id*='Export']",
            "[id*='Excel']",
        ]

        logger.info("GAOSB veri toplama akışı başlatılıyor...")
        
        # PlaywrightClient tarayıcı kapatma döngüsünü context manager ile yönetir (finally temizliği)
        # Çıktı ve ekran görüntüsü klasörlerini hazırla
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        screenshot_dir = output_dir / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        try:
            with PlaywrightClient(headless=headless) as client:
                page = client.create_page()

                def take_screenshot(name: str):
                    try:
                        page.screenshot(path=str(screenshot_dir / f"{name}.png"))
                        logger.info(f"Ekran görüntüsü kaydedildi: {name}.png")
                    except Exception as ex:
                        logger.warning(f"Ekran görüntüsü alınamadı ({name}): {ex}")

                try:
                    # Adım 1: Portal ana sayfasına git
                    try:
                        logger.info(f"GAOSB adresine gidiliyor: {gaosb_url}")
                        page.goto(gaosb_url, wait_until="domcontentloaded", timeout=45000)
                        take_screenshot("01_login_page")
                    except Exception as e:
                        logger.error(f"GAOSB portal ana sayfasına ulaşılamadı: {e}")
                        raise SourceAuthenticationError("gaosb") from e

                    # Adım 2: Kullanıcı girişi (Login)
                    try:
                        logger.info("Kullanıcı kimlik bilgileri dolduruluyor...")
                        page.locator("#ctl00_ContentPlaceHolder1_eUserName_I").first.fill(username)
                        page.locator("#ctl00_ContentPlaceHolder1_ePassword_I").first.fill(password)

                        # EULA onay kutusu (görünürse)
                        eula_cb = page.locator("#ctl00_ContentPlaceHolder1_chkReadcontract_S").first
                        if eula_cb.is_visible(timeout=2000):
                            eula_cb.click()
                            logger.info("EULA sözleşme onay kutusu işaretlendi.")

                        # Neden: DevExpress butonu görünür <div class="dxb"> ile sarılı,
                        # arkasındaki <input type="submit"> pointer events almıyor.
                        # Görünür div'e tıklamak gerekiyor.
                        login_btn_div = page.locator("#ctl00_ContentPlaceHolder1_LoginButton_CD").first
                        try:
                            if login_btn_div.is_visible(timeout=3000):
                                login_btn_div.click()
                                logger.info("Login butonu (DevExpress div) tıklandı.")
                            else:
                                # Fallback: JavaScript ile submit
                                logger.info("Div görünür değil, JavaScript submit deneniyor...")
                                page.evaluate("document.querySelector('form').submit()")
                        except Exception as e:
                            logger.error(f"Login butonu tıklanamadı: {e}")
                            raise SourceAuthenticationError("gaosb") from e

                        # mainpage.aspx sayfasına yönlenmeyi bekle
                        page.wait_for_url("**/mainpage.aspx", timeout=30000)
                        logger.info("Giriş başarılı, mainpage.aspx sayfasına ulaşıldı.")
                        take_screenshot("02_mainpage")
                    except Exception as e:
                        logger.error(f"Kullanıcı girişi veya yönlendirme başarısız oldu: {e}")
                        raise SourceAuthenticationError("gaosb") from e

                    # Adım 3: Sayaç Sorgu Sayfasına Geç
                    try:
                        logger.info("Sayaç sorgu sayfasına geçiş yapılıyor...")
                        page.evaluate("__doPostBack('ctl00$mnuQuery', '')")
                        page.wait_for_load_state("domcontentloaded", timeout=20000)
                        time.sleep(2)
                        take_screenshot("03_query_page")
                    except Exception as e:
                        logger.error(f"Sayaç sorgu sayfasına geçiş yapılamadı: {e}")
                        raise

                    # Adım 4: VIEWSTATE Parse (Değerler post'a eklenir ama logda gösterilmez)
                    try:
                        logger.info("VIEWSTATE değerleri çözümleniyor...")
                        viewstate = page.locator("#__VIEWSTATE").get_attribute("value") or ""
                        viewstate_gen = page.locator("#__VIEWSTATEGENERATOR").get_attribute("value") or ""
                        event_val = page.locator("#__EVENTVALIDATION").get_attribute("value") or ""

                        # Güvenlik ve log temizliği için sadece uzunluk bilgileri yazılır
                        logger.info(f"__VIEWSTATE okundu (Uzunluk: {len(viewstate)})")
                        logger.info(f"__VIEWSTATEGENERATOR okundu (Uzunluk: {len(viewstate_gen)})")
                        logger.info(f"__EVENTVALIDATION okundu (Uzunluk: {len(event_val)})")
                    except Exception as e:
                        logger.error(f"VIEWSTATE/EventValidation bilgileri okunamadı: {e}")
                        raise

                    # Adım 5: Tarih Doldurma ve Sorgulama
                    try:
                        logger.info("Sayfa üzerindeki text input alanları taranıyor...")
                        text_inputs = page.query_selector_all("input[type='text'], input:not([type])")
                        for idx, inp in enumerate(text_inputs):
                            inp_id = inp.get_attribute("id") or ""
                            inp_name = inp.get_attribute("name") or ""
                            inp_placeholder = inp.get_attribute("placeholder") or ""
                            logger.info(f"  - Input [{idx}]: id='{inp_id}', name='{inp_name}', placeholder='{inp_placeholder}'")

                        # Başlangıç ve Bitiş tarih input alanlarını tespit et
                        from_el = None
                        for sel in from_selectors:
                            try:
                                el = page.locator(sel).first
                                if el.is_visible(timeout=1000):
                                    from_el = el
                                    logger.info(f"date_from için eşleşen selector bulundu: {sel}")
                                    break
                            except Exception:
                                continue

                        to_el = None
                        for sel in to_selectors:
                            try:
                                el = page.locator(sel).first
                                if el.is_visible(timeout=1000):
                                    to_el = el
                                    logger.info(f"date_to için eşleşen selector bulundu: {sel}")
                                    break
                            except Exception:
                                continue

                        # Eğer tarih alanları bulunamazsa hata fırlatılır (tahmin edilmez)
                        if not from_el or not to_el:
                            logger.error("Başlangıç veya bitiş tarihi giriş alanları sayfada tespit edilemedi.")
                            raise ValueError("Tarih input selector'ları bulunamadı. Lütfen sayfa yapısını kontrol edin.")

                        logger.info(f"Tarih alanları dolduruluyor: {formatted_date_from} - {formatted_date_to}")

                        # Neden: DevExpress DateEdit bileşeni fill() ile değer almayabilir.
                        # JavaScript ile value set edip change event tetiklemek daha güvenilir.
                        def fill_dx_date(el, value: str):
                            el.click()
                            time.sleep(0.3)
                            # Önce triple-click ve Control+A ile tümünü seç, sonra yaz
                            el.click(click_count=3)
                            time.sleep(0.2)
                            page.keyboard.press("Control+A")
                            time.sleep(0.2)
                            el.type(value, delay=80)
                            time.sleep(0.3)
                            page.keyboard.press("Tab")
                            time.sleep(0.3)

                        fill_dx_date(from_el, formatted_date_from)
                        logger.info(f"  date_from girildi: {formatted_date_from}")

                        fill_dx_date(to_el, formatted_date_to)
                        logger.info(f"  date_to girildi: {formatted_date_to}")

                        # Neden: Tarihlerin input'a yerleştiğini doğrulamak için mevcut değeri logla
                        from_val = from_el.input_value()
                        to_val = to_el.input_value()
                        logger.info(f"  Doğrulama — Date1 değeri: '{from_val}', Date2 değeri: '{to_val}'")
                        time.sleep(1)
                        take_screenshot("04_dates_filled")

                        # Neden: Önce sayfadaki tüm butonları logla, sorgu butonunun
                        # gerçek ID/name değerini tespit etmek için.
                        all_buttons = page.evaluate("""() => {
                            return [...document.querySelectorAll(
                                'input[type="button"], input[type="submit"], .dxbButton, .dxb'
                            )].map(el => ({
                                tag: el.tagName,
                                id: el.id || '',
                                name: el.name || '',
                                value: el.value || el.innerText || '',
                                visible: el.offsetParent !== null
                            }));
                        }""")
                        for b in all_buttons:
                            logger.info(f"  Buton: id='{b.get('id')}' name='{b.get('name')}' value='{b.get('value')}' visible={b.get('visible')}")

                        # Neden: DevExpress sorgu butonu PostBack ile çalışıyor,
                        # görünür div'e tıklamak gerekiyor.
                        query_clicked = False

                        # Strateji 1: BtnSubmit veya bilinen ID'lere göre tıkla
                        known_query_ids = [
                            "#ctl00_ContentPlaceHolder1_BtnSubmit_CD",
                            "#ctl00_ContentPlaceHolder1_btnQuery_CD",
                            "#ctl00_ContentPlaceHolder1_btnSorgula_CD",
                            "#ctl00_ContentPlaceHolder1_Button1_CD",
                        ]
                        for qid in known_query_ids:
                            try:
                                el = page.locator(qid).first
                                if el.is_visible(timeout=1000):
                                    el.click()
                                    logger.info(f"Sorgu butonu tıklandı: {qid}")
                                    query_clicked = True
                                    break
                            except Exception:
                                continue

                        # Strateji 2: .dxb div içinde Sorgula/Listele/Ara metni ara
                        if not query_clicked:
                            for text in ["Sorgula", "Listele", "Ara", "Query", "Getir"]:
                                try:
                                    el = page.locator(f".dxb:has-text('{text}')").first
                                    if el.is_visible(timeout=1000):
                                        el.click()
                                        logger.info(f"Sorgu butonu metin ile tıklandı: {text}")
                                        query_clicked = True
                                        break
                                except Exception:
                                    continue

                        # Strateji 3: JavaScript PostBack ile dene
                        if not query_clicked:
                            logger.info("JavaScript PostBack ile sorgu deneniyor...")
                            try:
                                page.evaluate("__doPostBack('ctl00$ContentPlaceHolder1$BtnSubmit', '')")
                                query_clicked = True
                                logger.info("PostBack ile sorgu gönderildi.")
                            except Exception as e:
                                logger.warning(f"PostBack denemesi başarısız: {e}")

                        if not query_clicked:
                            logger.error("Sorgu butonu hiçbir yöntemle bulunamadı.")
                            raise ValueError("Sorgu butonu bulunamadı.")

                        take_screenshot("05_query_clicked")

                        # Neden: PostBack sonrası sayfa yenilenir, grid yüklenmesini bekle.
                        logger.info("Grid yüklenmesi bekleniyor (.dxgvDataRow veya .dxgvEmptyDataRow)...")
                        try:
                            page.wait_for_selector(
                                ".dxgvDataRow, tr.dxgvDataRow_Default, .dxgvEmptyDataRow, tr.dxgvEmptyDataRow_Default",
                                timeout=20000
                            )
                            logger.info("Veri gridi başarıyla yüklendi.")
                        except Exception as ex:
                            logger.warning(f"Grid yükleme beklentisi timeout oldu, yine de export adımına geçiliyor: {ex}")

                        time.sleep(1.5)
                        take_screenshot("06_grid_loaded")
                    except Exception as e:
                        logger.error(f"Tarih doldurma veya sorgulama adımı başarısız oldu: {e}")
                        raise

                    # Adım 6: Excel Export ve Rapor Kaydetme
                    try:
                        logger.info("Export butonu aranıyor...")
                        export_btn = None
                        for sel in export_selectors:
                            try:
                                btn = page.locator(sel).first
                                if btn.is_visible(timeout=1000):
                                    export_btn = btn
                                    logger.info(f"Export butonu eşleşen selector: {sel}")
                                    break
                            except Exception:
                                continue

                        if not export_btn:
                            logger.error("Excel export butonu bulunamadı.")
                            raise ValueError("Export butonu bulunamadı.")

                        logger.info("İndirme işlemi bekleniyor...")
                        with page.expect_download(timeout=45000) as download_info:
                            export_btn.click()
                        download = download_info.value

                        # Çıktı klasörünü hazırla
                        from_yyyymmdd = get_yyyymmdd(formatted_date_from)
                        to_yyyymmdd = get_yyyymmdd(formatted_date_to)
                        dest_filename = f"gaosb_{from_yyyymmdd}_{to_yyyymmdd}.xlsx"
                        dest_path = output_dir / dest_filename

                        download.save_as(str(dest_path))
                        logger.info(f"Excel başarıyla indirildi ve kaydedildi: {dest_path}")
                        take_screenshot("07_export_completed")
                        return dest_path
                    except Exception as e:
                        logger.error(f"Excel export veya indirme adımı başarısız oldu: {e}")
                        raise
                except Exception as e:
                    # Tarayıcı kapanmadan önce hata ekran görüntüsünü kaydet
                    take_screenshot("error_screenshot")
                    raise
        except Exception as e:
            logger.error(f"GAOSB extraction işlemi sırasında genel hata oluştu: {e}")
            raise
