"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  createChatConversation,
  deleteChatConversation,
  getChatConversation,
  getChatConversations,
  streamChatCompletion,
} from "@/lib/api-client";
import type {
  ChatCompletionResponse,
  ChatStreamEvent,
  ConversationListResponse,
  ConversationResponse,
  TraceResponse,
} from "@/lib/api-client/types";
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
  node_type?: string | null;
  ref?: string | null;
  ref_source?: string | null;
  ref_version?: string | null;
};

type ConversationSummary = ConversationListResponse["items"][number];

const NODE_TYPE_META: Record<string, { icon: string; label: string }> = {
  capability: { icon: "extension", label: "Capability" },
  tool: { icon: "build", label: "Tool" },
  skill: { icon: "auto_awesome", label: "Skill" },
  retrieval: { icon: "search", label: "检索" },
  guard: { icon: "shield", label: "Guard" },
  runtime: { icon: "play_circle", label: "Runtime" },
};

function nodeTypeMeta(type: string | null | undefined): { icon: string; label: string } {
  if (type && NODE_TYPE_META[type]) return NODE_TYPE_META[type];
  return { icon: "radio_button_checked", label: "Step" };
}

type UsedRef = {
  ref: string;
  ref_source: string | null;
  ref_version: string | null;
  count: number;
};

function aggregateUsedRefs(steps: RenderTraceStep[], type: "skill" | "tool"): UsedRef[] {
  // Trace step 是后端运行过程的唯一来源，这里聚合出本轮真正触发过的 skill/tool。
  const map = new Map<string, UsedRef>();
  for (const step of steps) {
    if (step.node_type !== type || !step.ref) continue;
    const key = step.ref;
    const existing = map.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      map.set(key, {
        ref: step.ref,
        ref_source: step.ref_source ?? null,
        ref_version: step.ref_version ?? null,
        count: 1,
      });
    }
  }
  return [...map.values()];
}

function readPackageContext() {
  // 业务包上下文通过 URL 临时切换，只影响当前请求，不修改租户后台绑定。
  if (typeof window === "undefined") return undefined;
  const params = new URLSearchParams(window.location.search);
  const primary = params.get("primary") || undefined;
  const commons = params.get("commons")?.split(",").filter(Boolean) ?? [];
  if (!primary && commons.length === 0) return undefined;
  return {
    primary_package: primary,
    common_packages: commons,
  };
}

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
  // 对话区只支持当前需要的轻量 Markdown 子集，避免引入完整渲染器扩大前端依赖面。
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
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [isConversationListCollapsed, setIsConversationListCollapsed] = useState(false);
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
        // 首屏恢复最近会话；如果用户已在本地新建/发送，则不再用历史结果覆盖当前状态。
        const conversations = await getChatConversations();
        if (cancelled) return;
        setConversations(conversations.items);
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

  async function refreshConversations() {
    const next = await getChatConversations();
    setConversations(next.items);
  }

  function resetConversationState(nextConversationId?: string) {
    // 切换会话时同步清理 Trace、增量缓冲和打字机定时器，防止旧流式内容串到新会话。
    setConversationId(nextConversationId);
    setMessages([]);
    setTrace(null);
    setLatestResponse(null);
    setError(null);
    deltaBuffersRef.current = {};
    finalContentRef.current = {};
    Object.values(typewriterTimersRef.current).forEach((timer) => window.clearInterval(timer));
    typewriterTimersRef.current = {};
  }

  async function createConversation() {
    if (isStreaming) return;
    try {
      const conversation = await createChatConversation();
      hasStartedLocalConversationRef.current = true;
      resetConversationState(conversation.conversation_id);
      setConversations((prev) => [
        {
          conversation_id: conversation.conversation_id,
          title: conversation.title,
          updated_at: conversation.updated_at,
        },
        ...prev,
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "新建会话失败。";
      setError(`新建会话失败：${message}`);
    }
  }

  async function selectConversation(nextConversationId: string) {
    if (isStreaming || nextConversationId === conversationId) return;
    try {
      const conversation = await getChatConversation(nextConversationId);
      hasStartedLocalConversationRef.current = true;
      setConversationId(conversation.conversation_id);
      setMessages(conversationToMessages(conversation));
      setTrace(null);
      setLatestResponse(null);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "会话加载失败。";
      setError(`会话加载失败：${message}`);
    }
  }

  async function removeConversation(targetConversationId: string) {
    if (isStreaming) return;
    try {
      await deleteChatConversation(targetConversationId);
      const remaining = conversations.filter((item) => item.conversation_id !== targetConversationId);
      setConversations(remaining);
      if (targetConversationId !== conversationId) return;
      const next = remaining[0];
      if (next) {
        await selectConversation(next.conversation_id);
      } else {
        resetConversationState(undefined);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "删除会话失败。";
      setError(`删除会话失败：${message}`);
    }
  }

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
      node_type: item.node_type ?? null,
      ref: item.ref ?? null,
      ref_source: item.ref_source ?? null,
      ref_version: item.ref_version ?? null,
    })) ?? [];

  const usedSkills = aggregateUsedRefs(traceSteps, "skill");
  const usedTools = aggregateUsedRefs(traceSteps, "tool");
  const routing = latestResponse?.routing ?? null;

  async function submitMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed || isStreaming) return;

    const userMessageId = crypto.randomUUID();
    const assistantMessageId = crypto.randomUUID();
    hasStartedLocalConversationRef.current = true;
    // 先乐观插入用户消息和空助手消息，后续 SSE 增量会持续填充助手气泡。
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
      // 后端 SSE 会依次返回 trace_step、response_meta、message_delta 和 message_done。
      await streamChatCompletion(
        trimmed,
        retrievalMode,
        (event) => {
          handleStreamEvent(event, assistantMessageId, trimmed);
        },
        conversationId,
        readPackageContext(),
      );
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

  function switchPackageAndResend(packageId: string) {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      params.set("primary", packageId);
      window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
    }
    void submitMessage(trace?.message || input);
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
      // 网络增量先进入 buffer，再由本地定时器平滑输出，避免 UI 因 chunk 大小抖动。
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
      // Trace step 先到达，右侧执行链路可以早于最终回答逐步展示。
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
      // 元数据到达后补齐 conversation_id、intent、routing 和引用来源。
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
        routing: event.routing ?? null,
      });
      return;
    }

    if (event.event === "message_delta") {
      enqueueAssistantDelta(assistantMessageId, event.content);
      return;
    }

    if (event.event === "message_done") {
      // 最终内容以 message_done 为准，用它覆盖本地打字机可能尚未完全输出的缓冲。
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
      void refreshConversations();
    }
  }

  return (
    <section className={`chat-debug-layout ${isConversationListCollapsed ? "conversation-list-collapsed" : ""}`}>
      <aside className="panel-card conversation-panel">
        <div className="conversation-panel-header">
          {!isConversationListCollapsed ? (
            <>
              <div>
                <h3>会话</h3>
                <p>按最近更新时间排序</p>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="收起会话列表"
                onClick={() => setIsConversationListCollapsed(true)}
              >
                <span className="material-symbols-outlined">left_panel_close</span>
              </button>
            </>
          ) : (
            <button
              type="button"
              className="icon-button"
              aria-label="展开会话列表"
              onClick={() => setIsConversationListCollapsed(false)}
            >
              <span className="material-symbols-outlined">left_panel_open</span>
            </button>
          )}
        </div>

        {!isConversationListCollapsed ? (
          <>
            <button
              type="button"
              className="primary-button conversation-new-button"
              disabled={isStreaming}
              onClick={createConversation}
            >
              <span className="material-symbols-outlined">add</span>
              新增会话
            </button>
            <div className="conversation-list">
              {conversations.length > 0 ? (
                conversations.map((item) => (
                  <article
                    key={item.conversation_id}
                    className={`conversation-item ${conversationId === item.conversation_id ? "active" : ""}`}
                  >
                    <button
                      type="button"
                      className="conversation-select"
                      disabled={isStreaming}
                      onClick={() => selectConversation(item.conversation_id)}
                    >
                      <span className="material-symbols-outlined">chat_bubble</span>
                      <span>{item.title || "新会话"}</span>
                    </button>
                    <button
                      type="button"
                      className="icon-button danger"
                      aria-label={`删除会话 ${item.title || "新会话"}`}
                      disabled={isStreaming}
                      onClick={() => removeConversation(item.conversation_id)}
                    >
                      <span className="material-symbols-outlined">delete</span>
                    </button>
                  </article>
                ))
              ) : (
                <div className="conversation-empty">
                  <span className="material-symbols-outlined">forum</span>
                  <p>暂无会话</p>
                </div>
              )}
            </div>
          </>
        ) : null}
      </aside>

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

        {routing ? (
          <div className="panel-subsection">
            <h4>路由解释</h4>
            <article className="stack-item">
              <div>
                <strong>{routing.matched_package_id}</strong>
                <p>
                  置信度 {(routing.confidence * 100).toFixed(0)}%
                  {routing.signals.length ? ` · ${routing.signals.join(" · ")}` : ""}
                </p>
              </div>
              <span className="status-chip plain">routing</span>
            </article>
            {routing.candidates.length ? (
              <div className="routing-candidates">
                {routing.candidates.map((candidate) => (
                  <article key={candidate.package_id} className="routing-candidate">
                    <div>
                      <strong>{candidate.package_id}</strong>
                      <div className="routing-confidence" aria-label={`置信度 ${(candidate.confidence * 100).toFixed(0)}%`}>
                        <span style={{ width: `${Math.round(candidate.confidence * 100)}%` }} />
                      </div>
                    </div>
                    <button
                      type="button"
                      className="ghost-button compact"
                      disabled={isStreaming}
                      onClick={() => switchPackageAndResend(candidate.package_id)}
                    >
                      <span className="material-symbols-outlined">replay</span>
                      切换重发
                    </button>
                  </article>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="trace-list">
          {traceSteps.length > 0 ? (
            traceSteps.map((item, index) => {
              const meta = nodeTypeMeta(item.node_type);
              return (
                <article
                  key={`${item.name}-${item.timestamp}-${index}`}
                  className={`trace-item ${item.status === "completed" ? "completed" : ""}`}
                >
                  <div className="trace-dot" title={meta.label}>
                    <span className="material-symbols-outlined">{meta.icon}</span>
                  </div>
                  <div>
                    <strong>
                      {item.name}
                      {item.ref ? (
                        <span className="mono" style={{ marginLeft: 8, opacity: 0.7 }}>
                          {item.ref}
                          {item.ref_source ? ` @${item.ref_source}` : ""}
                        </span>
                      ) : null}
                    </strong>
                    <p>{item.summary}</p>
                  </div>
                  <span className={`status-chip ${item.status === "completed" ? "success" : "warning"}`}>
                    {item.status}
                  </span>
                </article>
              );
            })
          ) : (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">timeline</span>
              <p>发送请求后展示本轮真实执行链路。</p>
            </div>
          )}
        </div>

        {usedSkills.length > 0 ? (
          <div className="panel-subsection">
            <h4>已用 Skill</h4>
            <div className="stack-list">
              {usedSkills.map((item) => (
                <article key={`skill-${item.ref}`} className="stack-item">
                  <div>
                    <strong>{item.ref}</strong>
                    <p>
                      {item.ref_source ?? "package"}
                      {item.ref_version ? ` · ${item.ref_version}` : ""}
                      {item.count > 1 ? ` · 调用 ${item.count} 次` : ""}
                    </p>
                  </div>
                  <span className="status-chip plain">skill</span>
                </article>
              ))}
            </div>
          </div>
        ) : null}

        {usedTools.length > 0 ? (
          <div className="panel-subsection">
            <h4>已用 Tool</h4>
            <div className="stack-list">
              {usedTools.map((item) => (
                <article key={`tool-${item.ref}`} className="stack-item">
                  <div>
                    <strong>{item.ref}</strong>
                    <p>
                      {item.ref_source ?? "_platform"}
                      {item.ref_version ? ` · ${item.ref_version}` : ""}
                      {item.count > 1 ? ` · 调用 ${item.count} 次` : ""}
                    </p>
                  </div>
                  <span className="status-chip plain">tool</span>
                </article>
              ))}
            </div>
          </div>
        ) : null}

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
