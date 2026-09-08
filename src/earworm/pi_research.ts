/** Explicit retrieval only: anonymous Exa search, public HTML/PDF extraction.
 * We import deterministic parsers from pi-web-access, never its extension or
 * auto provider pipeline, which may call additional summarization models.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
import { preserveTables, readableText } from "./pi_html.ts";

interface Limits { web_access_path: string; deadline_ms: number; tools: string[]; source_cache: string; max_tool_calls: number; audit_path: string }

export function searchExcerpts(raw: string): string {
  const blocks = raw.split(/(?=^Title: )/m).filter(block => /^Title: /m.test(block));
  const results = blocks.slice(0, 5).map(block => {
    const title = block.match(/^Title: (.+)/m)?.[1]?.trim().slice(0, 200) ?? "Untitled source";
    const url = block.match(/^URL: (.+)/m)?.[1]?.trim().slice(0, 1500) ?? "";
    const date = block.match(/^Published: (.+)/m)?.[1]?.trim().slice(0, 80) ?? "Unknown";
    const excerpt = block.replace(/^(Title|URL|Published|Author):.*$/gm, "")
      .replace(/^(Highlights|Text):\s*/gm, "").replace(/\s+/g, " ").trim().slice(0, 500);
    return `Title: ${title}\nURL: ${url}\nPublished: ${date}\nExcerpt: ${excerpt}`;
  });
  // An unfamiliar response shape must remain visibly incomplete; never turn a
  // text fragment without source metadata into a supposedly verified source.
  return results.length ? results.join("\n\n").slice(0, 5000) : "Search returned an unsupported result format; no source excerpts extracted.";
}

async function bodyBytes(response: Response, limit = 2_000_000): Promise<Uint8Array> {
  if (Number(response.headers.get("content-length") ?? 0) > limit) throw new Error("Source exceeds the 2 MB retrieval limit.");
  const reader = response.body?.getReader();
  if (!reader) throw new Error("Source has no response body.");
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    for (;;) {
      const item = await reader.read();
      if (item.done) break;
      size += item.value.length;
      if (size > limit) throw new Error("Source exceeds the 2 MB retrieval limit.");
      chunks.push(item.value);
    }
  } finally {
    await reader.cancel();
  }
  const result = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.length; }
  return result;
}

export default async function (pi: ExtensionAPI): Promise<void> {
  let limits: Limits;
  try {
    limits = JSON.parse(readFileSync(process.env.EARWORM_LIMITS ?? "", "utf8")) as Limits;
  } catch {
    process.stderr.write("EARWORM_GUARD: Cannot load retrieval limits.\n");
    process.exit(1);
  }
  const require = createRequire(join(limits.web_access_path, "package.json"));
  const { Readability } = require("@mozilla/readability");
  const { parseHTML } = require("linkedom");
  const { extractText, getDocumentProxy } = require("unpdf");
  // This module checks public DNS/IPs and redirects. Explicit empty exceptions
  // avoid inheriting any global SSRF allowlist or proxy trust setting.
  const { fetchRemoteUrl } = await import(pathToFileURL(join(limits.web_access_path, "ssrf-protection.ts")).href);
  mkdirSync(limits.source_cache, { recursive: true, mode: 0o700 });
  const exhaustedMessage = "\nRetrieval evidence budget exhausted; finish the report with available evidence and mark gaps.";
  // Reserve room for an explicit exhaustion notice for every permitted tool
  // call, including tools already dispatched in the same parallel batch.
  const contentBudget = 40000 - limits.max_tool_calls * exhaustedMessage.length;
  let emitted = 0;
  let exhausted = false;
  if (contentBudget <= 0) {
    process.stderr.write("EARWORM_GUARD: Too many tool calls for the retrieval budget.\n");
    process.exit(1);
  }
  function markExhausted(): void {
    if (exhausted) return;
    exhausted = true;
    try {
      appendFileSync(limits.audit_path, JSON.stringify({ type: "retrieval_budget_exhausted", emitted_characters: emitted }) + "\n");
    } catch {
      process.stderr.write("EARWORM_GUARD: Cannot record retrieval exhaustion.\n");
      process.exit(1);
    }
  }
  function cacheFile(key: string): string {
    return createHash("sha256").update(key).digest("hex") + ".json";
  }
  function signalFor(signal?: AbortSignal): AbortSignal {
    const remaining = Math.max(1, Math.min(20000, limits.deadline_ms - Date.now()));
    return signal ? AbortSignal.any([signal, AbortSignal.timeout(remaining)]) : AbortSignal.timeout(remaining);
  }
  function result(text: string, details: Record<string, unknown> = {}) {
    if (exhausted) return { content: [{ type: "text" as const, text: exhaustedMessage }], details: { ...details, retrieval_budget_exhausted: true } };
    const remaining = contentBudget - emitted;
    const clipped = text.length >= remaining;
    text = text.slice(0, remaining);
    emitted += text.length;
    if (clipped) {
      markExhausted();
      text += exhaustedMessage;
    }
    return { content: [{ type: "text" as const, text }], details: { ...details,
      retrieval_budget_exhausted: exhausted, retrieval_budget_clipped: clipped } };
  }
  if (limits.tools.includes("web_search")) pi.registerTool({
    name: "web_search", label: "Search public sources",
    description: "Search public web sources with anonymous Exa MCP. Returns retrieved excerpts and URLs without an LLM summary. Prefer specific primary-source queries; at most five results per search.",
    parameters: Type.Object({ query: Type.String({ minLength: 1, maxLength: 1000 }) }),
    async execute(_id, { query }, signal) {
      if (exhausted) return result("");
      try {
        const response = await fetch("https://mcp.exa.ai/mcp?tools=web_search_exa", {
          method: "POST", signal: signalFor(signal),
          headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
          body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: {
            name: "web_search_exa", arguments: { query, numResults: 5, type: "auto", contextMaxCharacters: 5000 },
          } }),
        });
        if (!response.ok) return result(`Search unavailable: HTTP ${response.status}. No results retrieved.`);
        const body = new TextDecoder().decode(await bodyBytes(response));
        const candidates = body.startsWith("{") ? [body] : body.split("\n").filter(l => l.startsWith("data:")).map(l => l.slice(5).trim());
        for (const candidate of candidates) {
          let rpc;
          try { rpc = JSON.parse(candidate); } catch { continue; }
          if (rpc.error || rpc.result?.isError) return result("Search service reported an error. No results retrieved.");
          const texts = rpc.result?.content?.filter((c: { type: string }) => c.type === "text").map((c: { text: string }) => c.text);
          if (texts?.length) {
            const raw = texts.join("\n");
            const file = cacheFile("search:" + query);
            writeFileSync(join(limits.source_cache, file), JSON.stringify({ kind: "search", query, retrieved_at: new Date().toISOString(), text: raw }), { mode: 0o600 });
            return result(searchExcerpts(raw), { cached_source_file: file, excerpted: true });
          }
        }
        return result("Search returned no readable results.");
      } catch {
        return result("Search failed or timed out. No results retrieved.");
      }
    },
  });
  if (limits.tools.includes("web_fetch")) pi.registerTool({
    name: "web_fetch", label: "Read a public source",
    description: "Retrieve public HTTP(S) HTML, plain text, or a PDF. Deterministic extraction, no model summary. Returns a bounded page slice; use offset to read the next part. No authenticated, local, video, or browser-cookie access.",
    parameters: Type.Object({ url: Type.String({ maxLength: 3000 }), offset: Type.Optional(Type.Integer({ minimum: 0 })) }),
    async execute(_id, { url, offset = 0 }, signal) {
      if (exhausted) return result("");
      try {
        const parsed = new URL(url);
        if (parsed.username || parsed.password || (parsed.port && !["80", "443"].includes(parsed.port))) return result("Only public standard-port URLs without credentials are supported.");
        parsed.hash = "";
        const file = cacheFile("fetch:" + parsed.href);
        const path = join(limits.source_cache, file);
        const cached = existsSync(path);
        let text: string;
        if (cached) {
          text = JSON.parse(readFileSync(path, "utf8")).text;
        } else {
          const response = await fetchRemoteUrl(parsed.href, { signal: signalFor(signal), headers: { "User-Agent": "Earworm-Research/1.0" } },
            { allowRanges: [], trustEnvProxy: false, maxRedirects: 3, domainPolicy: { allow: [], deny: [] } });
          if (!response.ok) return result(`Source unavailable: HTTP ${response.status}. No source content retrieved.`);
          const bytes = await bodyBytes(response);
          const mime = response.headers.get("content-type") ?? "";
          if (mime.includes("pdf") || new TextDecoder().decode(bytes.slice(0, 5)) === "%PDF-") {
            const pdf = await getDocumentProxy(bytes);
            try { text = (await extractText(pdf, { mergePages: true })).text; } finally { await pdf.destroy(); }
          } else if (mime.includes("html")) {
            const { document } = parseHTML(new TextDecoder().decode(bytes));
            const tableCount = preserveTables(document);
            const bodyText = readableText(document.body ?? document);
            const article = new Readability(document).parse();
            if (article?.content) {
              const articleDocument = parseHTML(`<html><body>${article.content}</body></html>`).document;
              text = readableText(articleDocument.body);
              // Readability can drop data tables along with surrounding layout.
              // Retain the page extraction if any serialized table disappeared.
              if (tableCount && Array.from({ length: tableCount }, (_, i) => `[TABLE ${i + 1}`).some(marker => !text.includes(marker))) text = bodyText;
            } else text = bodyText;
          } else if (mime.startsWith("text/") || mime.includes("json")) {
            text = new TextDecoder().decode(bytes);
          } else return result("Source format is unsupported; no content extracted.");
          text = text.replace(/\n[ \t]+/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
          writeFileSync(path, JSON.stringify({ kind: "fetch", url: parsed.href,
            final_url: response.url || parsed.href, retrieved_at: new Date().toISOString(),
            content_type: mime, text, text_length: text.length, extraction_complete: true }), { mode: 0o600 });
        }
        const end = Math.min(text.length, offset + 8000);
        return result(`Source: ${parsed.href}\nCharacters ${offset}-${end} of ${text.length}. ${end < text.length ? `Continue at offset ${end}.` : "End of source."}\n\n${text.slice(offset, end)}`,
          { cached_source_file: file, cache_hit: cached, url: parsed.href, offset, end,
            total_characters: text.length, source_truncated: end < text.length });
      } catch {
        return result("Source could not be safely fetched or extracted. No source content retrieved.");
      }
    },
  });
}
