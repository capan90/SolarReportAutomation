"""
Neden: Smoke testlerin ortak altyapısı.
- Proje kökünü sys.path'e ekler (testler "app." importlarını bulabilsin).
- SMTP_ENABLED=false zorlar: app.core.config .env'i os.environ.setdefault ile
  yüklediğinden, buradaki atama .env'deki değeri ezer — testlerden asla gerçek
  e-posta gönderilemez. Bu blok, herhangi bir app importundan ÖNCE çalışmalıdır.
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["SMTP_ENABLED"] = "false"
