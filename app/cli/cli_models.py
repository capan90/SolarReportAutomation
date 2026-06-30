from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class CliArgs:
    """
    Neden: Komut satırından gelen parametreleri tip güvenli bir şekilde
    temsil etmek ve uygulama içinde taşımak.
    """
    mode: str  # 'daily' veya 'dry-run'
    date: Optional[str]  # 'YYYY-MM-DD'
    skip_download: bool
    skip_db_load: bool
    headless: bool
    health: bool = False
    source: Optional[str] = None
