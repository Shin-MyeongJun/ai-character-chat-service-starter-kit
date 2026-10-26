import { notFound } from "next/navigation";
import { AccountApp } from "@/components/account/account-app";
import { validAccountSection } from "@/lib/account";
export const metadata = { title: "내 계정 | 모서리" };
export default async function AccountPage({ params }: { params: Promise<{ section?: string[] }> }) {
  const { section = [] } = await params;
  if (!validAccountSection(section)) notFound();
  return <AccountApp section={section} />;
}
