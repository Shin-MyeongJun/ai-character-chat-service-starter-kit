import { notFound } from "next/navigation";
import { StudioImageExample } from "@/components/studio/studio-image-example";

export default function StudioImagePreviewPage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <StudioImageExample />;
}
