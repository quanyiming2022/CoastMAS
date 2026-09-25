"""Explicit isolated runtime settings; never fall back to the legacy database."""

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    storage_root: Path
    runtime_catalog: Path | None = None
    web_root: Path | None = None
    secure_cookies: bool = False
    max_upload_bytes: int = 2 * 1024**3
    local_sources: tuple[Path, ...] = ()
    upload_chunk_bytes: int = 8 * 1024**2
    preview_size: int = 768
    display_warp_mib: int = 64

    def __post_init__(self):
        if not 64 <= self.preview_size <= 2048 or not 16 <= self.display_warp_mib <= 256:
            raise ValueError("display budgets must stay bounded")
        if not 1 <= self.upload_chunk_bytes <= 16 * 1024**2:
            raise ValueError("upload chunks must fit the bounded transfer budget")
        url = make_url(self.database_url)
        if url.get_backend_name() != "sqlite" and not (url.database or "").startswith(
            "coastmas_next_"
        ):
            raise ValueError("new runtime requires a coastmas_next_ database namespace")
        object.__setattr__(self, "storage_root", self.storage_root.resolve())
