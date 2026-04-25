"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { getChatConversation, getChatConversations, streamChatCompletion } from "@/lib/api-client";
import type { ChatCompletionResponse, ChatStreamEvent, ConversationResponse, TraceResponse } from "@/lib/api-client/types";
import { chatData } from "@/lib/workspace-fixtures";

type RenderMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  time: string;
};

type RenderTraceStep = {
  name: string;
  summary: string;
  status: string;
  timestamp: string;
};

type RetrievalMode = "auto" | "rag" | "wiki";

function nowTime(): string {
  return new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function messageTime(value: string): string {
  return new Date(value).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function conversationToMessages(conversation: ConversationResponse): RenderMessage[] {
  return conversation.messages.map((message, index) => ({
    id: `${conversation.conversation_id}-${index}`,
    role: message.role,
    content: message.content,
    time: messageTime(message.created_at),
  }));
}

function isTableSeparator(line: string): boolean {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function isTableRow(line: string): boolean {
  return line.trim().startsWith("|") && line.trim().endsWith("|");
}

function parseTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function renderInlineMarkdown(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function renderMarkdown(content: string): ReactNode {
  const lines = content.split(/\r?\n/);
  const nodes: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (isTableRow(line) && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = parseTableRow(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && isTableRow(lines[index])) {
        rows.push(parseTableRow(lines[index]));
        index += 1;
      }
      nodes.push(
        <div className="markdown-table-wrap" key={`table-${index}`}>
          <table>
            <thead>
              <tr>
                {headers.map((header, cellIndex) => (
                  <th key={`${header}-${cellIndex}`}>{renderInlineMarkdown(header)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {headers.map((_, cellIndex) => (
                    <td key={cellIndex}>{renderInlineMarkdown(row[cellIndex] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (heading) {
      const level = heading[1].length;
      const HeadingTag = `h${Math.min(level + 2, 5)}` as "h3" | "h4" | "h5";
      nodes.push(
        <HeadingTag key={`heading-${index}`} className="markdown-heading">
          {renderInlineMarkdown(heading[2])}
        </HeadingTag>,
      );
      index += 1;
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      nodes.push(<hr key={`hr-${index}`} className="markdown-divider" />);
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      nodes.push(
        <ul key={`ul-${index}`} className="markdown-list">
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      nodes.push(
        <ol key={`ol-${index}`} className="markdown-list">
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
          ))}
        </ol>,
      );
      continue;
    }

    const paragraphLines = [trimmed];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^(#{1,4})\s+/.test(lines[index].trim()) &&
      !/^[-*]\s+/.test(lines[index].trim()) &&
      !/^\d+\.\s+/.test(lines[index].trim()) &&
      !/^---+$/.test(lines[index].trim()) &&
      !(isTableRow(lines[index]) && index + 1 < lines.length && isTableSeparator(lines[index + 1]))
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    nodes.push(
      <p key={`p-${index}`} className="markdown-paragraph">
        {renderInlineMarkdown(paragraphLines.join(" "))}
      </p>,
    );
  }

  return <div className="markdown-content">{nodes}</div>;
}

export function ChatWorkbench() {
  const [messages, setMessages] = useState<RenderMessage[]>([]);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [input, setInput] = useState("");
  const [latestResponse, setLatestResponse] = useState<ChatCompletionResponse | null>(null);
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("auto");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deltaBuffersRef = useRef<Record<string, string>>({});
  const finalContentRef = useRef<Record<string, string>>({});
  const typewriterTimersRef = useRef<Record<string, number>>({});
  const hasStartedLocalConversationRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function loadLatestConversation() {
      try {
        const conversations = await getChatConversations();
        const latestConversation = conversations.items[0];
        if (!latestConversation || cancelled) return;
        const conversation = await getChatConversation(latestConversation.conversation_id);
        if (cancelled || hasStartedLocalConversationRef.current) return;
        setConversationId(conversation.conversation_id);
        setMessages(conversationToMessages(conversation));
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "对话历史加载失败。";
          setError(`对话历史加载失败：${message}`);
        }
      }
    }

    loadLatestConversation();

    return () => {
      cancelled = true;
      Object.values(typewriterTimersRef.current).forEach((timer) => window.clearInterval(timer));
    };
  }, []);

  const references =
    latestResponse?.sources.map((item) => ({
      title: item.title,
      snippet:
        item.source_type === "wiki" && item.claim_text
          ? `${item.claim_text} (${item.locator ?? "wiki"})`
          : item.snippet,
      type: item.source_type,
    })) ?? [];

  const hasLatestResponse = latestResponse !== null;
  const hasReferences = references.length > 0;

  const traceSteps: RenderTraceStep[] =
    trace?.steps.map((item) => ({
      name: item.name,
      summary: item.summary,
      status: item.status,
      timestamp: item.timestamp ?? item.name,
    })) ?? [];

  async function submitMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed || isStreaming) return;

    const userMessageId = crypto.randomUUID();
    const assistantMessageId = crypto.randomUUID();
    hasStartedLocalConversationRef.current = true;
    setError(null);
    setLatestResponse(null);
    setTrace({
      trace_id: "",
      tenant_id: "",
      user_id: "",
      message: trimmed,
      intent: "",
      strategy: "",
      answer: "",
      created_at: new Date().toISOString(),
      steps: [],
      sources: [],
    });
    setMessages((prev) => [
      ...prev,
      { id: userMessageId, role: "user", content: trimmed, time: nowTime() },
      { id: assistantMessageId, role: "assistant", content: "", time: nowTime() },
    ]);
    setInput("");
    setIsStreaming(true);

    let failed = false;
    try {
      await streamChatCompletion(trimmed, retrievalMode, (event) => {
        handleStreamEvent(event, assistantMessageId, trimmed);
      }, conversationId);
    } catch (err) {
      failed = true;
      const message = err instanceof Error ? err.message : "请确认后端 API 已启动。";
      setError(`请求失败：${message}`);
      clearTypewriterState(assistantMessageId);
      setMessages((prev) =>
        prev.map((item) =>
          item.id === assistantMessageId && !item.content
            ? { ...item, content: "请求失败，未收到 Agent 响应。" }
            : item,
        ),
      );
    } finally {
      if (failed) {
        setIsStreaming(false);
      }
    }
  }

  function clearTypewriterState(messageId: string) {
    const timer = typewriterTimersRef.current[messageId];
    if (timer) {
      window.clearInterval(timer);
      delete typewriterTimersRef.current[messageId];
    }
    delete deltaBuffersRef.current[messageId];
    delete finalContentRef.current[messageId];
  }

  function appendAssistantContent(messageId: string, content: string) {
    setMessages((prev) =>
      prev.map((item) =>
        item.id === messageId
          ? { ...item, content: `${item.content}${content}` }
          : item,
      ),
    );
  }

  function startTypewriter(messageId: string) {
    if (typewriterTimersRef.current[messageId]) return;

    typewriterTimersRef.current[messageId] = window.setInterval(() => {
      const buffer = deltaBuffersRef.current[messageId] ?? "";
      if (!buffer) {
        const finalContent = finalContentRef.current[messageId];
        clearTypewriterState(messageId);
        if (finalContent !== undefined) {
          setMessages((prev) =>
            prev.map((item) =>
              item.id === messageId ? { ...item, content: finalContent } : item,
            ),
          );
          setIsStreaming(false);
        }
        return;
      }

      const takeSize = buffer.length > 32 ? 4 : 2;
      const nextChunk = buffer.slice(0, takeSize);
      deltaBuffersRef.current[messageId] = buffer.slice(takeSize);
      appendAssistantContent(messageId, nextChunk);
    }, 16);
  }

  function enqueueAssistantDelta(messageId: string, content: string) {
    deltaBuffersRef.current[messageId] = `${deltaBuffersRef.current[messageId] ?? ""}${content}`;
    startTypewriter(messageId);
  }

  function finishAssistantMessage(messageId: string, content: string) {
    finalContentRef.current[messageId] = content;
    if (!deltaBuffersRef.current[messageId]) {
      clearTypewriterState(messageId);
      setMessages((prev) =>
        prev.map((item) =>
          item.id === messageId ? { ...item, content } : item,
        ),
      );
      setIsStreaming(false);
      return;
    }
    startTypewriter(messageId);
  }

  function handleStreamEvent(event: ChatStreamEvent, assistantMessageId: string, userMessage: string) {
    if (event.event === "trace_step") {
      setTrace((prev) => ({
        trace_id: event.trace_id,
        tenant_id: prev?.tenant_id ?? "",
        user_id: prev?.user_id ?? "",
        message: prev?.message ?? userMessage,
        intent: prev?.intent ?? "",
        strategy: prev?.strategy ?? "",
        answer: prev?.answer ?? "",
        created_at: prev?.created_at ?? new Date().toISOString(),
        sources: prev?.sources ?? [],
        steps: [...(prev?.steps ?? []), event.step],
      }));
      return;
    }

    if (event.event === "response_meta") {
      setConversationId(event.conversation_id);
      setTrace((prev) => ({
        trace_id: event.trace_id,
        tenant_id: prev?.tenant_id ?? "",
        user_id: prev?.user_id ?? "",
        message: prev?.message ?? userMessage,
        intent: event.intent,
        strategy: event.strategy,
        answer: prev?.answer ?? "",
        created_at: prev?.created_at ?? new Date().toISOString(),
        steps: prev?.steps ?? [],
        sources: event.sources,
      }));
      setLatestResponse({
        trace_id: event.trace_id,
        conversation_id: event.conversation_id,
        intent: event.intent,
        strategy: event.strategy,
        message: {
          role: "assistant",
          content: "",
        },
        sources: event.sources,
        warnings: event.warnings,
        draft_action: event.draft_action ?? null,
      });
      return;
    }

    if (event.event === "message_delta") {
      enqueueAssistantDelta(assistantMessageId, event.content);
      return;
    }

    if (event.event === "message_done") {
      finishAssistantMessage(assistantMessageId, event.content);
      setLatestResponse((prev) =>
        prev
          ? {
              ...prev,
              message: {
                role: "assistant",
                content: event.content,
              },
            }
          : prev,
      );
      setTrace((prev) => (prev ? { ...prev, answer: event.content } : prev));
    }
  }

  return (
    <section className="chat-debug-layout">
      <section className="panel-card chat-panel">
        <div className="panel-header">
          <div>
            <h3>对话演练场</h3>
            <p>模拟真实用户环境测试 Agent 的逻辑响应。</p>
          </div>
          <span className={`status-chip ${isStreaming ? "warning pulse" : "success"}`}>
            {isStreaming ? "生成中" : "就绪"}
          </span>
        </div>

        <div className="thread-list">
          {chatData.threads.map((item) => (
            <button
              key={item}
              type="button"
              className="thread-chip"
              onClick={() => setInput(item)}
            >
              {item}
            </button>
          ))}
        </div>

        <div className="retrieval-mode-row">
          <span className="retrieval-mode-label">检索模式</span>
          <div className="pill-tabs retrieval-mode-tabs">
            {[
              { key: "auto", label: "自动" },
              { key: "rag", label: "RAG" },
              { key: "wiki", label: "Wiki" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                className={`pill-tab ${retrievalMode === item.key ? "active" : ""}`}
                onClick={() => setRetrievalMode(item.key as RetrievalMode)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <span className="status-chip plain info">
            {retrievalMode === "auto" ? "按意图自动选择" : retrievalMode === "rag" ? "固定走 RAG" : "固定走 Wiki"}
          </span>
        </div>

        <div className="chat-history">
          {messages.length > 0 ? (
            messages.map((message) => (
              <article
                key={message.id}
                className={`chat-bubble-row ${message.role}`}
              >
                <div className="bubble-avatar">
                  <span className="material-symbols-outlined">
                    {message.role === "user" ? "person" : "smart_toy"}
                  </span>
                </div>
                <div className="bubble-column">
                  <div className={`chat-bubble ${message.role}`}>
                    {message.content
                      ? message.role === "assistant"
                        ? renderMarkdown(message.content)
                        : message.content
                      : <span className="streaming-caret">正在响应</span>}
                  </div>
                  <span className="bubble-time">{message.time}</span>
                </div>
              </article>
            ))
          ) : (
            <div className="chat-empty-state">
              <span className="material-symbols-outlined">forum</span>
              <p>输入任务后开始真实对话。</p>
            </div>
          )}
        </div>

        {latestResponse?.warnings && latestResponse.warnings.length > 0 ? (
          <div className="chat-warnings">
            {latestResponse.warnings.map((tip) => (
              <p key={tip} className="chat-warning-item">
                <span className="material-symbols-outlined">warning</span>
                {tip}
              </p>
            ))}
          </div>
        ) : null}

        {latestResponse?.draft_action ? (
          <div className="draft-callout">
            <div>
              <strong>{latestResponse.draft_action.title}</strong>
              <p>{latestResponse.draft_action.summary}</p>
              <p>{latestResponse.draft_action.approval_hint}</p>
            </div>
            <div className="draft-callout-actions">
              <span className={`risk-level ${latestResponse.draft_action.risk_level.toLowerCase()}`}>
                {latestResponse.draft_action.risk_level}
              </span>
              <Link href="/approvals" className="primary-button">
                去审批确认
              </Link>
            </div>
          </div>
        ) : null}

        <div className="chat-composer">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="输入你要测试的任务..."
          />
          <div className="composer-toolbar">
            <div className="composer-flags">
              <button type="button" className="ghost-button">
                <span className="material-symbols-outlined">attach_file</span>
                附件
              </button>
              <button type="button" className="ghost-button">
                <span className="material-symbols-outlined">mic</span>
                语音
              </button>
              <span className="status-chip plain info">真实对话</span>
              <span className="status-chip plain">Trace 追踪</span>
            </div>
            <button
              type="button"
              className="primary-button"
              disabled={isStreaming}
              onClick={() => submitMessage(input)}
            >
              <span className="material-symbols-outlined">send</span>
              {isStreaming ? "处理中..." : "发送请求"}
            </button>
          </div>
          {error ? <p className="inline-error">{error}</p> : null}
        </div>
      </section>

      <aside className="panel-card trace-panel">
        <div className="panel-header">
          <div>
            <h3>Trace 执行链路</h3>
            <p>逐步查看意图识别、规划、插件执行与响应组装。</p>
          </div>
          <button type="button" className="ghost-button">
            <span className="material-symbols-outlined">refresh</span>
            刷新
          </button>
        </div>

        <div className="trace-list">
          {traceSteps.length > 0 ? (
            traceSteps.map((item, index) => (
              <article
                key={`${item.name}-${item.timestamp}-${index}`}
                className={`trace-item ${item.status === "completed" ? "completed" : ""}`}
              >
                <div className="trace-dot">{String(index + 1).padStart(2, "0")}</div>
                <div>
                  <strong>{item.name}</strong>
                  <p>{item.summary}</p>
                </div>
                <span className={`status-chip ${item.status === "completed" ? "success" : "warning"}`}>
                  {item.status}
                </span>
              </article>
            ))
          ) : (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">timeline</span>
              <p>发送请求后展示本轮真实执行链路。</p>
            </div>
          )}
        </div>

        <div className="panel-subsection">
          <h4>引用依据</h4>
          <div className="stack-list">
            {hasReferences ? (
              references.map((item) => (
                <article key={item.title} className="stack-item">
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.snippet}</p>
                  </div>
                  <span className="status-chip plain">{item.type}</span>
                </article>
              ))
            ) : hasLatestResponse ? (
              <article className="stack-item">
                <div>
                  <strong>无引用来源</strong>
                  <p>本轮回答未使用知识库检索结果。</p>
                </div>
                <span className="status-chip plain">model</span>
              </article>
            ) : null}
          </div>
        </div>
      </aside>
    </section>
  );
}
