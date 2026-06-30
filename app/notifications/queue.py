from abc import ABC, abstractmethod
import queue
from typing import Optional
from app.notifications.notification_models import NotificationEvent

class INotificationQueue(ABC):
    """
    Neden: Bildirim gönderim süreçlerini asenkronlaştırabilmek veya 
    arka plana alabilmek için kuyruk arayüzü sözleşmesini tanımlamak (SOLID - Dependency Inversion).
    """
    @abstractmethod
    def push(self, event: NotificationEvent) -> None:
        pass

    @abstractmethod
    def pop(self) -> Optional[NotificationEvent]:
        pass

    @abstractmethod
    def is_empty(self) -> bool:
        pass

class InMemoryNotificationQueue(INotificationQueue):
    """
    Neden: Projenin mevcut aşamasında thread-safe ve hafif bir in-memory 
    bildirim kuyruğu sağlayarak Redis/RabbitMQ geçişlerini kolaylaştırmak.
    """
    def __init__(self):
        self._queue = queue.Queue()

    def push(self, event: NotificationEvent) -> None:
        self._queue.put(event)

    def pop(self) -> Optional[NotificationEvent]:
        try:
            # Bloklama olmadan sıradaki bildirimi al
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def is_empty(self) -> bool:
        return self._queue.empty()
