import { notFound } from "next/navigation";
import { AccountApp } from "@/components/account/account-app";
import { validAccountSection } from "@/lib/account";
export const dynamic = "force-dynamic";
export default async function PreviewPage({ params, searchParams }: { params: Promise<{ section?: string[] }>; searchParams: Promise<{ state?: string }> }) {
  if (process.env.NODE_ENV !== "development") notFound();
  const { section = [] } = await params;
  if (!validAccountSection(section, true)) notFound();
  const { accountPreview } = await import("@/lib/account-preview");
  const { state } = await searchParams;
  return <AccountApp section={section} preview={{ ...accountPreview, state: state === "empty" || state === "loading" || state === "error" || state === "credit" ? state : undefined }} />;
}
