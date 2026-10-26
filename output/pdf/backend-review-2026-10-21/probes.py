"""Synthetic checks for report findings. No database or network connection."""
import asyncio,json,sys
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock,patch
from contextlib import asynccontextmanager
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'apps/api'));sys.dont_write_bytecode=True
from pydantic import ValidationError
from fastapi import HTTPException
from app.main import create_app
from app.http import character_dependencies as cd, lorebook_dependencies as ld
from app.modules.content.product.schemas import StartOptionInfoResponseDto
from app.modules.content.lorebook.types import CreateLorebookEntryCommand
from app.modules.content.lorebook.service.command import _validate_lorebook_entry
from app.modules.content.character.service import command as cc
from app.modules.content.character import types as ct
from app.modules.governance.moderation.mapper.character import CharacterSchemaMapper
from app.http.contracts.character import ChangeCharacterStatusRequestDto
results=[]
try:
    command=CreateLorebookEntryCommand(lorebook_id=uuid4(),owner_id=uuid4(),title=None,content='Synthetic start',entry_type='start_set',activation_type='always')
    _validate_lorebook_entry(command)
    try:StartOptionInfoResponseDto(id=uuid4(),title=None)
    except ValidationError as exc:results.append(dict(id='F01',result='nullable start entry accepted; response rejects null title',errors=[e['type'] for e in exc.errors()]))
except Exception as exc:results.append(dict(id='F01',probe_error=repr(exc)))
@asynccontextmanager
async def transaction(session):yield
async def main():
    app=create_app();guards=[cd.require_character_admin,cd.require_character_moderator,ld.require_lorebook_admin,ld.require_lorebook_moderator]
    for fn in guards:
        try:await fn()
        except HTTPException as exc:results.append(dict(id='F02',guard=fn.__name__,overridden=fn in app.dependency_overrides,status=exc.status_code))
    actor,target=uuid4(),uuid4()
    cmd=CharacterSchemaMapper.change_character_status_request_to_command(ChangeCharacterStatusRequestDto(character_id=target,status='approved'),actor)
    repo=AsyncMock(return_value=None)
    with patch.object(cc,'use_case_transaction',transaction),patch.object(cc.Repository,'get_character_by_id_and_owner_id',repo):
        try:await cc.change_character_status(object(),cmd)
        except LookupError:
            results.append(dict(id='F03',result='moderator actor ID is used as target owner filter',actor_is_owner_filter=repo.await_args.args[2]==actor))
asyncio.run(main())
(OUT/'probes.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(results,ensure_ascii=False))
