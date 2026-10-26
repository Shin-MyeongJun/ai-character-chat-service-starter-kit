// Imported exclusively by the development-only server route. Never used as an API fallback.
import type { AccountPreview } from "./account";
export const accountPreview: AccountPreview = {
  user: { id: "design-preview", email: "reader@example.com", email_verified: true },
  balance: { balance_credit: 12570, available_credit: 12450, reserved_credit: 120 },
  conversations: [
    { id: "preview-erin", product_id: "preview-work", title: "별빛 기록실 · 에린", last_message: "“오늘도 기록실에 와 주셨군요.”", created_at: "2026-10-20T05:32:00Z" },
    { id: "preview-yuha", product_id: "preview-clock", title: "시계탑의 약속 · 유하", last_message: "“자정이 되기 전에 만나요.”", created_at: "2026-10-19T12:08:00Z" },
  ],
  products: [
    { id: "preview-work", title: "별빛 기록실", description: "달빛 아래 열리는 비밀의 도서관", visibility: "private", status: "draft", created_at: "2026-10-18T05:00:00Z", updated_at: "2026-10-20T05:00:00Z" },
    { id: "preview-clock", title: "시계탑의 약속", description: "멈춘 시간 속에서 다시 만난 두 사람", visibility: "public", status: "published", created_at: "2026-10-18T05:00:00Z", updated_at: "2026-10-19T05:00:00Z" },
    { id: "preview-book", title: "오후의 작은 서점", description: "익숙한 골목에서 시작되는 이야기", visibility: "private", status: "draft", created_at: "2026-10-18T05:00:00Z", updated_at: "2026-10-18T05:00:00Z" },
  ],
  orders: [
    { id: "MC-20261019-001", amount: 10000, credits: 10000, createdAt: "2026-10-19T06:20:00Z", status: "pending" },
    { id: "MC-20261018-014", amount: 10000, credits: 10000, createdAt: "2026-10-18T05:20:00Z", status: "succeeded" },
    { id: "MC-20261017-008", amount: 5000, credits: 5000, createdAt: "2026-10-17T12:08:00Z", status: "failed" },
  ],
  ledger: [
    { id: "1", date: "2026-10-18T05:32:00Z", kind: "사용", title: "별빛 기록실", credits: -120 },
    { id: "2", date: "2026-10-18T05:20:00Z", kind: "획득", title: "크레딧 충전", credits: 10000 },
    { id: "3", date: "2026-10-17T12:08:00Z", kind: "사용", title: "시계탑의 약속", credits: -180 },
  ],
};
