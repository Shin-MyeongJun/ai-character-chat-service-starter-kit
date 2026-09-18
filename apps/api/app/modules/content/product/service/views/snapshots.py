# 캐릭터 스냅샷의 URL 참조 여부를 공개 조회로 확인한다. 파일 삭제나 저장소 조회는 하지 않는다.
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import query as CharacterQueryService
from app.modules.content.product import types as Types


async def check_media_reference(
    session, command: Types.MediaIsReferencedCommand
) -> Types.MediaReferenceView:
    url = command.url
    info = await CharacterQueryService.check_media_reference(
        session, CharacterTypes.CheckMediaReferenceCommand(url)
    )
    return Types.MediaReferenceView(info.referenced)
