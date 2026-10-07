import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "모서리 | 이야기가 시작되는 곳",
  description: "마음에 드는 세계를 발견하고, 당신의 이야기를 이어가세요.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ko" data-scroll-behavior="smooth"><body>{children}</body></html>;
}
