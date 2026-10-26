import type { Metadata } from "next";
import { CreatorStudio } from "@/components/studio/creator-studio";

export const metadata: Metadata = {
  title: "제작 스튜디오 | 모서리",
  description: "작품과 캐릭터, 로어북과 시작 장면을 만드는 나의 창작 공간",
};

export default async function StudioPage({ searchParams }: { searchParams: Promise<{ work?: string; product?: string }> }) {
  const { work, product } = await searchParams;
  return <CreatorStudio initialWorkId={work} initialProductId={product} />;
}
