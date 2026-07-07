"""
ParsingStrategy - indirilen ham dosyanin ayristirilmasi sozlesmesi.

Neden: Ham dosya formati portala gore degisir (Excel, CSV, farkli kolon
adlari/dilleri). Ayristirmayi indirme akisindan ayirmak (SRP); boylece ayni
indirme stratejisi farkli parser'larla eslestirilebilir.

Kapsam siniri: Bu sozlesme canonical model DONUSUMU icermez. Cikti, portal
bagimsiz ara temsildir (or. satir listesi); canonical esleme ayri bir
katmanin sorumlulugudur.
"""

from abc import ABC, abstractmethod

from app.portal_framework.models.results import DownloadRecord, StepResult
from app.portal_framework.models.session_context import SessionContext


class ParsingStrategy(ABC):
    """
    Neden: 'Indirilen dosya nasil okunur?' sorusunu portal bagimsiz tek bir
    yontem arkasina almak.
    """

    @abstractmethod
    def parse(self, ctx: SessionContext, download: DownloadRecord) -> StepResult:
        """
        Indirilen dosyayi ayristirir; sonuc StepResult.data icinde tasinir.

        DownloadRecord parametre olarak acikca gecirilir; ctx.downloads'a
        ortulu bagimlilik kurulmaz (test edilebilirlik).
        """
