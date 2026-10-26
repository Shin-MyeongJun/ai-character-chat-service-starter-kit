import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "Studio Admin · 관리자", description: "생성 프롬프트 관리자 조회", robots: { index: false, follow: false } };
export default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang="ko"><body>{children}</body></html>; }
