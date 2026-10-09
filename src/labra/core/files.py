"""Stored files: metadata in `stored_file`, bytes in whichever FileStore is configured."""

import hashlib
import uuid

from sqlalchemy.orm import Session

from labra.core.errors import NotFoundError
from labra.core.models import StoredFile
from labra.core.ports import FileStore

MAX_BYTES = 20 * 1024 * 1024


def save_file(
    db: Session,
    store: FileStore,
    data: bytes,
    filename: str,
    mime: str,
    user_id: uuid.UUID | None,
) -> StoredFile:
    if len(data) > MAX_BYTES:
        raise ValueError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    blob = store.put(data)
    row = StoredFile(
        sha256=blob.sha256,
        storage_key=blob.key,
        size=blob.size,
        filename=filename[:255],
        mime=mime,
        created_by=user_id,
    )
    db.add(row)
    db.flush()
    return row


def read_file(db: Session, store: FileStore, file_id: uuid.UUID) -> tuple[StoredFile, bytes]:
    """The file and its bytes. Refuses bytes that no longer match their recorded hash."""
    row = db.get(StoredFile, file_id)
    if row is None:
        raise NotFoundError()
    data = store.get(row.storage_key)
    if hashlib.sha256(data).hexdigest() != row.sha256:
        raise NotFoundError("The stored file is damaged. Restore it from a backup.")
    return row, data
