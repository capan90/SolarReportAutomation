"""
MockDriver - gercek tarayici acmadan test edilebilir BrowserDriver.

Neden: Stratejileri ve adapter akisini Playwright/Chromium baslatmadan, hizli ve
deterministik sekilde test etmek (ADR-001 test edilebilirlik gerekcesi). Tum cagrilari
kaydeder, onceden ayarlanmis (fixture) degerleri doner.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.portal_framework.driver.browser_driver import (
    BrowserDriver,
    NetworkRecord,
    ResponseHandler,
    WaitState,
)
from app.portal_framework.exceptions import DriverOperationError


class MockDriver(BrowserDriver):
    """
    Neden: BrowserDriver sozlesmesini bellek-ici sahte (fixture) davranisla
    gerceklemek. Test, beklenen cagrilarin yapilip yapilmadigini dogrulayabilir.
    """

    def __init__(
        self,
        current_url: str = "about:blank",
        download_path: Optional[Path] = None,
        selector_results: Optional[Dict[str, bool]] = None,
        fail_on: Optional[List[str]] = None,
    ):
        # Onceden ayarlanabilir davranislar (fixtures)
        self._current_url = current_url
        self._download_path = download_path or Path("mock_download.xlsx")
        self._selector_results = selector_results or {}
        self._fail_on = set(fail_on or [])

        # Gozlemlenebilir cagri kayitlari (test dogrulamasi icin)
        self.calls: List[Tuple[str, tuple]] = []
        self.goto_urls: List[str] = []
        self.clicks: List[str] = []
        self.fills: List[Tuple[str, str]] = []
        self.screenshots: List[Path] = []
        self.saved_doms: List[Path] = []
        self.closed: bool = False
        self._handlers: List[ResponseHandler] = []

    def _record(self, name: str, *args) -> None:
        self.calls.append((name, args))
        if name in self._fail_on:
            raise DriverOperationError(f"MockDriver: '{name}' bilincli olarak basarisiz.")

    # --- BrowserDriver sozlesmesi ---

    def goto(self, url: str, timeout_ms: Optional[int] = None) -> None:
        self._record("goto", url)
        self.goto_urls.append(url)
        self._current_url = url

    def click(self, selector: str, timeout_ms: Optional[int] = None) -> None:
        self._record("click", selector)
        self.clicks.append(selector)

    def fill(self, selector: str, value: str, timeout_ms: Optional[int] = None) -> None:
        self._record("fill", selector, value)
        self.fills.append((selector, value))

    def wait_for_selector(
        self,
        selector: str,
        state: WaitState = WaitState.VISIBLE,
        timeout_ms: Optional[int] = None,
    ) -> bool:
        self._record("wait_for_selector", selector, state)
        # Varsayilan: selector mevcut kabul edilir; aksi fixture ile ayarlanir.
        return self._selector_results.get(selector, True)

    def wait_for_download(self, timeout_ms: Optional[int] = None) -> Path:
        self._record("wait_for_download")
        return self._download_path

    def screenshot(self, path: Path, full_page: bool = False) -> Path:
        self._record("screenshot", path)
        self.screenshots.append(path)
        return path

    def save_dom(self, path: Path) -> Path:
        self._record("save_dom", path)
        self.saved_doms.append(path)
        return path

    def current_url(self) -> str:
        self._record("current_url")
        return self._current_url

    def on_response(self, handler: ResponseHandler) -> None:
        self._record("on_response")
        self._handlers.append(handler)

    def close(self) -> None:
        self._record("close")
        self.closed = True

    # --- Test yardimcilari (sozlesme disi) ---

    def emit_response(self, record: NetworkRecord) -> None:
        """Neden: Testte ag yaniti gozlemcilerini tetiklemek icin sahte olay yaymak."""
        for handler in self._handlers:
            handler(record)

    def was_called(self, name: str) -> bool:
        return any(call[0] == name for call in self.calls)
