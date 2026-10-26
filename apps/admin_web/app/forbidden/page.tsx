import { Brand } from "@/components/ui";
import { LogoutButton } from "@/components/logout-button";
export default function Page() { return <main className="forbidden-page"><Brand /><div><span className="eyebrow">관리자 전용</span><h1>접근 권한이 없습니다.</h1><p>이 화면은 관리자 권한이 있는 계정만 이용할 수 있습니다.<br />계정의 접근 권한을 확인해 주세요.</p><LogoutButton label="로그아웃 후 다시 로그인" /></div></main>; }
