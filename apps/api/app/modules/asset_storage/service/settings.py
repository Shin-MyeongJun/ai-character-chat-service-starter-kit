# 저장소 환경변수를 타입 설정으로 읽는다. production에서 test_local 사용은 설정 생성 시 거절된다.
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from app.modules.asset_storage.types import (
    AssetStorageConfigurationError,
    AssetStorageSettings,
    ExecutionEnvironment,
    S3StorageSettings,
    StorageKind,
    TestLocalStorageSettings,
)


def _required(source: Mapping[str, str], name: str) -> str:
    value = source.get(name, "").strip()
    if not value:
        raise AssetStorageConfigurationError(f"{name} is required.")
    return value


def _float(source: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(source.get(name, str(default)))
    except ValueError as exc:
        raise AssetStorageConfigurationError(f"{name} must be a number.") from exc


def _int(source: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(source.get(name, str(default)))
    except ValueError as exc:
        raise AssetStorageConfigurationError(f"{name} must be an integer.") from exc


def load_asset_storage_settings(
    environ: Mapping[str, str] | None = None,
) -> AssetStorageSettings:
    """Load only this module's typed settings from an environment mapping."""

    source = os.environ if environ is None else environ
    environment_value = source.get("ENVIRONMENT", "local").strip().lower()
    if environment_value == "prod":
        environment_value = "production"
    try:
        environment = ExecutionEnvironment(environment_value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ExecutionEnvironment)
        raise AssetStorageConfigurationError(
            f"ENVIRONMENT must be one of: {allowed}."
        ) from exc

    kind_value = _required(source, "ASSET_STORAGE_KIND").lower()
    try:
        storage_kind = StorageKind(kind_value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in StorageKind)
        raise AssetStorageConfigurationError(
            f"ASSET_STORAGE_KIND must be one of: {allowed}."
        ) from exc

    if storage_kind is StorageKind.TEST_LOCAL:
        return AssetStorageSettings(
            environment=environment,
            storage_kind=storage_kind,
            test_local=TestLocalStorageSettings(
                storage_id=source.get(
                    "ASSET_STORAGE_ID", "test-local-default"
                ).strip(),
                root=Path(
                    source.get("ASSET_TEST_LOCAL_ROOT", r"C:\testChatData").strip()
                ),
            ),
        )

    return AssetStorageSettings(
        environment=environment,
        storage_kind=storage_kind,
        s3=S3StorageSettings(
            storage_id=_required(source, "ASSET_STORAGE_ID"),
            bucket=_required(source, "ASSET_S3_BUCKET"),
            region=_required(source, "ASSET_S3_REGION"),
            key_prefix=source.get("ASSET_S3_KEY_PREFIX", "").strip(),
            connect_timeout_seconds=_float(
                source, "ASSET_S3_CONNECT_TIMEOUT_SECONDS", 5.0
            ),
            read_timeout_seconds=_float(
                source, "ASSET_S3_READ_TIMEOUT_SECONDS", 60.0
            ),
            max_attempts=_int(source, "ASSET_S3_MAX_ATTEMPTS", 3),
        ),
    )
