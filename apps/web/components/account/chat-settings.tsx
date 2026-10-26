"use client";
import { useState } from "react";
import { useUserTheme } from "@/components/user-theme";
import { ActionLink, Button, Card, ChoiceGroup, Dialog, Section } from "./account-ui";
import styles from "./account.module.css";
export function ChatSettings({ onClose, walletHref = "/account/wallet" }: { onClose: () => void; walletHref?: string }) {
  const { theme, setTheme } = useUserTheme();
  const [confirm, setConfirm] = useState(false);
  return <Dialog title={confirm ? "대화를 삭제할까요?" : "대화 설정"} onClose={confirm ? () => setConfirm(false) : onClose}><div className={styles.chatSettings}>
    {confirm ? <><p>대화 삭제 기능은 준비 중입니다. 기존 대화는 보존돼요.</p><Button primary disabled>대화 삭제 · 준비 중</Button><Button autoFocus onClick={() => setConfirm(false)}>취소</Button></> : <><Section title="화면 테마"><ChoiceGroup label="대화 테마" values={["라이트", "다크"]} value={theme === "dark" ? "다크" : "라이트"} onChange={value => setTheme(value === "다크" ? "dark" : "light")} /></Section><Section title="답변과 크레딧"><Card><p>답변 가격은 요청 시 서버에서 계산됩니다. 크레딧이 부족하면 지갑을 먼저 확인해 주세요.</p></Card><ActionLink href={walletHref}>내 크레딧 지갑 →</ActionLink></Section><Button onClick={() => setConfirm(true)}>대화 삭제 안내</Button><Button primary onClick={onClose}>닫기 · 대화로 돌아가기</Button></>}
  </div></Dialog>;
}

export function CreditShortageDialog({ onClose, walletHref = "/account/wallet" }: { onClose: () => void; walletHref?: string }) {
  return <Dialog title="크레딧이 부족해요" onClose={onClose}><div className={styles.chatSettings}><p>지금은 답변을 이어갈 크레딧이 부족해요. 지갑에서 사용 가능 잔액과 예약 중인 금액을 확인해 주세요.</p><ActionLink primary href={walletHref}>내 크레딧 지갑 보기</ActionLink><Button onClick={onClose}>대화로 돌아가기</Button></div></Dialog>;
}
