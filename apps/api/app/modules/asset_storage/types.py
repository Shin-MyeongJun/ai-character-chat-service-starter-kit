from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, ClassVar, Protocol, Self, runtime_checkable


class StorageKind(StrEnum):
    TEST_LOCAL = "test_local"
    S3 = "s3"


class ExecutionEnvironment(StrEnum):
    TEST = "test"
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class AssetStorageErrorKind(StrEnum):
    NOT_FOUND = "not_found"
    ACCESS_DENIED = "access_denied"
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    INVALID_REQUEST = "invalid_request"
    DATA_INTEGRITY = "data_integrity"
    PROVIDER = "provider"


class AssetStorageError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: AssetStorageErrorKind,
        operation: str,
        object_key: str,
        retryable: bool = False,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.operation = operation
        self.object_key = object_key
        self.retryable = retryable
        self.status_code = status_code
        self.request_id = request_id


class AssetNotFoundError(AssetStorageError):
    pass


class AssetStorageConfigurationError(ValueError):
    pass


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_INVALID_SEGMENT_CHARACTERS = frozenset('<>:"\\|?*')


def _validate_object_key(object_key: str) -> None:
    if not isinstance(object_key, str) or not object_key:
        raise ValueError("object_key must be a non-empty string.")
    if object_key.startswith("/") or object_key.endswith("/"):
        raise ValueError("object_key must be a relative object key.")
    if len(object_key.encode("utf-8")) > 1024:
        raise ValueError("object_key must not exceed 1024 UTF-8 bytes.")
    segments = object_key.split("/")
    if segments[0] == ".asset_storage":
        raise ValueError("object_key uses a reserved module path.")
    for segment in segments:
        if segment in {"", ".", ".."}:
            raise ValueError("object_key contains an invalid path segment.")
        if segment.endswith((" ", ".")):
            raise ValueError("object_key segments may not end with a space or dot.")
        if any(character in _INVALID_SEGMENT_CHARACTERS for character in segment):
            raise ValueError("object_key contains a non-portable path character.")
        if any(ord(character) < 32 for character in segment):
            raise ValueError("object_key contains a control character.")
        stem = segment.split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            raise ValueError("object_key contains a reserved Windows path name.")


@dataclass(frozen=True, slots=True)
class StoreAssetCommand:
    object_key: str
    content: BinaryIO = field(repr=False, compare=False)
    size_bytes: int
    content_type: str

    def __post_init__(self) -> None:
        _validate_object_key(self.object_key)
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be zero or greater.")
        if not callable(getattr(self.content, "read", None)):
            raise TypeError("content must be a readable binary stream.")
        if not self.content_type.strip():
            raise ValueError("content_type must be non-blank.")
        if "\r" in self.content_type or "\n" in self.content_type:
            raise ValueError("content_type must not contain line breaks.")


@dataclass(frozen=True, slots=True)
class ReadAssetCommand:
    object_key: str

    def __post_init__(self) -> None:
        _validate_object_key(self.object_key)


@dataclass(frozen=True, slots=True)
class DeleteAssetCommand:
    object_key: str

    def __post_init__(self) -> None:
        _validate_object_key(self.object_key)


@dataclass(frozen=True, slots=True)
class GetAssetMetadataCommand:
    object_key: str

    def __post_init__(self) -> None:
        _validate_object_key(self.object_key)


@dataclass(frozen=True, slots=True)
class StoredAssetInfo:
    storage_kind: StorageKind
    storage_id: str
    object_key: str
    size_bytes: int
    content_type: str
    etag: str | None = None
    last_modified: datetime | None = None


@dataclass(frozen=True, slots=True)
class AssetMetadataInfo:
    storage_kind: StorageKind
    storage_id: str
    object_key: str
    size_bytes: int
    content_type: str
    etag: str | None = None
    last_modified: datetime | None = None


@runtime_checkable
class AsyncAssetReader(Protocol):
    async def read(self, size: int = -1) -> bytes: ...

    async def aclose(self) -> None: ...


@dataclass(slots=True)
class AssetReadInfo:
    metadata: AssetMetadataInfo
    _reader: AsyncAssetReader = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    async def read(self, size: int = -1) -> bytes:
        if self._closed:
            raise ValueError("The asset reader is closed.")
        return await self._reader.read(size)

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            await self._reader.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


@runtime_checkable
class AssetStorageAdapter(Protocol):
    storage_kind: StorageKind
    storage_id: str

    async def store_asset(self, command: StoreAssetCommand) -> StoredAssetInfo: ...

    async def read_asset(self, command: ReadAssetCommand) -> AssetReadInfo: ...

    async def delete_asset(self, command: DeleteAssetCommand) -> None: ...

    async def get_asset_metadata(
        self, command: GetAssetMetadataCommand
    ) -> AssetMetadataInfo: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class TestLocalStorageSettings:
    __test__: ClassVar[bool] = False
    storage_id: str = "test-local-default"
    root: Path = Path(r"C:\testChatData")

    def __post_init__(self) -> None:
        if not self.storage_id.strip():
            raise AssetStorageConfigurationError("storage_id must be non-blank.")
        if not self.root.is_absolute():
            raise AssetStorageConfigurationError(
                "TestLocalStorageSettings.root must be an absolute path."
            )


@dataclass(frozen=True, slots=True)
class S3StorageSettings:
    storage_id: str
    bucket: str
    region: str
    key_prefix: str = ""
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 60.0
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.storage_id.strip():
            raise AssetStorageConfigurationError("storage_id must be non-blank.")
        if not self.bucket.strip():
            raise AssetStorageConfigurationError("S3 bucket must be non-blank.")
        if not self.region.strip():
            raise AssetStorageConfigurationError("S3 region must be non-blank.")
        if self.key_prefix.startswith("/") or self.key_prefix.endswith("/"):
            raise AssetStorageConfigurationError(
                "S3 key_prefix must not start or end with '/'."
            )
        if self.key_prefix:
            try:
                _validate_object_key(self.key_prefix)
            except ValueError as exc:
                raise AssetStorageConfigurationError(
                    f"Invalid S3 key_prefix: {exc}"
                ) from exc
        if self.connect_timeout_seconds <= 0 or self.read_timeout_seconds <= 0:
            raise AssetStorageConfigurationError("S3 timeouts must be positive.")
        if self.max_attempts < 1:
            raise AssetStorageConfigurationError(
                "S3 max_attempts must be at least one."
            )


@dataclass(frozen=True, slots=True)
class AssetStorageSettings:
    environment: ExecutionEnvironment
    storage_kind: StorageKind
    test_local: TestLocalStorageSettings | None = None
    s3: S3StorageSettings | None = None

    def __post_init__(self) -> None:
        try:
            environment = ExecutionEnvironment(self.environment)
            storage_kind = StorageKind(self.storage_kind)
        except ValueError as exc:
            raise AssetStorageConfigurationError(str(exc)) from exc
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "storage_kind", storage_kind)
        if (
            environment is ExecutionEnvironment.PRODUCTION
            and storage_kind is StorageKind.TEST_LOCAL
        ):
            raise AssetStorageConfigurationError(
                "test_local asset storage is forbidden in production."
            )
        if storage_kind is StorageKind.TEST_LOCAL and self.test_local is None:
            raise AssetStorageConfigurationError(
                "test_local settings are required when test_local is selected."
            )
        if storage_kind is StorageKind.S3 and self.s3 is None:
            raise AssetStorageConfigurationError(
                "S3 settings are required when s3 is selected."
            )
