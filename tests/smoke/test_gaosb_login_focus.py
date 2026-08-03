"""
Neden: 2026-08-01 aylık koşusunda GAOSB login'i "şifre alanı boş" diye üç kez düştü.
Kök neden: DevExpress maskeli şifre kutusunun dummy (_CLND) → gerçek (_I) alan geçişi
olmadı, odak kullanıcı adı alanında kaldı ve şifre tuşları MASKESİZ kullanıcı adı
kutusuna döküldü (log kanıtı: kullanıcı adı 9 → 13, şifre 0; 13 = 9 + 4).

Bu testler odak sızıntısının ÖNLENDİĞİNİ (şifre yanlış alana hiç yazılmaz) ve sızıntının
sessizce yeniden denenmediğini doğrular.

2026-08-02 09:00 regresyonu: odak alınamadığında (şifre HİÇ yazılmadan) da tek atışta pes
ediliyordu ve günlük mahsuplaşma tamamen düşüyordu. Oysa DevExpress maskesi bazen geç
initialize oluyor ve ikinci deneme başarılı oluyor. Bu yüzden iki durum ayrıldı:
sızıntı = yeniden deneme YOK, odak alınamadı = yeniden deneme VAR.
"""

import pytest

from app.sources.exceptions import SourceAuthenticationError
from app.sources.gaosb.extractor import (
    GaosbExtractor,
    GaosbLoginFocusError,
    GaosbPasswordLeakError,
)

USERNAME = "251842607"  # 9 karakter — gerçek koşudaki uzunluk
PASSWORD = "1234"       # 4 karakter — gerçek koşudaki uzunluk


class FakeInput:
    """Odak semantiğini gerçekçi taklit eden input: tuşlar AKTİF elemana yazılır."""

    def __init__(self, page, el_id, visible=True, takes_focus=True):
        self.page = page
        self.id = el_id
        self.value = ""
        self.visible = visible
        # Neden: DevExpress'te gizli/geçişi yapılmamış alan tıklansa da odağı almıyor.
        self.takes_focus = takes_focus
        self.clicked = 0

    @property
    def first(self):
        return self

    def click(self, **_kw):
        self.clicked += 1
        if self.takes_focus:
            self.page.active_id = self.id

    def focus(self, **_kw):
        if self.takes_focus:
            self.page.active_id = self.id

    def is_visible(self, **_kw):
        return self.visible

    def count(self):
        return 1

    def get_attribute(self, name, **_kw):
        return self.id if name == "id" else None

    def input_value(self, **_kw):
        return self.value

    def press(self, key, **_kw):
        if key == "Control+a" and self.page.active_id == self.id:
            self.value = ""

    def press_sequentially(self, text, **_kw):
        # Neden: Gerçek klavye yazımı odaktaki elemana gider — tuşları çağrılan
        # locator'a değil, sayfanın aktif elemanına yaz. Sızıntı tam olarak budur.
        target = self.page.by_id.get(self.page.active_id)
        if target is not None:
            target.value += text


class LateMaskDummy(FakeInput):
    """
    DevExpress maskesinin GEÇ initialize olduğu durum (2026-08-02 09:00 imzası): ilk
    kontrolde dummy alan henüz görünmüyor ve gerçek alan tıklansa da odağı tutmuyor.
    Mask hazır olduğunda dummy görünür oluyor ve tıklanınca gerçek alan odak alabiliyor.
    """

    def __init__(self, page, el_id, visible_from_check):
        super().__init__(page, el_id, visible=False)
        self._checks = 0
        self._visible_from_check = visible_from_check

    def is_visible(self, **_kw):
        self._checks += 1
        return self._checks >= self._visible_from_check

    def click(self, **_kw):
        super().click(**_kw)
        self.page.pwd.takes_focus = True


class FakePage:
    def __init__(
        self,
        password_takes_focus=True,
        steal_focus_on_type=False,
        mask_ready_at_check=None,
    ):
        self.user = FakeInput(self, "ctl00_ContentPlaceHolder1_eUserName_I")
        self.pwd = FakeInput(
            self,
            "ctl00_ContentPlaceHolder1_ePassword_I",
            takes_focus=password_takes_focus and mask_ready_at_check is None,
        )
        if mask_ready_at_check is None:
            self.dummy = FakeInput(self, "ctl00_ContentPlaceHolder1_ePassword_I_CLND")
        else:
            self.dummy = LateMaskDummy(
                self, "ctl00_ContentPlaceHolder1_ePassword_I_CLND", mask_ready_at_check
            )
        self.eula = FakeInput(self, "chk", visible=False)
        self.by_id = {e.id: e for e in (self.user, self.pwd, self.dummy)}
        self.active_id = ""
        self.url = "https://osos.gaosb.org/Login.aspx"
        self._steal_focus_on_type = steal_focus_on_type

    def locator(self, selector):
        if "eUserName" in selector:
            return self.user
        if "_CLND" in selector:
            return self.dummy
        if "ePassword" in selector:
            if self._steal_focus_on_type:
                # Neden: Odak doğrulaması geçtikten SONRA DevExpress odağı geri alıyor.
                self.pwd.press_sequentially = self._stealing_type
            return self.pwd
        return self.eula

    def _stealing_type(self, text, **_kw):
        self.active_id = self.user.id
        self.user.value += text

    def wait_for_selector(self, *_a, **_kw):
        return None

    def evaluate(self, script, *_a):
        if "activeElement" in script:
            return self.active_id
        return 0


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("app.sources.gaosb.extractor.time.sleep", lambda *_a: None)


def test_password_typed_into_password_field_on_happy_path():
    page = FakePage()
    GaosbExtractor()._fill_login_form(page, USERNAME, PASSWORD)

    assert page.user.value == USERNAME
    assert page.pwd.value == PASSWORD


def test_focus_leak_aborts_before_password_is_typed():
    """Şifre alanı odağı hiç alamıyorsa şifre HİÇ yazılmamalı."""
    page = FakePage(password_takes_focus=False)

    with pytest.raises(GaosbLoginFocusError) as exc:
        GaosbExtractor()._fill_login_form(page, USERNAME, PASSWORD)

    # Asıl güvenlik iddiası: şifre maskesiz kullanıcı adı alanına sızmadı.
    assert page.user.value == USERNAME
    assert PASSWORD not in page.user.value
    assert page.pwd.value == ""
    assert "odaklan" in str(exc.value).lower()


def test_focus_stolen_during_typing_is_detected():
    """Odak doğrulaması geçse bile kullanıcı adı büyüdüyse süreç durmalı."""
    page = FakePage(steal_focus_on_type=True)

    with pytest.raises(GaosbPasswordLeakError) as exc:
        GaosbExtractor()._fill_login_form(page, USERNAME, PASSWORD)

    # 2026-08-01'deki tam imza: 9 → 13
    assert len(page.user.value) == len(USERNAME) + len(PASSWORD)
    assert "sızıntı" in str(exc.value).lower()


def test_late_devexpress_mask_init_recovers_without_leak():
    """
    2026-08-02 regresyonu: mask geç initialize olduğunda ilk turda odak alınamıyor.
    İkinci tur şifreyi doğru alana yazmalı — koşu düşmemeli.
    """
    page = FakePage(mask_ready_at_check=2)

    GaosbExtractor()._fill_login_form(page, USERNAME, PASSWORD)

    assert page.pwd.value == PASSWORD
    assert page.user.value == USERNAME  # maskesiz alana sızmadı


def test_password_leak_is_not_silently_retried():
    """
    GaosbPasswordLeakError, _perform_login'in 3'lük döngüsüne düşmemeli. Dışarıya
    SourceAuthenticationError olarak çıkar (teşhis logu asıl nedeni yazar).
    """
    page = FakePage(steal_focus_on_type=True)
    extractor = GaosbExtractor()
    page.wait_for_function = lambda *_a, **_kw: None

    with pytest.raises(SourceAuthenticationError):
        extractor._perform_login(page, USERNAME, PASSWORD)

    # Tek deneme yapılmış olmalı (3 değil) — şifre alanı yalnızca bir kez tıklandı.
    assert page.pwd.clicked == 1


def test_focus_failure_is_retried_but_password_never_typed():
    """
    Odak hiç alınamadığında şifre yazılmadığı için sızıntı yok; tek atışta pes etmek
    yerine form baştan doldurulup yeniden denenmeli (2026-08-02 koşu kaybı).
    """
    page = FakePage(password_takes_focus=False)
    extractor = GaosbExtractor()
    page.wait_for_function = lambda *_a, **_kw: None

    with pytest.raises(Exception):
        extractor._perform_login(page, USERNAME, PASSWORD)

    assert page.pwd.clicked > 1, "Odak hatası yeniden denenmeliydi"
    assert page.pwd.value == ""
    assert page.user.value == USERNAME  # şifre maskesiz alana düşmedi


def test_screenshot_skipped_when_credential_fields_cannot_be_cleared(tmp_path, monkeypatch):
    """Alanlar temizlenemiyorsa ekran görüntüsü alınmamalı (açık metin şifre riski)."""
    page = FakePage()
    shots = []

    def _boom(_script, *_a):
        raise RuntimeError("evaluate engellendi")

    page.evaluate = _boom
    page.title = lambda: "Abbysis OSOS Web arayüzü"
    page.screenshot = lambda **kw: shots.append(kw)
    monkeypatch.setattr("app.sources.gaosb.extractor.PROJECT_ROOT", tmp_path)

    GaosbExtractor()._log_login_failure_diagnostics(page)

    assert shots == [], "Temizlik başarısızken ekran görüntüsü alınmamalıydı"
