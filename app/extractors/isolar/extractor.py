import re
from pathlib import Path
from typing import Optional
from playwright.sync_api import Page
from app.core.config import settings
from app.core.logger import setup_logger
from app.core.utils import with_retry
from app.core.exceptions import (
    IsolarError,
    IsolarAuthenticationError,
    IsolarCredentialsError,
    IsolarServerSelectionError,
    IsolarTimeoutError,
    IsolarUnexpectedPageError,
    IsolarNavigationTimeoutError,
    IsolarReportPageNotFoundError,
    IsolarMenuStructureChangedError,
    IsolarDownloadError,
    IsolarDownloadTimeoutError,
    IsolarExportButtonNotFoundError
)


logger = setup_logger("IsolarExtractor")

class IsolarExtractor:
    """
    Neden: İsOlar Cloud portalına özgü sayfa etkileşimlerini, login akışını,
    oturum doğrulamayı ve hata yönetimini sarmalayıp yönetmek.
    """
    def __init__(self, page: Page, run_id: Optional[str] = None):
        self.page = page
        self.run_id = run_id

    @with_retry(
        max_retries=3,
        backoff_factor=2.0,
        retryable_exceptions=(IsolarTimeoutError, IsolarUnexpectedPageError, IsolarNavigationTimeoutError),
        non_retryable_exceptions=(IsolarCredentialsError, IsolarServerSelectionError)
    )
    def login_and_verify(self) -> None:
        """
        Neden: Sprint 1 hedefi olan İsOlar portalına başarılı şekilde giriş yapma
        ve oturum açıldığını doğrulama akışını orkestre etmek.
        """
        logger.info("İsOlar oturum açma akışı başlatılıyor...")
        
        self._open_login_page()
        self._handle_cookies()
        self._login()
        self._verify_login()
        
        logger.info("İsOlar oturumu başarıyla doğrulandı.")

    def _open_login_page(self) -> None:
        """
        Neden: İsOlar giriş sayfasına gitmek ve sayfanın ağ hareketliliği bitene kadar yüklenmesini beklemek.
        """
        base_url = settings.base_url
        logger.info(f"Giriş sayfasına gidiliyor: {base_url}")
        try:
            self.page.goto(base_url, wait_until="networkidle", timeout=20000)
        except Exception as e:
            raise IsolarTimeoutError(f"İsOlar portal sayfasına bağlanılamadı (Zaman aşımı): {e}")

    def _handle_cookies(self) -> None:
        """
        Neden: Çerez onay modalı çıktığında 'Evet katılıyorum' butonuna tıklayarak
        otomasyonu engelleyebilecek çerez perdesini kapatmak.
        """
        try:
            # Kullanıcı dostu get_by_role seçimi ile 'Evet' veya 'Accept' içeren birincil butonu bul
            cookie_btn = self.page.get_by_role("button", name=re.compile("Evet|Agree|Accept", re.I))
            if cookie_btn.is_visible():
                logger.info("Çerez onay modalı bulundu, onaylanıyor...")
                cookie_btn.click()
                # Modalın kapanması için kısa bir süre bekle
                self.page.wait_for_timeout(500)
        except Exception as e:
            logger.debug(f"Çerez onay modalı adımı atlandı veya hata oluştu (kritik değil): {e}")

    def _login(self) -> None:
        """
        Neden: Kimlik bilgilerini doldurmak, sözleşmeleri kabul etmek,
        güvenlik kontrollerini (CAPTCHA) denetlemek ve giriş işlemini tetiklemek.
        """
        logger.info("Giriş bilgileri dolduruluyor...")
        
        # 1. Kullanıcı Adı ve Şifre Alanlarını Doldur
        # Kullanıcı dostu get_by_placeholder kullanarak 'Hesap/Account' ve 'Şifre/Password' alanlarını hedefle
        account_input = self.page.get_by_placeholder(re.compile("Hesap|Account", re.I))
        password_input = self.page.get_by_placeholder(re.compile("Şifre|Password", re.I))
        
        # Elementlerin görünür ve aktif olmasını bekle
        account_input.wait_for(state="visible", timeout=5000)
        password_input.wait_for(state="visible", timeout=5000)
        
        account_input.fill(settings.username)
        password_input.fill(settings.password)

        # 2. Güvenlik ve CAPTCHA Kontrolü
        # iSolarCloud bazen şüpheli isteklerde veya çoklu girişlerde doğrulama kodu (Lütfen Girin) ister.
        captcha_input = self.page.get_by_placeholder(re.compile("Lütfen Girin|Verification Code", re.I))
        if captcha_input.is_visible():
            raise IsolarAuthenticationError(
                "İsOlar portalı CAPTCHA / Doğrulama Kodu talep ediyor. Otomasyon bu adımı manuel müdahale olmadan geçemez."
            )

        # 3. Gizlilik Politikası / Kullanıcı Sözleşmesi Kutusu Kontrolü
        # Eğer sayfada yasal onay onay kutusu varsa bulup işaretle
        checkboxes = self.page.locator("input[type='checkbox']").all()
        for cb in checkboxes:
            label_text = cb.evaluate("el => { const p = el.closest('.el-checkbox') || el.parentElement; return p ? p.innerText : ''; }").lower()
            if any(word in label_text for word in ["sözleşme", "gizlilik", "politika", "agree", "policy", "terms", "service"]):
                logger.info(f"Gizlilik/Sözleşme onay kutusu işaretleniyor: '{label_text}'")
                cb.check(force=True)

        # 4. Giriş Butonunu Tetikle
        # Birden fazla 'Giriş' butonu (mobil/masaüstü için gizli/görünür) arasından sadece görünür olanı bulup tıkla
        login_buttons = self.page.get_by_role("button", name=re.compile("Giriş|Login", re.I)).all()
        clicked = False
        for btn in login_buttons:
            if btn.is_visible():
                logger.info("Görünür Giriş butonuna tıklanıyor...")
                btn.click()
                clicked = True
                break
                
        if not clicked:
            raise IsolarUnexpectedPageError("Giriş yapabilmek için görünür bir 'Giriş/Login' butonu bulunamadı.")

    def _verify_login(self) -> None:
        """
        Neden: Giriş sonrasında başarılı bir yönlendirme yapıldığını veya
        sayfada oluşan giriş hatalarını tespit etmek.
        """
        logger.info("Giriş başarısı doğrulanıyor...")
        self._wait_for_authenticated_state()
        self._validate_authenticated_ui()

    def _wait_for_authenticated_state(self) -> None:
        """
        Neden: Giriş formundan çıkılıp URL'in yönlenmesini veya
        giriş bileşenlerinin kaybolmasını asenkron olarak beklemek.
        """
        logger.info("Oturumun açılması bekleniyor (sayfa durum değişimi)...")
        try:
            # 1. URL'in login içermeyen bir adrese geçmesini bekle
            self.page.wait_for_function(
                "() => !window.location.href.toLowerCase().includes('login')",
                timeout=12000
            )
            # 2. Şifre alanının gizlenmesini bekle
            password_input = self.page.get_by_placeholder(re.compile("Şifre|Password", re.I))
            password_input.wait_for(state="hidden", timeout=5000)
            
            logger.info("Giriş formundan başarıyla çıkıldı.")
        except Exception as e:
            logger.debug(f"Oturum açma geçiş süreci beklerken zaman aşımı veya uyarı: {e}")

    def _validate_authenticated_ui(self) -> None:
        """
        Neden: Giriş yapıldıktan sonra arayüzün kimliği doğrulanmış durumunu
        (authenticated layout) teyit etmek.
        """
        # 1. Login formu görünmüyor olmalı
        password_input = self.page.get_by_placeholder(re.compile("Şifre|Password", re.I))
        if password_input.is_visible():
            logger.warning("Doğrulama Hatası: Giriş formu hala görünür durumda.")
            self._check_login_failures()

        # 2. URL login sayfasından çıkmış olmalı
        if "login" in self.page.url.lower():
            logger.warning("Doğrulama Hatası: URL hala giriş sayfasını işaret ediyor.")
            self._check_login_failures()

        # 3. Authenticated layout görünmeli (Sidebar, Logout, User Menu, Plant List, Dashboard Container vb.)
        authenticated_indicators = [
            ".el-aside",             # Element Plus Sidebar
            ".sidebar",              # Genel Sidebar
            ".plant-list",           # Tesis Listesi Container
            ".plant-item",           # Tekil Tesis Elemanı
            "[href*='plantList']",   # Tesis Listesi Linki
            "[class*='plant']",      # Tesis içeren sınıf
            "[class*='user-avatar']",# Kullanıcı Profili/Avatarı
            ".user-avatar",          # Kullanıcı Avatarı
            "text=Oturumu Kapat",    # Oturumu kapat butonu
            "text=Çıkış",            # Türkçe Çıkış metni
            "text=Logout",           # İngilizce Logout metni
            ".main-container"        # Ana kapsayıcı dizin
        ]

        ui_valid = False
        for selector in authenticated_indicators:
            try:
                if self.page.locator(selector).first.is_visible():
                    logger.info(f"Oturum açma doğrulanmış arayüz bileşeni ile teyit edildi: {selector}")
                    ui_valid = True
                    break
            except Exception:
                pass

        # Alternatif olarak URL post-login şablonu içeriyorsa fakat eleman tam render olmadıysa tolerans sağla
        if not ui_valid:
            if any(p in self.page.url.lower() for p in ["plantlist", "main", "dashboard", "station"]):
                logger.info(f"Oturum açma post-login URL yapısı ile doğrulandı: {self.page.url}")
                ui_valid = True

        if not ui_valid:
            logger.error("Kimliği doğrulanmış arayüz bileşenleri veya yönlendirilmiş URL tespit edilemedi.")
            self._check_login_failures()

        logger.info(f"Oturum başarıyla açıldı ve arayüz doğrulandı. Mevcut URL: {self.page.url}")


    def _check_login_failures(self) -> None:
        """
        Neden: Giriş başarısız olduğunda sayfadaki hata mesajlarını veya diyalogları
        okuyarak anlamlı ve spesifik bir exception fırlatmak.
        """
        # Element Plus hata kutuları, alert ve mesaj sınıflarını sorgula
        error_locators = [
            ".el-message-box__message",
            ".el-message",
            ".error-message",
            ".el-notification__content",
            "[role='alert']"
        ]
        
        visible_errors = []
        for selector in error_locators:
            elements = self.page.locator(selector).all()
            for el in elements:
                if el.is_visible():
                    text = el.inner_text().strip()
                    if text:
                        visible_errors.append(text)
                        
        if visible_errors:
            error_msg = " | ".join(visible_errors)
            logger.error(f"Giriş hatası tespit edildi: {error_msg}")
            
            # Hata metnine göre spesifik exception fırlat
            if any(w in error_msg.lower() for w in ["şifre", "parola", "şifre yanlış", "password", "incorrect", "wrong"]):
                raise IsolarCredentialsError(f"Geçersiz şifre veya kullanıcı adı: {error_msg}")
            elif any(w in error_msg.lower() for w in ["sunucu", "mevcut", "server", "not exist"]):
                raise IsolarServerSelectionError(f"Sunucu seçimi yanlış veya kullanıcı mevcut değil: {error_msg}")
            else:
                raise IsolarAuthenticationError(f"Oturum açma hatası: {error_msg}")

        # Eğer görünür hata yoksa ama URL hala login sayfasındaysa timeout fırlat
        if "login" in self.page.url.lower():
            raise IsolarTimeoutError("Giriş yapıldı fakat ana sayfaya yönlendirme zaman aşımına uğradı.")
        else:
            raise IsolarUnexpectedPageError(f"Beklenmeyen bir sayfaya yönlendirme yapıldı. URL: {self.page.url}")

    @with_retry(
        max_retries=3,
        backoff_factor=2.0,
        retryable_exceptions=(IsolarError,)
    )
    def navigate_to_daily_report(self) -> None:
        """
        Neden: Giriş sonrasında global Report menüsü ve Yield Report alt menüsü üzerinden
        günlük üretim raporunun yer aldığı sayfaya güvenli navigasyonu gerçekleştirmek.
        """
        logger.info("Günlük üretim raporu sayfasına navigasyon başlatılıyor...")
        
        # 1. Global 'Report' menüsüne tıkla
        try:
            report_menu = self.page.locator("text=Report").first
            # Menu yapısının değişip değişmediğini kontrol et
            report_menu.wait_for(state="visible", timeout=10000)
            logger.info("Global Report menüsü bulundu, tıklanıyor...")
            report_menu.click()
        except Exception as e:
            raise IsolarMenuStructureChangedError(f"Global 'Report' menüsü bulunamadı veya tıklanamadı: {e}")
            
        # 2. Report Overview sayfasının yüklenmesini ve URL değişimini bekle
        try:
            self.page.wait_for_url(re.compile(r"reportTransformation/overview"), timeout=10000)
            self.page.wait_for_load_state("networkidle")
            logger.info("Report Overview sayfası yüklendi.")
        except Exception as e:
            raise IsolarNavigationTimeoutError(f"Report Overview sayfasına yönlendirme zaman aşımına uğradı: {e}")
            
        # 3. 'Yield report' alt menüsüne/kartına tıkla
        try:
            yield_report_btn = self.page.locator("text=Yield report").first
            yield_report_btn.wait_for(state="visible", timeout=8000)
            logger.info("Yield Report alt menüsü bulundu, tıklanıyor...")
            yield_report_btn.click()
        except Exception as e:
            raise IsolarMenuStructureChangedError(f"Yield Report alt menü kartı bulunamadı veya tıklanamadı: {e}")
            
        # 4. Yield Report sayfasının yüklenmesini ve URL değişimini bekle
        try:
            self.page.wait_for_url(re.compile(r"reportTransformation/yieldReport"), timeout=12000)
            self.page.wait_for_load_state("networkidle")
            logger.info("Yield Report sayfası yüklendi.")
        except Exception as e:
            raise IsolarNavigationTimeoutError(f"Yield Report sayfasına yönlendirme zaman aşımına uğradı: {e}")
            
        # 5. Rapor ekranı başarı kriterlerini doğrula (Table, Export Button, Day/Month/Year filters)
        self._verify_report_page_elements()

    def _verify_report_page_elements(self) -> None:
        """
        Neden: Rapor ekranının eksiksiz yüklendiğini, tablo ve dışa aktarım
        butonlarının görüntülendiğini teyit etmek.
        """
        logger.info("Rapor sayfası elemanları doğrulanıyor...")
        
        # Başarı Kriterleri: 
        # - Veri tablosu (el-table__body)
        # - Export butonu (Export metni veya .export-record-btn/.controls-btn)
        # - Date Filter (Day/Month/Year veya Gün/Ay/Yıl metinleri)
        try:
            table = self.page.locator(".el-table__body").first
            table.wait_for(state="visible", timeout=8000)
            logger.info("Veri tablosunun görünürlüğü doğrulandı.")
        except Exception as e:
            raise IsolarReportPageNotFoundError(f"Rapor veri tablosu yüklenemedi veya görünür değil: {e}")
            
        try:
            export_btn = self.page.get_by_role("button", name=re.compile("Export", re.I)).first
            export_btn.wait_for(state="visible", timeout=5000)
            logger.info("Dışa aktarma (Export) butonunun görünürlüğü doğrulandı.")
        except Exception as e:
            raise IsolarReportPageNotFoundError(f"Dışa aktarma (Export) butonu bulunamadı veya görünür değil: {e}")
            
        try:
            day_filter = self.page.locator("text=Day").first
            day_filter.wait_for(state="visible", timeout=5000)
            logger.info("Tarih filtresinin (Day) görünürlüğü doğrulandı.")
        except Exception as e:
            raise IsolarReportPageNotFoundError(f"Zaman kırılım/tarih filtresi bulunamadı veya görünür değil: {e}")
            
        logger.info("Tüm rapor sayfası başarı kriterleri başarıyla karşılandı.")

    @with_retry(
        max_retries=3,
        backoff_factor=2.0,
        retryable_exceptions=(IsolarError,)
    )
    def download_daily_report(self) -> Path:
        """
        Neden: Rapor sayfasında gün filtresinin seçildiğinden emin olmak,
        dışa aktarım işlemini (Export as Excel) asenkron olarak tetiklemek ve
        kuyruktan başarıyla tamamlanan rapor dosyasını indirip geçici konuma kaydetmek.
        """
        logger.info("Günlük üretim raporu indirme işlemi başlatılıyor...")

        # 1. Günlük görünümün (Day) seçildiğinden emin ol / Gerekirse tıkla
        try:
            day_filter = self.page.locator("text=Day").first
            day_filter.wait_for(state="visible", timeout=5000)
            logger.info("Day filtresi seçiliyor...")
            day_filter.click()
            self.page.wait_for_load_state("networkidle")
        except Exception as e:
            logger.warning(f"Day filtresi seçilemedi (devam ediliyor): {e}")

        # 2. Tüm tesisleri seç (İlk checkbox - Select All)
        try:
            inners = self.page.locator(".el-checkbox__inner").all()
            if inners:
                logger.info("Tüm tesisler tabloda işaretleniyor...")
                inners[0].click()
                self.page.wait_for_timeout(1000)
        except Exception as e:
            logger.warning(f"Tablo checkbox işaretleme hatası: {e}")

        # 3. Export butonunu bul ve tıkla (Dropdown aç)
        export_btn = self.page.locator("button.controls-btn").first
        if not export_btn.is_visible():
            raise IsolarExportButtonNotFoundError("Excel dışa aktarım (Export) butonu bulunamadı.")

        logger.info("Export butonu tıklanıyor...")
        export_btn.click()
        self.page.wait_for_timeout(1000)

        # 4. Dropdown menüden "Export as Excel" seç
        try:
            excel_option = self.page.locator("text=Export as Excel").first
            excel_option.wait_for(state="visible", timeout=5000)
            logger.info("Dropdown menüden 'Export as Excel' seçiliyor...")
            excel_option.click()
        except Exception as e:
            raise IsolarMenuStructureChangedError(f"Dropdown üzerinde 'Export as Excel' seçeneği bulunamadı: {e}")

        # 5. "Start export" bildiriminin görünmesini bekle
        try:
            toast = self.page.locator(".el-message").first
            toast.wait_for(state="visible", timeout=8000)
            logger.info(f"Bildirim yakalandı: {toast.inner_text().strip()}")
        except Exception as e:
            logger.warning(f"Bildirim ekranında 'Start export' görülmedi (yine de devam ediliyor): {e}")

        # 6. 'Export records' (Dışa aktarım geçmişi) sayfasına git
        try:
            export_records_btn = self.page.locator("button.export-record-btn").first
            export_records_btn.wait_for(state="visible", timeout=5000)
            logger.info("Export Records sayfasına yönlendiriliyor...")
            export_records_btn.click()
            self.page.wait_for_url(re.compile(r"reportTransformation/reportExport"), timeout=10000)
            self.page.wait_for_load_state("networkidle")
        except Exception as e:
            raise IsolarNavigationTimeoutError(f"Export Records sayfasına yönlendirme hatası: {e}")

        # 7. Asenkron işlem durumunu sorgula (durum 'Export successful' olana kadar bekle)
        success = False
        max_attempts = 15
        poll_interval = 4000
        
        logger.info("Rapor hazırlama durumu sorgulanıyor (Polling)...")
        for attempt in range(max_attempts):
            try:
                row = self.page.locator(".el-table__row").first
                row.wait_for(state="visible", timeout=5000)
                status_text = row.locator("td").nth(3).inner_text().strip()
                logger.info(f"Sorgu {attempt + 1}/{max_attempts}: Durum = '{status_text}'")
                
                if "Export successful" in status_text:
                    success = True
                    break
            except Exception as e:
                logger.warning(f"Sorgulama esnasında satır/durum okunamadı: {e}")
                
            logger.info(f"Rapor henüz hazır değil, {poll_interval/1000}s sonra tekrar denenecek...")
            self.page.wait_for_timeout(poll_interval)
            
            # Sayfayı yenileyerek güncel verileri çek
            try:
                self.page.reload(wait_until="networkidle")
                self.page.wait_for_timeout(2000)
            except Exception as e:
                logger.warning(f"Sayfa yenilenirken hata: {e}")

        if not success:
            raise IsolarDownloadTimeoutError("Belirtilen süre içerisinde rapor üretimi tamamlanamadı (Zaman Aşımı).")

        # 8. Başarıyla üretilmiş olan ilk satırdaki dosyayı indir
        logger.info("Rapor hazır. İndirme (Download) başlatılıyor...")
        try:
            row = self.page.locator(".el-table__row").first
            download_btn = row.locator(".icon-G2_Download_241").first
            
            with self.page.expect_download(timeout=30000) as download_info:
                download_btn.click()
            download = download_info.value
        except Exception as e:
            raise IsolarDownloadError(f"İndirme butonu tıklanırken veya indirme esnasında hata: {e}")

        if not download:
            raise IsolarDownloadError("Dosya indirme işlemi tetiklendi fakat dosya nesnesi alınamadı.")

        # 9. Dosyayı geçici dizine kaydet
        temp_dir = settings.download_directory / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / download.suggested_filename

        logger.info(f"Dosya geçici konuma kaydediliyor: {temp_path}")
        try:
            download.save_as(str(temp_path))
        except Exception as e:
            raise IsolarDownloadError(f"İndirilen geçici dosya diske kaydedilemedi: {e}")

        logger.info(f"Dosya indirme başarıyla tamamlandı: {temp_path.name}")
        return temp_path



