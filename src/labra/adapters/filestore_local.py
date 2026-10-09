import hashlib
import os
import tempfile
from pathlib import Path
from typing import Self

from labra.core.config import Settings
from labra.core.errors import ConfigError, NotFoundError
from labra.core.ports import StoredBlob


class LocalFileStore:
    """Files on local disk under `<root>/<ab>/<cd>/<sha256>`. Writing the same bytes twice
    stores them once."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        if not settings.files_dir.is_absolute():
            raise ConfigError("LABRA_FILES_DIR must be an absolute path.")
        return cls(settings.files_dir)

    def _path(self, key: str) -> Path:
        if len(key) != 64 or not all(c in "0123456789abcdef" for c in key):
            raise NotFoundError()
        return self.root / key[:2] / key[2:4] / key

    def put(self, data: bytes) -> StoredBlob:
        key = hashlib.sha256(data).hexdigest()
        path = self._path(key)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write to a temporary file and rename, so a crash never leaves half a file.
            fd, tmp = tempfile.mkstemp(dir=path.parent)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            Path(tmp).replace(path)
        return StoredBlob(sha256=key, size=len(data), key=key)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFoundError()
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except NotFoundError:
            return False
