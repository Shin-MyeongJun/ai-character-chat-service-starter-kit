export type AuthUser = { id: string; email: string; email_verified: boolean };
export const statuses = { pending: "대기", succeeded: "성공", failed: "실패", cancelled: "취소", stale: "만료" } as const;
export type GenerationStatus = keyof typeof statuses;
export type Generation = {
  generation_id: string; conversation_id: string; model_id: string; model_name: string;
  reasoning_effort: string; status: string; created_at: string; finished_at: string | null;
  history_invalidated_at: string | null; prompt_recorded: boolean;
  prompt_created_at: string | null; provider: string | null;
};
export type Prompt = { request_json: string; digest: string; format_version: number; created_at: string; provider: string; max_output_tokens: number };
export type PromptPage = { items: Generation[]; total: number; page: number; page_size: number };
export type PromptDetail = { generation: Generation; prompt: Prompt | null };
export const promptEndpoint = "/admin/reporting/generation-prompts";
