from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

import boto3
from boto3.s3.transfer import S3UploadFailedError, TransferConfig
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    PartialCredentialsError,
    ProxyConnectionError,
    ReadTimeoutError,
)

from app.modules.asset_storage.types import (
    AssetMetadataInfo,
    AssetNotFoundError,
    AssetReadInfo,
    AssetStorageError,
    AssetStorageErrorKind,
    DeleteAssetCommand,
    GetAssetMetadataCommand,
    ReadAssetCommand,
    S3StorageSettings,
    StorageKind,
    StoreAssetCommand,
    StoredAssetInfo,
)


class _S3AssetReader:
    def __init__(
        self,
        body: Any,
        error_mapper: Callable[[Exception], AssetStorageError],
    ) -> None:
        self._body = body
        self._error_mapper = error_mapper

    async def read(self, size: int = -1) -> bytes:
        try:
            return await asyncio.to_thread(self._body.read, size)
        except BotoCoreError as exc:
            raise self._error_mapper(exc) from exc

    async def aclose(self) -> None:
        try:
            await asyncio.to_thread(self._body.close)
        except BotoCoreError as exc:
            raise self._error_mapper(exc) from exc


class S3StorageAdapter:
    storage_kind = StorageKind.S3

    def __init__(
        self,
        settings: S3StorageSettings,
        *,
        client: Any | None = None,
    ) -> None:
        self._settings = settings
        self.storage_id = settings.storage_id
        self._owns_client = client is None
        self._client = client or boto3.client(
            "s3",
            region_name=settings.region,
            config=Config(
                connect_timeout=settings.connect_timeout_seconds,
                read_timeout=settings.read_timeout_seconds,
                retries={
                    "mode": "standard",
                    "total_max_attempts": settings.max_attempts,
                },
            ),
        )
        # The whole managed transfer runs off the event loop. Disabling its nested
        # thread pool also makes non-seekable caller streams safe to consume once.
        self._transfer_config = TransferConfig(use_threads=False)

    def _provider_key(self, object_key: str) -> str:
        if self._settings.key_prefix:
            provider_key = f"{self._settings.key_prefix}/{object_key}"
        else:
            provider_key = object_key
        if len(provider_key.encode("utf-8")) > 1024:
            raise ValueError("The S3 prefix and object_key exceed 1024 UTF-8 bytes.")
        return provider_key

    @staticmethod
    def _validate_seekable_size(command: StoreAssetCommand) -> None:
        stream = command.content
        try:
            position = stream.tell()
            stream.seek(0, 2)
            remaining = stream.tell() - position
            stream.seek(position)
        except (AttributeError, OSError):
            return
        if remaining != command.size_bytes:
            raise AssetStorageError(
                "The stream length does not match size_bytes.",
                kind=AssetStorageErrorKind.DATA_INTEGRITY,
                operation="store",
                object_key=command.object_key,
            )

    def _map_error(
        self, exc: Exception, *, operation: str, object_key: str
    ) -> AssetStorageError:
        status_code = None
        request_id = None
        error_code = None
        if isinstance(exc, ClientError):
            response = exc.response
            metadata = response.get("ResponseMetadata", {})
            status_code = metadata.get("HTTPStatusCode")
            request_id = metadata.get("RequestId")
            error_code = str(response.get("Error", {}).get("Code", ""))

        if error_code in {"NoSuchKey", "NotFound", "404"} or status_code == 404:
            return AssetNotFoundError(
                f"Asset {object_key!r} was not found.",
                kind=AssetStorageErrorKind.NOT_FOUND,
                operation=operation,
                object_key=object_key,
                status_code=status_code,
                request_id=request_id,
            )
        if isinstance(exc, (NoCredentialsError, PartialCredentialsError)) or error_code in {
            "AccessDenied",
            "InvalidAccessKeyId",
            "SignatureDoesNotMatch",
            "ExpiredToken",
        }:
            kind, retryable = AssetStorageErrorKind.ACCESS_DENIED, False
        elif isinstance(exc, (ConnectTimeoutError, ReadTimeoutError)) or error_code in {
            "RequestTimeout",
            "RequestTimeoutException",
        }:
            kind, retryable = AssetStorageErrorKind.TIMEOUT, True
        elif isinstance(
            exc,
            (
                EndpointConnectionError,
                ConnectionClosedError,
                ProxyConnectionError,
            ),
        ):
            kind, retryable = AssetStorageErrorKind.CONNECTION, True
        elif status_code is not None and 400 <= status_code < 500:
            kind, retryable = AssetStorageErrorKind.INVALID_REQUEST, False
        else:
            kind = AssetStorageErrorKind.PROVIDER
            retryable = status_code is None or status_code >= 500
        return AssetStorageError(
            f"S3 {operation} failed for asset {object_key!r}.",
            kind=kind,
            operation=operation,
            object_key=object_key,
            retryable=retryable,
            status_code=status_code,
            request_id=request_id,
        )

    @staticmethod
    def _metadata_from_response(
        response: dict[str, Any],
        *,
        storage_id: str,
        object_key: str,
    ) -> AssetMetadataInfo:
        etag = response.get("ETag")
        return AssetMetadataInfo(
            storage_kind=StorageKind.S3,
            storage_id=storage_id,
            object_key=object_key,
            size_bytes=int(response["ContentLength"]),
            content_type=str(response.get("ContentType") or "application/octet-stream"),
            etag=str(etag).strip('"') if etag is not None else None,
            last_modified=(
                response.get("LastModified")
                if isinstance(response.get("LastModified"), datetime)
                else None
            ),
        )

    def _parse_metadata(
        self,
        response: dict[str, Any],
        *,
        operation: str,
        object_key: str,
    ) -> AssetMetadataInfo:
        try:
            return self._metadata_from_response(
                response,
                storage_id=self.storage_id,
                object_key=object_key,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AssetStorageError(
                f"S3 returned invalid metadata for asset {object_key!r}.",
                kind=AssetStorageErrorKind.PROVIDER,
                operation=operation,
                object_key=object_key,
            ) from exc

    async def store_asset(self, command: StoreAssetCommand) -> StoredAssetInfo:
        self._validate_seekable_size(command)
        try:
            await asyncio.to_thread(
                self._client.upload_fileobj,
                Fileobj=command.content,
                Bucket=self._settings.bucket,
                Key=self._provider_key(command.object_key),
                ExtraArgs={"ContentType": command.content_type},
                Config=self._transfer_config,
            )
        except AssetStorageError:
            raise
        except (ClientError, BotoCoreError, S3UploadFailedError) as exc:
            raise self._map_error(
                exc, operation="store", object_key=command.object_key
            ) from exc
        return StoredAssetInfo(
            storage_kind=self.storage_kind,
            storage_id=self.storage_id,
            object_key=command.object_key,
            size_bytes=command.size_bytes,
            content_type=command.content_type,
        )

    async def read_asset(self, command: ReadAssetCommand) -> AssetReadInfo:
        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                Bucket=self._settings.bucket,
                Key=self._provider_key(command.object_key),
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._map_error(
                exc, operation="read", object_key=command.object_key
            ) from exc
        try:
            metadata = self._parse_metadata(
                response, operation="read", object_key=command.object_key
            )
        except AssetStorageError:
            body = response.get("Body")
            if callable(getattr(body, "close", None)):
                await asyncio.to_thread(body.close)
            raise
        return AssetReadInfo(
            metadata,
            _S3AssetReader(
                response["Body"],
                lambda exc: self._map_error(
                    exc, operation="read", object_key=command.object_key
                ),
            ),
        )

    async def delete_asset(self, command: DeleteAssetCommand) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete_object,
                Bucket=self._settings.bucket,
                Key=self._provider_key(command.object_key),
            )
        except (ClientError, BotoCoreError) as exc:
            mapped = self._map_error(
                exc, operation="delete", object_key=command.object_key
            )
            if mapped.kind is AssetStorageErrorKind.NOT_FOUND:
                return
            raise mapped from exc

    async def get_asset_metadata(
        self, command: GetAssetMetadataCommand
    ) -> AssetMetadataInfo:
        try:
            response = await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._settings.bucket,
                Key=self._provider_key(command.object_key),
            )
        except (ClientError, BotoCoreError) as exc:
            raise self._map_error(
                exc, operation="metadata", object_key=command.object_key
            ) from exc
        return self._parse_metadata(
            response,
            operation="metadata",
            object_key=command.object_key,
        )

    async def aclose(self) -> None:
        if self._owns_client and callable(getattr(self._client, "close", None)):
            await asyncio.to_thread(self._client.close)
