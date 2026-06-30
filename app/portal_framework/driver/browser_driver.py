"""
BrowserDriver - tarayici soyutlama arayuzu.

Neden: Playwright'i adapter ve strateji kodundan izole etmek (ADR-001). Boylece
MockDriver ile browser olmadan test, gelecekte SeleniumDriver/RemoteDriver ile farkli
backend desteklenir. Stratejiler Playwright'i degil bu arayuzu bilir.

Bu modul bilincli olarak app.portal_framework.models'tan bagimsizdir (dongusel import
engelleme). Driver yalnizca kendi primitif tiplerini tanir.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional


class WaitState(str, Enum):
    """Neden: wait_for_selector icin beklenen DOM durumunu tip-guvenli ifade etmek."""

    ATTACHED = "attached"
    DETACHED = "detached"
    VISIBLE = "visible"
    HIDDEN = "hidden"


@dataclass(frozen=True)
class NetworkRecord:
    """
    Neden: Ag trafiginin denetim icin kanitini tutmak. GUVENLIK: istek govdesi
    (body) ICERIGI asla tutulmaz; yalnizca uzunlugu ve JSON anahtar isimleri.
    Boylece kimlik bilgisi/sifre loglanmaz.
    """

    url: str
    method: str
    status: int
    content_type: str = ""
    request_body_len: int = 0
    response_keys: List[str] = field(default_factory=list)


# Ag yanitlarini dinleyen geri cagrim tipi (Observer pattern hook).
ResponseHandler = Callable[[NetworkRecord], None]


class BrowserDriver(ABC):
    """
    Neden: Tum tarayici etkilesimlerini tek bir sozlesme altinda toplamak.
    Yalnizca framework seviyesinde gereken cekirdek metodlar tanimlidir (KISS/YAGNI).
    """

    @abstractmethod
    def goto(self, url: str, timeout_ms: Optional[int] = None) -> None:
        """Verilen URL'e gider."""

    @abstractmethod
    def click(self, selector: str, timeout_ms: Optional[int] = None) -> None:
        """Verilen selectore tiklar."""

    @abstractmethod
    def fill(self, selector: str, value: str, timeout_ms: Optional[int] = None) -> None:
        """Verilen input alanini doldurur."""

    @abstractmethod
    def wait_for_selector(
        self,
        selector: str,
        state: WaitState = WaitState.VISIBLE,
        timeout_ms: Optional[int] = None,
    ) -> bool:
        """Selectorun istenen duruma gelmesini bekler; basari durumunu doner."""

    @abstractmethod
    def wait_for_download(self, timeout_ms: Optional[int] = None) -> Path:
        """Bir indirme tamamlanana kadar bekler ve indirilen dosya yolunu doner."""

    @abstractmethod
    def screenshot(self, path: Path, full_page: bool = False) -> Path:
        """Ekran goruntusu alir ve kaydedildigi yolu doner."""

    @abstractmethod
    def save_dom(self, path: Path) -> Path:
        """Gecerli sayfanin DOM'unu diske kaydeder ve yolu doner."""

    @abstractmethod
    def current_url(self) -> str:
        """Gecerli URL'i doner."""

    @abstractmethod
    def on_response(self, handler: ResponseHandler) -> None:
        """
        Neden: Ag yaniti gozlemcisi (Observer) kaydetmek. Boylece adapter kodu
        network log yazma sorumlulugunu uzerine almaz; gevsek bagli kalir.
        """

    @abstractmethod
    def close(self) -> None:
        """Tarayici kaynaklarini serbest birakir (orphan process engelleme)."""
