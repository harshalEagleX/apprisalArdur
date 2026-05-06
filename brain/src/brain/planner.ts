import OpenAI from "openai";
import { HumanMessage, SystemMessage } from "@langchain/core/messages";
import { ChatOpenAI } from "@langchain/openai";
import { z } from "zod";
import { config } from "../config";
import type { BrainAction, BrainContext } from "../types/actions";

const actionSchema = z.object({
  kind: z.enum(["navigate", "click", "fill", "select", "upload", "waitForState", "api", "evaluate", "noop"]),
  description: z.string(),
  selector: z.string().optional(),
  text: z.string().optional(),
  value: z.string().optional(),
  path: z.string().optional(),
  targetState: z.string().optional(),
  confidence: z.number().min(0).max(1)
});

const actionListSchema = z.object({ actions: z.array(actionSchema).min(1).max(5) });

export class Planner {
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

  async decide(context: BrainContext): Promise<BrainAction[]> {
    if (this.langchain) return this.decideWithLangChain(context);
    if (!this.client) return this.heuristic(context);

    const response = await this.client.responses.create({
      model: config.openAiModel,
      input: [
        {
          role: "system",
          content: "You are a cautious UI testing planner. Return only JSON with an actions array. Prefer backend state over fragile selectors."
        },
        {
          role: "user",
          content: JSON.stringify(context)
        }
      ],
      text: {
        format: {
          type: "json_schema",
          name: "testing_actions",
          schema: {
            type: "object",
            additionalProperties: false,
            required: ["actions"],
            properties: {
              actions: {
                type: "array",
                minItems: 1,
                maxItems: 5,
                items: {
                  type: "object",
                  additionalProperties: false,
                  required: ["kind", "description", "confidence"],
                  properties: {
                    kind: { enum: ["navigate", "click", "fill", "select", "upload", "waitForState", "api", "evaluate", "noop"] },
                    description: { type: "string" },
                    selector: { type: "string" },
                    text: { type: "string" },
                    value: { type: "string" },
                    path: { type: "string" },
                    targetState: { type: "string" },
                    confidence: { type: "number", minimum: 0, maximum: 1 }
                  }
                }
              }
            }
          }
        }
      }
    });

    const parsed = actionListSchema.safeParse(JSON.parse(response.output_text));
    return parsed.success ? parsed.data.actions : this.heuristic(context);
  }

  private async decideWithLangChain(context: BrainContext): Promise<BrainAction[]> {
    if (!this.langchain) return this.heuristic(context);
    const response = await this.langchain.invoke([
      new SystemMessage("You are a cautious UI testing planner. Return only JSON in this shape: {\"actions\":[{\"kind\":\"navigate|click|fill|select|upload|waitForState|api|evaluate|noop\",\"description\":\"...\",\"confidence\":0.9}]}. Prefer backend state over fragile selectors."),
      new HumanMessage(JSON.stringify(context))
    ]);
    const content = typeof response.content === "string" ? response.content : JSON.stringify(response.content);
    const parsed = actionListSchema.safeParse(JSON.parse(content));
    return parsed.success ? parsed.data.actions : this.heuristic(context);
  }

  private heuristic(context: BrainContext): BrainAction[] {
    const goal = context.goal.toLowerCase();
    if (goal.includes("reviewer") || context.role === "REVIEWER") {
      return [
        { kind: "navigate", description: "Open reviewer queue", path: "/reviewer/queue", confidence: 0.95 },
        { kind: "evaluate", description: "Validate queue and review state with backend", confidence: 0.9 }
      ];
    }
    if (goal.includes("upload")) {
      return [
        { kind: "navigate", description: "Open admin batch workspace", path: "/admin/batches", confidence: 0.95 },
        { kind: "upload", description: "Upload configured ZIP batch or reuse existing batch", confidence: 0.85 }
      ];
    }
    return [
      { kind: "navigate", description: "Open admin batch workspace", path: "/admin/batches", confidence: 0.9 },
      { kind: "evaluate", description: "Compare UI and backend batch state", confidence: 0.85 }
    ];
  }
}
