"""
Neden: NotificationService + policy + queue davranışını sabitlemek (smoke).
- PolicyEvaluator tmp_path'teki sentetik JSON dosyalarıyla test edilir (gerçek
  config/notification_policy.json okunmaz).
- Servis testlerinde EmailSender yerine stub enjekte edilir (SMTP yok) ve
  _save_audit monkeypatch'lenir (gerçek notification_history tablosu kirlenmez).
"""
import pytest

from app.notifications.notification_models import NotificationEvent
from app.notifications.notification_service import NotificationService
from app.notifications.policy_evaluator import NotificationPolicyEvaluator
from app.notifications.queue import InMemoryNotificationQueue


def make_event(event_type="SUCCESS"):
    return NotificationEvent(
        run_id="test-run", event_type=event_type, exit_code=0, duration_ms=1,
        machine_name="TEST", git_commit="abc", stage_summary="özet",
        validation_summary=None, attachment_path=None,
    )


class StubSender:
    """EmailSender yerine geçen kayıt tutucu — SMTP'ye asla çıkmaz."""

    def __init__(self, raise_error=False):
        self.sent_events = []
        self.raise_error = raise_error

    def send(self, event, email_profile="default"):
        if self.raise_error:
            raise RuntimeError("sentetik SMTP hatası")
        self.sent_events.append((event.event_type, email_profile))
        return True, 1, ""


@pytest.fixture
def service_factory(monkeypatch):
    """Stub sender'lı, audit'i DB yerine listeye yazan servis üretir."""

    def _make(policy_path, sender=None):
        sender = sender or StubSender()
        service = NotificationService(
            policy_evaluator=NotificationPolicyEvaluator(policy_path=policy_path),
            queue=InMemoryNotificationQueue(),
            email_sender=sender,
        )
        audits = []
        monkeypatch.setattr(
            service, "_save_audit",
            lambda *args, **kwargs: audits.append(args),
        )
        return service, sender, audits

    return _make


def test_policy_varsayilan_kurallar(tmp_path):
    # Dosya yoksa varsayılan politika: SUCCESS/LOCK_EXISTS sessiz, hatalar bildirilir
    evaluator = NotificationPolicyEvaluator(policy_path=tmp_path / "yok.json")
    assert evaluator.should_notify("SUCCESS") is False
    assert evaluator.should_notify("LOCK_EXISTS") is False
    assert evaluator.should_notify("FAILED") is True
    assert evaluator.should_notify("failed") is True  # büyük/küçük harf duyarsız
    assert evaluator.should_notify("BILINMEYEN_TIP") is True  # bilinmeyen tip → gönder


def test_policy_json_dosyasindan(tmp_path):
    policy_file = tmp_path / "policy.json"
    policy_file.write_text('{"policies": {"SUCCESS": true, "FAILED": false}}', encoding="utf-8")
    evaluator = NotificationPolicyEvaluator(policy_path=policy_file)
    assert evaluator.should_notify("SUCCESS") is True
    assert evaluator.should_notify("FAILED") is False


def test_policy_bozuk_json_fallback(tmp_path):
    policy_file = tmp_path / "policy.json"
    policy_file.write_text("{bozuk json!!", encoding="utf-8")
    evaluator = NotificationPolicyEvaluator(policy_path=policy_file)
    # Okunamayan dosyada varsayılanlara düşer, exception fırlatmaz
    assert evaluator.should_notify("SUCCESS") is False
    assert evaluator.should_notify("FAILED") is True


def test_queue_fifo_ve_bos():
    q = InMemoryNotificationQueue()
    assert q.is_empty() is True
    assert q.pop() is None  # boş kuyrukta bloklamadan None

    ilk, ikinci = make_event("FAILED"), make_event("SUCCESS")
    q.push(ilk)
    q.push(ikinci)
    assert q.is_empty() is False
    assert q.pop() is ilk  # FIFO
    assert q.pop() is ikinci
    assert q.pop() is None


def test_notify_policy_engeller_force_gecer(service_factory, tmp_path):
    # Varsayılan politika: SUCCESS gönderilmez
    service, sender, audits = service_factory(tmp_path / "yok.json")
    service.notify(make_event("SUCCESS"))
    assert sender.sent_events == []
    assert audits == []

    # force=True politikayı bypass eder (raporun ekli gönderimi senaryosu)
    service.notify(make_event("SUCCESS"), force=True, email_profile="daily")
    assert sender.sent_events == [("SUCCESS", "daily")]
    assert len(audits) == 1

    # FAILED politika gereği normal yoldan gönderilir
    service.notify(make_event("FAILED"))
    assert ("FAILED", "default") in sender.sent_events


def test_notify_best_effort_pipeline_bozulmaz(service_factory, tmp_path):
    # Sender patlasa bile notify() exception fırlatmamalı (ana pipeline korunur)
    service, _, _ = service_factory(tmp_path / "yok.json", sender=StubSender(raise_error=True))
    service.notify(make_event("FAILED"))  # raise etmemeli
