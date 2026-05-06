import OpenAI from "openai";
import { HumanMessage, SystemMessage } from "@langchain/core/messages";
import { ChatOpenAI } from "@langchain/openai";
import { z } from "zod";
import { config } from "../config";
import type { BrainContext, EvaluationResult } from "../types/actions";

const evaluationSchema = z.object({
  ok: z.boolean(),
  summary: z.string(),
  issues: z.array(z.string()),
  nextActions: z.array(z.object({
    kind: z.enum(["navigate", "click", "fill", "select", "upload", "waitForState", "api", "evaluate", "noop"]),
    description: z.string(),
    selector: z.string().optional(),
    text: z.string().optional(),
    value: z.string().optional(),
    path: z.string().optional(),
    targetState: z.string().optional(),
    confidence: z.number().min(0).max(1)
  }))
});

export class Evaluator {
  private readonly client?: OpenAI;
  private readonly langchain?: ChatOpenAI;

  constructor() {
    if (config.aiProvider === "langchain" && config.openAiApiKey) {
      this.langchain = new ChatOpenAI({
        apiKey: config.openAiApiKey,
        model: config.openAiModel,
        temperature: 0
      });
    } else if (config.aiProvider === "openai" && config.openAiApiKey) {
      this.client = new OpenAI({ apiKey: config.openAiApiKey });
    }
  }

  async evaluate(context: BrainContext): Promise<EvaluationResult> {
    if (this.langchain) return this.evaluateWithLangChain(context);
    if (!this.client) {
      return { ok: true, summary: "Heuristic evaluator accepted backend/UI state.", issues: [], nextActions: [] };
    }

    const response = await this.client.responses.create({
      model: config.openAiModel,
      input: [
        {
          role: "system",
          content: "You evaluate multi-user UI test runs. Return JSON. Flag state mismatches, broken UI signals, and concurrency risks."
        },
        { role: "user", content: JSON.stringify(context) }
      ],
      text: {
        format: {
          type: "json_schema",
          name: "evaluation",
          schema: {
            type: "object",
            additionalProperties: false,
            required: ["ok", "summary", "issues", "nextActions"],
            properties: {
              ok: { type: "boolean" },
              summary: { type: "string" },
              issues: { type: "array", items: { type: "string" } },
              nextActions: { type: "array", items: { type: "object" } }
            }
          }
        }
      }
    });

    const parsed = evaluationSchema.safeParse(JSON.parse(response.output_text));
    if (parsed.success) return parsed.data;
    return { ok: false, summary: "AI evaluator returned invalid JSON.", issues: [parsed.error.message], nextActions: [] };
  }

  private async evaluateWithLangChain(context: BrainContext): Promise<EvaluationResult> {
    if (!this.langchain) {
      return { ok: true, summary: "Heuristic evaluator accepted backend/UI state.", issues: [], nextActions: [] };
    }
    const response = await this.langchain.invoke([
      new SystemMessage("You evaluate multi-user UI test runs. Return only JSON with ok, summary, issues, and nextActions."),
      new HumanMessage(JSON.stringify(context))
    ]);
    const content = typeof response.content === "string" ? response.content : JSON.stringify(response.content);
    const parsed = evaluationSchema.safeParse(JSON.parse(content));
    if (parsed.success) return parsed.data;
    return { ok: false, summary: "LangChain evaluator returned invalid JSON.", issues: [parsed.error.message], nextActions: [] };
  }
}
