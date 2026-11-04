// The LLM card of an import (done page, history). parser_first asks the model only for what the
// rules could not read, so a job sent to an AI can end without a request (R2 M-11 M-12: Typhoon
// OCR read the scanned book well enough); say so instead of "not used".
export type LlmUsage = { calls: number; prompt_tokens: number; completion_tokens: number; seconds: number; model?: string } | null;

const AI: Record<string, string> = { ollama: "Local AI · Gemma", gemini: "Cloud AI · Gemini" };

export function llmSummary(provider: string, llm: LlmUsage): { value: string; detail: string; short: string } {
  if (llm && llm.calls > 0) {
    return {
      value: `${llm.calls} คำขอ`,
      detail: `${llm.model} · ${llm.prompt_tokens}/${llm.completion_tokens} tokens · ${llm.seconds} s`,
      short: `${llm.calls} คำขอ · ${llm.prompt_tokens}/${llm.completion_tokens} tok`,
    };
  }
  if (AI[provider]) {
    return { value: "0 คำขอ", detail: `เลือก ${AI[provider]} · ไม่ต้องเรียก เพราะอ่านด้วยกฎได้ครบ`, short: "0 คำขอ (กฎอ่านได้ครบ)" };
  }
  return { value: "ไม่ใช้", detail: "อ่านด้วยกฎอย่างเดียว", short: "–" };
}
