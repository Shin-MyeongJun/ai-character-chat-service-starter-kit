# 격리 DB에서 0019 전후 기존 URL 보존과 관리 미디어가 있을 때 downgrade 거절을 확인한다.
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


async def migration_sql(direction, revisions):
    return await asyncio.to_thread(
        subprocess.check_output,
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ROOT / "apps/api/alembic.ini"),
            direction,
            revisions,
            "--sql",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_media_migration_preserves_legacy_urls_and_guards_rollback(db):
    async with db.bind.connect() as conn:
        schema = await conn.scalar(text("SELECT current_schema()"))
    url = make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql")
    connection = await asyncpg.connect(url.render_as_string(hide_password=False))
    try:
        await connection.execute(f"SET search_path TO {schema}, public")
        await connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY); INSERT INTO alembic_version VALUES ('0019')"
        )
        down = await migration_sql("downgrade", "0019:0018")
        await connection.execute(down)
        owner, character, image = uuid4(), uuid4(), uuid4()
        await connection.execute(
            "INSERT INTO users(id,email) VALUES($1,'legacy-media@test.local')", owner
        )
        await connection.execute(
            "INSERT INTO characters(id,owner_id,name,persona_prompt) VALUES($1,$2,'legacy','legacy')",
            character,
            owner,
        )
        legacy_url = r"C:\legacy\unchanged.png"
        await connection.execute(
            "INSERT INTO character_images(id,character_id,emotion_tag,image_url) VALUES($1,$2,'normal',$3)",
            image,
            character,
            legacy_url,
        )
        await connection.execute(await migration_sql("upgrade", "0018:0019"))
        saved = await connection.fetchrow(
            "SELECT image_url,media_id FROM character_images WHERE id=$1", image
        )
        assert saved["image_url"] == legacy_url and saved["media_id"] is None
        await connection.execute(
            "INSERT INTO character_media(owner_id,character_id,request_id,storage_kind,storage_id,object_key,content_type,size_bytes,original_filename,purpose,sha256,state) VALUES($1,$2,$3,'test_local','test','key','image/png',1,'x.png','test','digest','pending')",
            owner,
            character,
            uuid4(),
        )
        with pytest.raises(asyncpg.RaiseError, match="Managed media exists"):
            await connection.execute(down)
        await connection.execute("ROLLBACK")
        assert await connection.fetchval("SELECT count(*) FROM character_media") == 1
    finally:
        await connection.close()
