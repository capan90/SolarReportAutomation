"""
Neden: Portal/oturum bağımlı modüller (adapter, dashboard, scheduler, jobs)
davranışsal olarak entegrasyon sprintine bırakıldı; burada yalnızca modüllerin
bozulmadan import edilebildiği doğrulanır. Bir syntax hatası, eksik bağımlılık
veya import-anı yan etkisi patlarsa bu testler pre-commit'te yakalar.
"""
import importlib

import pytest

MODULLER = [
    "app.sources.gaosb.extractor",
    "app.sources.isolarcloud.extractor",
    "app.extractors.isolar.extractor",
    "app.sources.registry",
    "app.orchestrator.etl_orchestrator",
    "app.dashboard.web_server",
    "app.scheduler.windows_scheduler",
    "app.jobs.daily_settlement_job",
    "app.jobs.monthly_settlement_job",
    "app.jobs.plant_status_job",
]


@pytest.mark.parametrize("modul_adi", MODULLER)
def test_modul_import_edilebilir(modul_adi):
    modul = importlib.import_module(modul_adi)
    assert modul is not None
