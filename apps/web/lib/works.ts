export type Work = {
  id: string;
  title: string;
  subtitle: string;
  genre: string;
  tags: string[];
  author: string;
  color: string;
  accent: string;
  symbol: string;
  popularity: string;
  badge?: string;
  coverImage?: string;
  opening: string;
  startOptions: { id: string; title: string; preview: string }[];
};

export const demoWorks: Work[] = [
  {
    id: "demo-archive",
    coverImage: "/images/stories/archive.png",
    title: "밤의 기록 보관소",
    subtitle: "사라진 기억을 보관하는 도서관에서 당신 앞으로 온 편지 한 통.",
    genre: "미스터리",
    tags: ["도서관", "비밀", "판타지"],
    author: "별의서재",
    color: "#151b31",
    accent: "#c3a77b",
    symbol: "✧",
    popularity: "2.4k",
    badge: "EDITOR'S PICK",
    opening:
      "자정이 넘자 보관소의 시계가 열세 번 울렸다. 책장 사이에서 누군가 당신의 이름을 불렀다. 돌아보니 낯선 편지가 바닥에 놓여 있었다.",
    startOptions: [
      { id: "letter", title: "편지를 열어본다", preview: "봉투에는 오래전 잊은 필체로 당신의 이름이 적혀 있다." },
      { id: "voice", title: "목소리를 따라간다", preview: "꺼진 등 뒤로 희미한 발소리가 이어진다." },
    ],
  },
  {
    id: "demo-bluehour",
    coverImage: "/images/stories/bluehour.png",
    title: "푸른 시간의 역",
    subtitle: "막차가 떠난 플랫폼에서 다시 만난 오래된 친구.",
    genre: "로맨스",
    tags: ["재회", "현대", "감성"],
    author: "유월",
    color: "#315478",
    accent: "#d7c6b0",
    symbol: "☾",
    popularity: "1.8k",
    opening:
      "마지막 열차가 떠난 뒤에도 플랫폼에는 네가 남아 있었다. 바람에 흩날린 머리카락을 넘기며 네가 웃는다. ‘정말 올 줄은 몰랐어.’",
    startOptions: [{ id: "platform", title: "플랫폼에서", preview: "서로 할 말이 많지만, 첫마디는 쉽지 않다." }],
  },
  {
    id: "demo-garden",
    coverImage: "/images/stories/garden.png",
    title: "유리 온실의 계약",
    subtitle: "꽃이 사람의 비밀을 기억한다는 도시의 작은 온실.",
    genre: "판타지",
    tags: ["마법", "힐링", "계약"],
    author: "온실지기",
    color: "#275047",
    accent: "#e0b9a0",
    symbol: "❋",
    popularity: "980",
    badge: "NEW",
    opening:
      "비를 피해 들어온 온실은 이상할 만큼 따뜻했다. 주인이 빈 화분 하나를 내밀며 말했다. ‘여기에 묻고 싶은 이야기가 있으신가요?’",
    startOptions: [{ id: "rain", title: "비 오는 오후", preview: "유리 지붕을 두드리는 빗소리만 들린다." }],
  },
  {
    id: "demo-radio",
    coverImage: "/images/stories/radio.png",
    title: "새벽 2시 라디오",
    subtitle: "전파가 닿지 않는 곳에서 들려온 당신만의 방송.",
    genre: "일상",
    tags: ["라디오", "새벽", "대화"],
    author: "모노",
    color: "#6a3c47",
    accent: "#f1bd83",
    symbol: "◉",
    popularity: "3.1k",
    opening:
      "잡음 사이로 목소리가 흘러나왔다. ‘여기는 새벽 두 시, 당신에게만 들리는 방송입니다. 오늘은 어떤 하루였나요?’",
    startOptions: [{ id: "signal", title: "주파수를 맞춘다", preview: "작은 다이얼을 돌리자 음악이 멈춘다." }],
  },
  {
    id: "demo-orbit",
    title: "우주의 끝에서",
    subtitle: "조난 신호를 보낸 우주선에는 한 사람만 남아 있었다.",
    genre: "SF",
    tags: ["우주", "탐사", "선택"],
    author: "궤도",
    color: "#263a57",
    accent: "#a7c4d5",
    symbol: "✦",
    popularity: "1.2k",
    opening:
      "통신이 연결되자 화면에는 고장 난 조종석이 보였다. 상대가 카메라를 올려다본다. ‘아직 누군가 듣고 있었군요.’",
    startOptions: [{ id: "signal", title: "구조 신호", preview: "수신 좌표는 지도에 표시되지 않는 구역을 가리킨다." }],
  },
  {
    id: "demo-cafe",
    title: "계절을 파는 카페",
    subtitle: "다시 만나고 싶은 날의 날씨를 주문할 수 있다면.",
    genre: "힐링",
    tags: ["카페", "마법", "일상"],
    author: "서쪽창가",
    color: "#845e45",
    accent: "#efd0a4",
    symbol: "✿",
    popularity: "760",
    opening:
      "작은 종이 울리며 문이 열렸다. 메뉴판에는 커피 대신 계절이 적혀 있었다. ‘오늘은 어떤 날을 다시 만나고 싶으세요?’",
    startOptions: [{ id: "menu", title: "메뉴판 앞에서", preview: "봄, 여름, 가을, 겨울. 단 하나만 고를 수 있다." }],
  },
];

export const demoWorkById = (id: string) => demoWorks.find((work) => work.id === id);

export function isDemoWork(id: string): boolean {
  return id.startsWith("demo-");
}
