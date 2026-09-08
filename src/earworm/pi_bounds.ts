import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { appendFileSync, readFileSync } from "node:fs";

interface Limits {
  provider: string; model: string; max_output_tokens: number; max_input_bytes: number;
  max_requests: number; max_tool_calls: number; max_price_input: number;
  max_price_output: number; budget_usd: number; deadline_ms: number;
  audit_path: string; tools: string[];
  request_reasoning_effort?: string;
}

function stop(message: string): never {
  // Pi catches hook exceptions and would send the original request. Terminating
  // this isolated process is necessary for a failed guard to prevent dispatch.
  process.stderr.write(`EARWORM_GUARD: ${message}\n`);
  process.exit(1);
}

export default function (pi: ExtensionAPI): void {
  let limits: Limits;
  try {
    limits = JSON.parse(readFileSync(process.env.EARWORM_LIMITS ?? "", "utf8")) as Limits;
  } catch {
    stop("Cannot load request limits.");
  }
  const canary = process.env.EARWORM_CANARY === "1";
  let requests = 0;
  let toolCalls = 0;
  pi.on("tool_call", (event) => {
    if (canary || !limits.tools.includes(event.toolName)) stop("Unapproved tool call.");
    if (++toolCalls > limits.max_tool_calls) stop("Tool-call limit reached.");
    if (Date.now() >= limits.deadline_ms) stop("Stage deadline reached.");
  });
  pi.on("before_provider_request", (event, ctx) => {
    if (ctx.model?.provider !== limits.provider || ctx.model?.id !== limits.model) stop("Unexpected model route.");
    if (ctx.model.api !== "openai-completions") stop("Only bounded OpenAI-compatible request bodies are supported.");
    if (Date.now() >= limits.deadline_ms) stop("Stage deadline reached.");
    if (++requests > (canary ? 1 : limits.max_requests)) stop("Model-request limit reached.");
    if (!event.payload || typeof event.payload !== "object" || Array.isArray(event.payload)) stop("Invalid request body.");
    const payload = { ...event.payload } as Record<string, unknown>;
    if (!Array.isArray(payload.messages)) stop("Expected text chat messages.");
    const output = canary ? 128 : limits.max_output_tokens;
    if (![limits.max_price_input, limits.max_price_output, limits.budget_usd].every(n => Number.isFinite(n) && n >= 0)
        || !Number.isInteger(output) || output <= 0) stop("Invalid request price or token limit.");
    if (limits.provider !== "openrouter" &&
        (ctx.model.cost.input > limits.max_price_input || ctx.model.cost.output > limits.max_price_output)) {
      stop("Configured price ceiling is below the selected model price.");
    }
    let committed = 0;
    let retrievalExhausted = false;
    try {
      const rows = readFileSync(limits.audit_path, "utf8").trim().split("\n")
        .filter(Boolean).map(line => JSON.parse(line) as { type?: string; reserved_usd?: number });
      committed = rows.reduce((sum, row) => sum + (row.reserved_usd ?? 0), 0);
      retrievalExhausted = rows.some(row => row.type === "retrieval_budget_exhausted");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") stop("Cannot read request budget audit.");
    }
    delete payload.max_completion_tokens;
    payload.max_tokens = output;
    // Pi's "off" can omit this field, letting an Ollama model turn thinking
    // on by default and consume the entire output allowance before answering.
    if (limits.request_reasoning_effort) {
      if (!["none", "low", "medium", "high"].includes(limits.request_reasoning_effort)) stop("Invalid explicit reasoning effort.");
      payload.reasoning_effort = limits.request_reasoning_effort;
    }
    if (limits.provider === "openrouter") {
      payload.provider = {
        allow_fallbacks: false,
        require_parameters: true,
        max_price: { prompt: limits.max_price_input, completion: limits.max_price_output },
      };
    }
    const size = () => new TextEncoder().encode(JSON.stringify(payload)).length;
    const cost = (bytes: number) => (bytes * limits.max_price_input + output * limits.max_price_output) / 1_000_000;
    const finalCall = !canary && limits.tools.length > 0 &&
      (requests === limits.max_requests || toolCalls >= limits.max_tool_calls || retrievalExhausted ||
       limits.budget_usd - committed - cost(size()) < cost(limits.max_input_bytes));
    if (finalCall) {
      payload.tool_choice = "none";
      payload.messages = [...payload.messages, { role: "user", content:
        "The retrieval or request budget is ending. Write the final requested artifact now using available evidence. " +
        "Do not call tools. Mark unsupported points as gaps or omit them; do not invent missing evidence." }];
    }
    // Count the complete body, including the final-writing instruction and
    // routing caps. UTF-8 bytes conservatively overcount text input tokens.
    const bytes = size();
    const reserved = cost(bytes);
    if (bytes > (canary ? 12000 : limits.max_input_bytes)) stop("Request exceeds input-byte limit.");
    if (committed + reserved > limits.budget_usd) stop("Stage budget would be exceeded.");
    try {
      appendFileSync(limits.audit_path, JSON.stringify({ type: "request", canary,
        provider: limits.provider, model: limits.model, input_bytes: bytes,
        max_output_tokens: output, reserved_usd: reserved, final_call: finalCall, timestamp: Date.now() }) + "\n", { mode: 0o600 });
    } catch {
      stop("Cannot reserve request budget before dispatch.");
    }
    return payload;
  });
}
