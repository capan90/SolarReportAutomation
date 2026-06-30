import threading
from typing import Optional
from app.sources.models import SourceContext

# Thread-local depolama alanı (çoklu iş parçacığı güvenliği için)
_local_context = threading.local()

def set_source_context(context: SourceContext) -> None:
    """Aktif thread üzerinde kaynak bağlamını (context) set eder."""
    _local_context.active_context = context

def get_source_context() -> Optional[SourceContext]:
    """Aktif thread üzerindeki kaynak bağlamını döner."""
    return getattr(_local_context, "active_context", None)

def clear_source_context() -> None:
    """Kaynak bağlamını temizler."""
    if hasattr(_local_context, "active_context"):
        delattr(_local_context, "active_context")
