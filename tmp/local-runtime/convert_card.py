"""One-off local conversion: retain nonsexual narrative, never execute card code."""
import json
import re
from pathlib import Path
from uuid import uuid4

root = Path(__file__).parent
card = json.loads((root / 'source-card.json').read_text(encoding='utf-8'))['data']
source = card['character_book']['entries']
blocked = re.compile(
    r'\bsex\w*|breast|\bbust\b|\bcup\b|\bhips?\b|butt|\bass\b|virgin|lust|arous|nude|naked|'
    r'genital|penis|vagin|nipple|erotic|horny|nsfw|fetish|\brape\b|\braping\b|orgasm|intercourse|'
    r'kiss|romantic|libido|seduc|sensual|\blover\b|\bchest\b|\bthigh|\bcurv|'
    r'\bintimat|\bmoan|\bpanties|\bunderwear|\blingerie|\bejac|\bsemen|'
    r'성적|가슴|성기|섹스|음란|교미|욕정|발정|(?<![가-힣])음부(?![가-힣])|유두|정액|음경|음핵|항문|처녀', re.I)
replacements = {
    'Harry Potter': 'Harriet Potter', '해리 포터': '해리엇 포터',
    'Ron Weasley': 'Rona Weasley', '론 위즐리': '로나 위즐리',
    'Draco Malfoy': 'Karina Malfoy', '드레이코 말포이': '카리나 말포이',
    'Sirius Black': 'Siriana Black', '시리우스 블랙': '시리아나 블랙',
    'Remus Lupin': 'Lynessa Lupin', '리무스 루핀': '리네사 루핀',
    'Severus Snape': 'Severa Snape', '세베루스 스네이프': '세베라 스네이프',
    'Rubeus Hagrid': 'Rubina Hagrid', '루베우스 해그리드': '루비나 해그리드',
}
removed = {}

def clean(text, label):
    kept = []
    count = 0
    for line in text.splitlines():
        if blocked.search(line):
            count += 1
            continue
        if re.match(r'^\s*(Appearance|Physical|Height|Weight|Her physical|Her Characteristics|Features of her|Dress at home)', line, re.I):
            count += 1
            continue
        # Risu control lines cannot run in this application's prompt system.
        if line.lstrip().startswith(('{{#', '{{/', '{{else', '@@', '$firstmessage')):
            continue
        if '→' in line:
            continue
        line = re.sub(r'\{\{#if.*?\}\}\}\}', '', line)
        line = line.replace('{{/if}}', '').replace('{{/}}', '')
        if re.search(r'\{\{(?:getvar|equal|all|any|\?|setvar)::?', line):
            continue
        for old, new in replacements.items():
            line = line.replace(old, new)
        kept.append(line)
    removed[label] = count
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(kept)).strip()

def character(name, persona, role='登場人物'):
    return {'id': str(uuid4()), 'name': name, 'role': role,
            'introduction': f'{name} · Hogwarts -IF- 비성적 모험 설정',
            'persona': persona, 'dialogue': '', 'relationships': '',
            'tags': ['호그와트'], 'assets': []}

chars = [character('호그와트 이야기 진행자',
    '마법학교의 일상, 수업, 탐험과 수수께끼를 진행한다. 독자의 행동과 감정을 대신 결정하지 않는다. '
    '장면에 있는 인물은 독립적인 성격과 목표를 가진다. 모든 장면은 비성적인 모험이다.', '이야기 진행자')]
# Choose one TS profile per overlapping character; preserve the longer Ekrizdis.
profile_indices = [36, 38, 42, 44, 45, 46, 47, 52, 58, 59, 60, 61, 62, 63]
for index in profile_indices:
    entry = source[index]
    text = entry['content']
    if index == 61:
        # The second block is the regular Harriet variant (the first is alter).
        blocks = text.split('### TS Character Framework')
        text = '### TS Character Framework' + blocks[-1]
    name = entry['comment']
    if index == 61: name = '해리엇 포터'
    if index == 63: name = '카리나 말포이 (TS)'
    if index == 58: name = '에크리즈디스'
    persona = clean(text, name)
    if persona:
        chars.append(character(name, persona, '교수' if index in [36, 38, 42, 62] else '등장인물'))

lore = []
folder_names = {e['keys'][0]: e['comment'] for e in source
                if e.get('keys') and e['keys'][0].startswith('\uf000folder:')}
skip = set(profile_indices + [37, 43, 49, 57])
for index, entry in enumerate(source):
    if index in skip or not entry['content'].strip(): continue
    text = entry['content']
    if index == 40:
        # Remove original profiles replaced by the TS rows, retaining all other NPCs.
        text = '\n'.join(line for line in text.splitlines()
                         if not any(name in line for name in replacements))
    content = clean(text, f'lore-{index}')
    if not content: continue
    keywords = [k for k in entry.get('keys', []) if k.strip() and not k.startswith('\uf000')]
    category = '장소' if index in [17, 26] else '인물' if index == 40 else '사건' if index < 17 or 28 <= index <= 35 else '세계관'
    activation = 'always' if entry.get('constant') or not keywords else 'keyword'
    # Preserve all chapter timelines but activate only the first book for the default start.
    if 30 <= index <= 35 or index == 54: activation = 'manual'
    lore.append({'id': str(uuid4()), 'title': entry['comment'], 'category': category,
        'folder': folder_names.get(entry.get('folder'), '가져온 자료'), 'content': content,
        'tags': ['CHARX'], 'keywords': list(dict.fromkeys(keywords)),
        'enabled': bool(entry.get('enabled', True)), 'activation': activation, 'match': 'any',
        'priority': '보통', 'scanDepth': 9, 'searchTarget': 'all', 'partialMatch': True,
        'caseSensitive': bool(entry.get('case_sensitive', False)), 'tokenBudget': 2000,
        'order': int(entry.get('insertion_order', index)), 'placement': 'before', 'exclusiveGroup': ''})

place_id = next(row['id'] for row in lore if row['category'] == '장소')
scenes = []
markers = list(re.finditer(r'^\{\{#if_pure.*$', card['first_mes'], re.M))
scene_titles = {'m1': '킹스 크로스 역', 'm2': '호그와트 급행열차', 'm3': '입학 연회',
    'm4': '교수로 시작', 'm5': '호그와트 복도', 'm6': '금지된 숲',
    'm7': '추가 시작 7', 'm8': '추가 시작 8', 'm9': '추가 시작 9'}
for index, marker in enumerate(markers):
    condition = marker.group(0)
    language = '한국어' if '::ko' in condition else 'English'
    mode = re.search(r'first_message\}\}::(m\d+)', condition).group(1)
    text = card['first_mes'][marker.end():markers[index+1].start() if index+1 < len(markers) else None]
    # Do not republish explicit scenes, even in truncated or lightly edited form.
    if blocked.search(text):
        removed[f'scene-{language}-{mode}'] = 'excluded'
        continue
    opening = clean(text, f'scene-{language}-{mode}')
    if not opening: continue
    scenes.append({'id': str(uuid4()), 'title': f'{scene_titles[mode]} · {language}',
        'background': '1990년대 호그와트 마법학교와 마법사 세계.', 'opening': opening,
        'characterId': chars[0]['id'], 'placeId': place_id, 'initialNotes': '',
        'language': language, 'storyTime': '1991년 9월 1일' if mode in ['m1','m2','m3'] else '선택한 시작 시점',
        'perspective': '2인칭', 'variants': ''})

description = card['description'].split('### Physical Development')[0]
rules = clean(description, 'world-rules') + '\n\nTS 우선: ' + '; '.join(f'{a} 대신 {b}' for a,b in replacements.items() if a.isascii())
rules += '\n같은 인물의 non 버전은 등장하지 않는다. 비성적인 마법학교 모험만 진행한다. Risu 스크립트는 실행하지 않는다.'
post = clean(card['post_history_instructions'], 'post-history')
if post:
    lore.append({'id': str(uuid4()), 'title': '서술 지침 · 비성적 부분', 'category': '세계관', 'folder': '시스템',
        'content': post, 'tags': ['CHARX'], 'keywords': [], 'enabled': True, 'activation': 'always',
        'match': 'any', 'priority': '높음', 'scanDepth': 9, 'searchTarget': 'all',
        'partialMatch': True, 'caseSensitive': False, 'tokenBudget': 2000, 'order': 0,
        'placement': 'before', 'exclusiveGroup': ''})
project = {'version': 2, 'work': {'title': 'Hogwarts -IF- 3.1 · TS 모험 테스트',
    'introduction': '첨부 CHARX의 비성적 세계관·인물·스토리 설정을 옮긴 로컬 테스트 작품입니다. TS 중복 인물은 TS만 사용합니다.',
    'tags': ['판타지', '마법학교', 'TS', '로컬 테스트'], 'worldRules': rules,
    'visibility': '비공개', 'defaultSceneId': scenes[0]['id']},
    'characters': chars, 'scenes': scenes, 'lorebooks': lore}
(root / 'hogwarts-studio.json').write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')
summary = {'source_entries': len(source), 'characters': len(chars), 'lore_entries': len(lore),
           'scenes': len(scenes), 'text_chars': len(json.dumps(project,ensure_ascii=False)),
           'omitted_source_entries': sorted(skip), 'removed_lines': removed,
           'assets_imported': 0, 'card_assets': len(card['assets'])}
(root / 'conversion-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='removed_lines'},ensure_ascii=False))
