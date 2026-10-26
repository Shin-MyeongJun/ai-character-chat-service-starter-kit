import { PromptDetail } from "@/components/generation-prompts/prompt-detail";
export default async function Page({ params }: { params: Promise<{ generationId: string }> }) { const { generationId } = await params; return <PromptDetail id={generationId} />; }
