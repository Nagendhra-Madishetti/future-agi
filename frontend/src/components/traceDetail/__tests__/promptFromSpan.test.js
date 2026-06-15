import { describe, it, expect } from "vitest";
import {
  normalizeMessagesFromSpan,
  extractModelFromSpan,
  extractProviderFromSpan,
  extractParamsFromSpan,
  buildPromptConfigFromSpan,
} from "../promptFromSpan";

describe("normalizeMessagesFromSpan", () => {
  // Mastra/Gemini: gen_ai.input.messages stored as an ARRAY value
  it("parses an array-valued gen_ai.input.messages (parts[].content)", () => {
    const span = {
      span_attributes: {
        "gen_ai.input.messages": [
          {
            role: "system",
            parts: [{ content: "You are helpful", type: "text" }],
          },
          {
            role: "user",
            parts: [{ content: "Weather in Mumbai?", type: "text" }],
          },
        ],
      },
    };
    expect(normalizeMessagesFromSpan(span)).toEqual([
      { role: "system", content: "You are helpful" },
      { role: "user", content: "Weather in Mumbai?" },
    ]);
  });

  // Mastra: object input {messages:[{role, content: str | [{type,text}]}]}
  it("parses {messages:[...]} object input with string/array content", () => {
    const span = {
      input: {
        messages: [
          { role: "system", content: "You are helpful" },
          { role: "user", content: [{ type: "text", text: "Weather?" }] },
        ],
      },
    };
    expect(normalizeMessagesFromSpan(span)).toEqual([
      { role: "system", content: "You are helpful" },
      { role: "user", content: "Weather?" },
    ]);
  });

  // Google ADK: nested message.contents.N.message_content.text (+ .type)
  it("parses nested message_content.text and ignores the .type sibling", () => {
    const span = {
      span_attributes: {
        "gen_ai.input.messages.0.message.role": "system",
        "gen_ai.input.messages.0.message.content": "Delegate weather Qs",
        "gen_ai.input.messages.1.message.role": "user",
        "gen_ai.input.messages.1.message.contents.0.message_content.text":
          "What's the weather in NY?",
        "gen_ai.input.messages.1.message.contents.0.message_content.type":
          "text",
      },
    };
    expect(normalizeMessagesFromSpan(span)).toEqual([
      { role: "system", content: "Delegate weather Qs" },
      { role: "user", content: "What's the weather in NY?" },
    ]);
  });

  // LangChain: flattened, system NOT first, object content, multi-turn
  it("parses flattened multi-turn with system out of order and object content", () => {
    const span = {
      span_attributes: {
        "gen_ai.input.messages.0.message.role": "user",
        "gen_ai.input.messages.0.message.content": "Hello",
        "gen_ai.input.messages.1.message.role": "system",
        "gen_ai.input.messages.1.message.content": "You are an assistant",
        "gen_ai.input.messages.2.message.role": "assistant",
        "gen_ai.input.messages.2.message.content": { response: "Hi there" },
      },
    };
    expect(normalizeMessagesFromSpan(span)).toEqual([
      { role: "user", content: "Hello" },
      { role: "system", content: "You are an assistant" },
      { role: "assistant", content: '{"response":"Hi there"}' },
    ]);
  });

  // Simple OpenInference (the case that already worked) — canonical snake keys
  it("parses canonical llm.input_messages flat strings", () => {
    const span = {
      span_attributes: {
        "llm.input_messages.0.message.role": "system",
        "llm.input_messages.0.message.content": "You are helpful",
        "llm.input_messages.1.message.role": "user",
        "llm.input_messages.1.message.content": "Hi",
      },
    };
    expect(normalizeMessagesFromSpan(span)).toEqual([
      { role: "system", content: "You are helpful" },
      { role: "user", content: "Hi" },
    ]);
  });

  it("returns [] for an unparseable object input (no raw-blob dump)", () => {
    const span = {
      span_attributes: {},
      input: { config: { http_options: { headers: {} } } },
    };
    expect(normalizeMessagesFromSpan(span)).toEqual([]);
  });

  it("treats a plain-text input as a single user message", () => {
    expect(normalizeMessagesFromSpan({ input: "Hello there" })).toEqual([
      { role: "user", content: "Hello there" },
    ]);
  });
});

describe("extractModelFromSpan", () => {
  it("prefers span.model", () => {
    expect(
      extractModelFromSpan({ model: "gpt-5.2", span_attributes: {} }),
    ).toBe("gpt-5.2");
  });
  it("falls back to gen_ai.request.model then llm.model_name", () => {
    expect(
      extractModelFromSpan({
        span_attributes: { "gen_ai.request.model": "gemini-2.0-flash" },
      }),
    ).toBe("gemini-2.0-flash");
    expect(
      extractModelFromSpan({ span_attributes: { "llm.model_name": "gpt-4o" } }),
    ).toBe("gpt-4o");
  });
  it("returns '' when no model present", () => {
    expect(extractModelFromSpan({ span_attributes: {} })).toBe("");
  });
});

describe("extractProviderFromSpan", () => {
  it("reads provider from gen_ai.provider.name / llm.provider / span.provider", () => {
    expect(
      extractProviderFromSpan({
        span_attributes: { "gen_ai.provider.name": "google.generative-ai" },
      }),
    ).toBe("google.generative-ai");
    expect(extractProviderFromSpan({ provider: "openai" })).toBe("openai");
    expect(extractProviderFromSpan({ span_attributes: {} })).toBe("");
  });
});

describe("buildPromptConfigFromSpan return", () => {
  it("includes model, provider, and params alongside messages", () => {
    const span = {
      model: "gpt-5.2",
      span_attributes: {
        "gen_ai.provider.name": "openai",
        "gen_ai.request.temperature": 0.3,
        "gen_ai.input.messages.0.message.role": "user",
        "gen_ai.input.messages.0.message.content": "Hi",
      },
    };
    const { model, provider, parameters } = buildPromptConfigFromSpan(span);
    expect(model).toBe("gpt-5.2");
    expect(provider).toBe("openai");
    expect(parameters).toEqual({ temperature: 0.3 });
  });
});

describe("extractParamsFromSpan", () => {
  it("reads individual gen_ai.request.* numeric params", () => {
    expect(
      extractParamsFromSpan({
        span_attributes: {
          "gen_ai.request.temperature": 0.7,
          "gen_ai.request.max_tokens": 256,
          "gen_ai.request.top_p": 0.9,
        },
      }),
    ).toEqual({ temperature: 0.7, max_tokens: 256, top_p: 0.9 });
  });

  it("reads the gen_ai.request.parameters blob and drops transport junk", () => {
    expect(
      extractParamsFromSpan({
        span_attributes: {
          "gen_ai.request.parameters": JSON.stringify({
            temperature: 0.5,
            _type: "openai-chat",
            model: "gpt-5.2",
            stream: false,
            http_options: { headers: {} },
          }),
        },
      }),
    ).toEqual({ temperature: 0.5 });
  });

  it("returns {} when params are empty/absent", () => {
    expect(
      extractParamsFromSpan({
        span_attributes: { "gen_ai.request.parameters": "" },
      }),
    ).toEqual({});
  });
});

describe("buildPromptConfigFromSpan", () => {
  it("wraps content in workbench format and keeps an existing system message", () => {
    const span = {
      span_attributes: {
        "gen_ai.input.messages.0.message.role": "system",
        "gen_ai.input.messages.0.message.content": "Sys",
        "gen_ai.input.messages.1.message.role": "user",
        "gen_ai.input.messages.1.message.content": "Hi",
      },
    };
    const { messages } = buildPromptConfigFromSpan(span);
    expect(messages).toEqual([
      { role: "system", content: [{ type: "text", text: "Sys" }] },
      { role: "user", content: [{ type: "text", text: "Hi" }] },
    ]);
  });

  it("prepends an empty system only when none exists", () => {
    const span = {
      span_attributes: {
        "gen_ai.input.messages.0.message.role": "user",
        "gen_ai.input.messages.0.message.content": "Hi",
      },
    };
    const { messages } = buildPromptConfigFromSpan(span);
    expect(messages[0]).toEqual({
      role: "system",
      content: [{ type: "text", text: "" }],
    });
    expect(messages[1].role).toBe("user");
  });

  it("does not prepend a system when one already exists out of order", () => {
    const span = {
      span_attributes: {
        "gen_ai.input.messages.0.message.role": "user",
        "gen_ai.input.messages.0.message.content": "Hi",
        "gen_ai.input.messages.1.message.role": "system",
        "gen_ai.input.messages.1.message.content": "Sys",
      },
    };
    const { messages } = buildPromptConfigFromSpan(span);
    expect(messages.filter((m) => m.role === "system")).toHaveLength(1);
    expect(messages[0].role).toBe("user");
  });

  it("returns no messages for an unparseable object input", () => {
    const { messages } = buildPromptConfigFromSpan({
      span_attributes: {},
      input: { config: {} },
    });
    expect(messages).toEqual([]);
  });
});
