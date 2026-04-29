"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  createChatConversation,
  deleteChatConversation,
  getCurrentUser,
  getChatConversation,
  getChatConversations,
  getTenantPackages,
  getTrace,
  streamChatCompletion,
  updateTenantPackages,
} from "@/lib/api-client";
import type {
  ChatCompletionResponse,
  ChatStreamEvent,
  ConversationListResponse,
  ConversationResponse,
  TenantPackagesResponse,
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
  duration_ms?: number | null;
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

const TRACE_STEP_LABELS: Record<string, string> = {
  received: "接收请求",
  input_guard: "输入检查",
  memory: "读取会话记忆",
  react_planner: "规划决策",
  classified: "意图识别",
  capability_candidates: "候选能力",
  skill_selected: "选择 Skill",
  slot_fill: "补齐槽位",
  planned: "执行计划",
  risk: "风险评估",
  governance: "治理校验",
  executed: "执行完成",
  tool_executed: "执行 Tool",
  model: "模型生成",
  output_guard: "输出审查",
  completed: "组装响应",
};

function nodeTypeMeta(type: string | null | undefined): { icon: string; label: string } {
  if (type && NODE_TYPE_META[type]) return NODE_TYPE_META[type];
  return { icon: "radio_button_checked", label: "Step" };
}

function traceStepLabel(name: string): string {
  if (TRACE_STEP_LABELS[name]) return TRACE_STEP_LABELS[name];
  if (name.startsWith("skill_step:")) return `Skill 步骤：${name.slice("skill_step:".length)}`;
  return name;
}

function traceStatusClass(status: string): string {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "skipped") return "plain";
  if (status === "running") return "warning pulse";
  return "warning";
}

function formatDuration(value: number | null | undefined): string {
  if (typeof value !== "number") return "-";
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

function traceStepDomId(index: number): string {
  return `trace-step-${index}`;
}

function nextTypewriterChunkSize(bufferLength: number): number {
  if (bufferLength > 240) return 36;
  if (bufferLength > 120) return 24;
  if (bufferLength > 48) return 14;
  return 8;
}

function pendingTraceStep(steps: RenderTraceStep[], intent: string | null | undefined): RenderTraceStep | null {
  const last = steps[steps.length - 1];
  if (!last || last.name === "completed" || last.status === "failed" || last.status === "skipped") return null;
  const nextByName: Record<string, Pick<RenderTraceStep, "name" | "summary" | "node_type">> = {
    received: { name: "input_guard", summary: "正在执行输入安全检查。", node_type: "guard" },
    input_guard: { name: "memory", summary: "正在读取会话记忆与长期知识摘要。", node_type: "runtime" },
    memory: { name: "react_planner", summary: "正在进行 LLM Planner 或规则规划。", node_type: "runtime" },
    react_planner: { name: "classified", summary: "正在确认意图与执行策略。", node_type: "runtime" },
    classified: { name: "capability_candidates", summary: "正在筛选当前用户可用能力。", node_type: "runtime" },
    capability_candidates: { name: "planned", summary: "正在选择 Skill、Tool 或 capability 执行路径。", node_type: "runtime" },
    skill_selected: { name: "slot_fill", summary: "正在补齐 Skill 必需入参。", node_type: "skill" },
    slot_fill: { name: "planned", summary: "正在生成执行计划。", node_type: "runtime" },
    planned: { name: "risk", summary: "正在评估风险等级与自主度。", node_type: "guard" },
    risk: { name: "governance", summary: "正在校验权限、配额与治理规则。", node_type: "guard" },
    governance: { name: "executed", summary: "正在调用已选能力。", node_type: "capability" },
    executed: intent === "knowledge_query" || intent === "wiki_query" || intent === "general_chat"
      ? { name: "model", summary: "正在生成模型回答。", node_type: "skill" }
      : { name: "output_guard", summary: "正在进行输出审查。", node_type: "guard" },
    model: { name: "output_guard", summary: "正在进行输出审查。", node_type: "guard" },
    output_guard: { name: "completed", summary: "正在组装最终响应。", node_type: "runtime" },
  };
  if (last.name.startsWith("skill_step:")) {
    return {
      name: "executed",
      summary: "正在继续执行 Skill 编排或汇总步骤结果。",
      status: "running",
      timestamp: "running",
      node_type: "skill",
    };
  }
  const next = nextByName[last.name];
  if (!next) return null;
  return {
    ...next,
    status: "running",
    timestamp: "running",
  };
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

function readPackageContext(defaults?: TenantPackagesResponse | null) {
  // 业务包上下文通过 URL 临时切换，只影响当前请求，不修改租户后台绑定。
  if (typeof window === "undefined") return undefined;
  const params = new URLSearchParams(window.location.search);
  const primary = params.get("primary") || defaults?.primary_package || undefined;
  const commons = params.get("commons")?.split(",").filter(Boolean) ?? defaults?.common_packages ?? [];
  if (!primary && commons.length === 0) return undefined;
  return {
    primary_package: primary,
    common_packages: commons,
  };
}

function packageLabel(packages: TenantPackagesResponse | null, packageId: string | null | undefined): string {
  if (!packageId) return "未选择";
  const item = packages?.available_packages.find((candidate) => candidate.package_id === packageId);
  return item ? `${item.name}${item.version ? ` ${item.version}` : ""}` : packageId;
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
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [tenantPackages, setTenantPackages] = useState<TenantPackagesResponse | null>(null);
  const [selectedPrimaryPackage, setSelectedPrimaryPackage] = useState("");
  const [selectedCommonPackages, setSelectedCommonPackages] = useState<string[]>([]);
  const [isSavingPackageDefaults, setIsSavingPackageDefaults] = useState(false);
  const [packageError, setPackageError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTraceStep, setExpandedTraceStep] = useState<number | null>(null);
  const [highlightedTraceStep, setHighlightedTraceStep] = useState<number | null>(null);
  const [isRefreshingTrace, setIsRefreshingTrace] = useState(false);
  const [streamingAssistantMessageId, setStreamingAssistantMessageId] = useState<string | null>(null);
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

  useEffect(() => {
    let cancelled = false;

    async function loadPackageContext() {
      try {
        const user = await getCurrentUser();
        if (cancelled) return;
        setTenantId(user.tenant_id);
        const packages = await getTenantPackages(user.tenant_id);
        if (cancelled) return;
        const urlContext = readPackageContext(packages);
        const fallbackPrimary =
          urlContext?.primary_package ||
          packages.primary_package ||
          packages.available_packages.find((item) => item.domain === "industry")?.package_id ||
          "";
        setTenantPackages(packages);
        setSelectedPrimaryPackage(fallbackPrimary);
        setSelectedCommonPackages(urlContext?.common_packages ?? packages.common_packages);
        setPackageError(null);
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "业务包上下文加载失败。";
          setPackageError(message);
        }
      }
    }

    loadPackageContext();

    return () => {
      cancelled = true;
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
    setExpandedTraceStep(null);
    setHighlightedTraceStep(null);
    setStreamingAssistantMessageId(null);
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
      setExpandedTraceStep(null);
      setHighlightedTraceStep(null);
      setStreamingAssistantMessageId(null);
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
      duration_ms: item.duration_ms ?? null,
    })) ?? [];

  const runningTraceStep = isStreaming ? pendingTraceStep(traceSteps, trace?.intent) : null;
  const visibleTraceSteps: RenderTraceStep[] = runningTraceStep ? [...traceSteps, runningTraceStep] : traceSteps;
  const knownDurationSteps = traceSteps.filter((item) => typeof item.duration_ms === "number");
  const totalDurationMs = knownDurationSteps.reduce((sum, item) => sum + (item.duration_ms ?? 0), 0);
  const modelDurationMs = traceSteps
    .filter((item) => item.name === "model")
    .reduce((sum, item) => sum + (item.duration_ms ?? 0), 0);
  const retrievalDurationMs = traceSteps
    .filter((item) => item.node_type === "retrieval")
    .reduce((sum, item) => sum + (item.duration_ms ?? 0), 0);
  const toolDurationMs = traceSteps
    .filter((item) => item.node_type === "tool")
    .reduce((sum, item) => sum + (item.duration_ms ?? 0), 0);
  const failedStepCount = traceSteps.filter((item) => item.status === "failed").length;
  const skippedStepCount = traceSteps.filter((item) => item.status === "skipped").length;

  const usedSkills = aggregateUsedRefs(traceSteps, "skill");
  const usedTools = aggregateUsedRefs(traceSteps, "tool");
  const routing = latestResponse?.routing ?? null;
  const industryPackages = tenantPackages?.available_packages.filter((item) => item.domain === "industry") ?? [];
  const commonPackageOptions = tenantPackages?.available_packages.filter((item) => item.domain === "common") ?? [];
  const selectedPackageStatus = tenantPackages?.available_packages.find(
    (item) => item.package_id === selectedPrimaryPackage,
  )?.status;

  function syncPackageQuery(nextPrimary: string, nextCommons: string[]) {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (nextPrimary) {
      params.set("primary", nextPrimary);
    } else {
      params.delete("primary");
    }
    if (nextCommons.length > 0) {
      params.set("commons", nextCommons.join(","));
    } else {
      params.delete("commons");
    }
    const suffix = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${suffix ? `?${suffix}` : ""}`);
  }

  function selectPrimaryPackage(packageId: string) {
    setSelectedPrimaryPackage(packageId);
    syncPackageQuery(packageId, selectedCommonPackages);
  }

  function toggleCommonPackage(packageId: string) {
    const next = selectedCommonPackages.includes(packageId)
      ? selectedCommonPackages.filter((item) => item !== packageId)
      : [...selectedCommonPackages, packageId];
    setSelectedCommonPackages(next);
    syncPackageQuery(selectedPrimaryPackage, next);
  }

  async function savePackageDefaults() {
    if (!tenantId || !selectedPrimaryPackage) return;
    setIsSavingPackageDefaults(true);
    setPackageError(null);
    try {
      const updated = await updateTenantPackages(tenantId, {
        primary_package: selectedPrimaryPackage,
        common_packages: selectedCommonPackages,
      });
      setTenantPackages(updated);
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存业务包默认配置失败。";
      setPackageError(message);
    } finally {
      setIsSavingPackageDefaults(false);
    }
  }

  async function submitMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed || isStreaming) return;

    const userMessageId = crypto.randomUUID();
    const assistantMessageId = crypto.randomUUID();
    hasStartedLocalConversationRef.current = true;
    // 先乐观插入用户消息和空助手消息，后续 SSE 增量会持续填充助手气泡。
    setError(null);
    setLatestResponse(null);
    setExpandedTraceStep(null);
    setHighlightedTraceStep(null);
    setStreamingAssistantMessageId(assistantMessageId);
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
        selectedPrimaryPackage
          ? {
              primary_package: selectedPrimaryPackage,
              common_packages: selectedCommonPackages,
            }
          : undefined,
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

  async function refreshTrace() {
    if (!trace?.trace_id || isStreaming || isRefreshingTrace) return;
    setIsRefreshingTrace(true);
    setError(null);
    try {
      const nextTrace = await getTrace(trace.trace_id);
      setTrace(nextTrace);
      setHighlightedTraceStep(null);
      if (expandedTraceStep !== null && expandedTraceStep >= nextTrace.steps.length) {
        setExpandedTraceStep(null);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Trace 刷新失败。";
      setError(`Trace 刷新失败：${message}`);
    } finally {
      setIsRefreshingTrace(false);
    }
  }

  function warningTargetIndex(tip: string): number | null {
    const normalized = tip.toLowerCase();
    if (normalized.includes("llm") || normalized.includes("模型")) {
      const modelIndex = traceSteps.findIndex((step) => step.name === "model" && step.status !== "completed");
      if (modelIndex >= 0) return modelIndex;
    }
    if (tip.includes("OutputGuard") || tip.includes("拦截")) {
      const guardIndex = traceSteps.findIndex((step) => step.name === "output_guard");
      if (guardIndex >= 0) return guardIndex;
    }
    const failedIndex = traceSteps.findIndex((step) => step.status === "failed" || step.status === "skipped");
    return failedIndex >= 0 ? failedIndex : null;
  }

  function focusTraceStep(index: number | null) {
    if (index === null) return;
    setExpandedTraceStep(index);
    setHighlightedTraceStep(index);
    window.setTimeout(() => {
      document.getElementById(traceStepDomId(index))?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, 0);
    window.setTimeout(() => {
      setHighlightedTraceStep((current) => (current === index ? null : current));
    }, 1800);
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
          setStreamingAssistantMessageId(null);
        }
        return;
      }

      const takeSize = nextTypewriterChunkSize(buffer.length);
      const nextChunk = buffer.slice(0, takeSize);
      deltaBuffersRef.current[messageId] = buffer.slice(takeSize);
      appendAssistantContent(messageId, nextChunk);
    }, 32);
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
      setStreamingAssistantMessageId(null);
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

        <div className="chat-package-context">
          <div className="chat-package-main">
            <label htmlFor="chat-primary-package">
              <span className="material-symbols-outlined">deployed_code</span>
              业务包
            </label>
            <select
              id="chat-primary-package"
              value={selectedPrimaryPackage}
              disabled={isStreaming || !tenantPackages}
              onChange={(event) => selectPrimaryPackage(event.target.value)}
            >
              <option value="">未选择业务包</option>
              {industryPackages.map((item) => (
                <option key={item.package_id} value={item.package_id}>
                  {item.name} {item.version ?? ""}
                </option>
              ))}
            </select>
            <span className={`status-chip plain ${selectedPrimaryPackage ? "info" : "warning"}`}>
              {selectedPackageStatus || (selectedPrimaryPackage ? "当前请求上下文" : "未选择")}
            </span>
          </div>

          <div className="chat-package-common">
            {commonPackageOptions.map((item) => (
              <button
                key={item.package_id}
                type="button"
                className={`package-chip ${selectedCommonPackages.includes(item.package_id) ? "active" : ""}`}
                disabled={isStreaming}
                onClick={() => toggleCommonPackage(item.package_id)}
                title={item.package_id}
              >
                {item.name}
              </button>
            ))}
            <button
              type="button"
              className="secondary-button compact"
              disabled={!tenantId || !selectedPrimaryPackage || isSavingPackageDefaults}
              onClick={savePackageDefaults}
            >
              <span className="material-symbols-outlined">save</span>
              {isSavingPackageDefaults ? "保存中..." : "设为默认"}
            </button>
          </div>

          <div className="chat-package-summary">
            <span>{packageLabel(tenantPackages, selectedPrimaryPackage)}</span>
            {selectedCommonPackages.length > 0 ? (
              <span>+ {selectedCommonPackages.map((item) => packageLabel(tenantPackages, item)).join("、")}</span>
            ) : (
              <span>未叠加通用包</span>
            )}
          </div>
          {packageError ? <p className="inline-error">{packageError}</p> : null}
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
                        ? message.id === streamingAssistantMessageId
                          ? <span className="streaming-plain-text">{message.content}</span>
                          : renderMarkdown(message.content)
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
              <button
                key={tip}
                type="button"
                className="chat-warning-item"
                onClick={() => focusTraceStep(warningTargetIndex(tip))}
              >
                <span className="material-symbols-outlined">warning</span>
                <span>{tip}</span>
                <span className="material-symbols-outlined warning-jump">travel_explore</span>
              </button>
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
          <button
            type="button"
            className="ghost-button"
            disabled={!trace?.trace_id || isStreaming || isRefreshingTrace}
            onClick={refreshTrace}
          >
            <span className="material-symbols-outlined">refresh</span>
            {isRefreshingTrace ? "刷新中..." : "刷新"}
          </button>
        </div>

        {traceSteps.length > 0 ? (
          <div className="trace-summary-grid">
            <div>
              <span>总耗时</span>
              <strong>{knownDurationSteps.length ? formatDuration(totalDurationMs) : "-"}</strong>
            </div>
            <div>
              <span>模型</span>
              <strong>{modelDurationMs ? formatDuration(modelDurationMs) : "-"}</strong>
            </div>
            <div>
              <span>检索</span>
              <strong>{retrievalDurationMs ? formatDuration(retrievalDurationMs) : "-"}</strong>
            </div>
            <div>
              <span>工具</span>
              <strong>{toolDurationMs ? formatDuration(toolDurationMs) : "-"}</strong>
            </div>
            <div>
              <span>异常</span>
              <strong>{failedStepCount + skippedStepCount}</strong>
            </div>
          </div>
        ) : null}

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
          {visibleTraceSteps.length > 0 ? (
            visibleTraceSteps.map((item, index) => {
              const meta = nodeTypeMeta(item.node_type);
              const isExpanded = expandedTraceStep === index;
              const statusClass = traceStatusClass(item.status);
              return (
                <article
                  key={`${item.name}-${item.timestamp}-${index}`}
                  id={traceStepDomId(index)}
                  className={[
                    "trace-item",
                    item.status,
                    isExpanded ? "expanded" : "",
                    highlightedTraceStep === index ? "highlighted" : "",
                  ].filter(Boolean).join(" ")}
                >
                  <div className="trace-dot" title={meta.label}>
                    <span className="material-symbols-outlined">{meta.icon}</span>
                  </div>
                  <div className="trace-main">
                    <button
                      type="button"
                      className="trace-step-toggle"
                      onClick={() => setExpandedTraceStep(isExpanded ? null : index)}
                    >
                      <span>
                        <strong>{traceStepLabel(item.name)}</strong>
                        <span className="trace-step-raw">{item.name}</span>
                      </span>
                      <span className="material-symbols-outlined">
                        {isExpanded ? "expand_less" : "expand_more"}
                      </span>
                    </button>
                    <p>{item.summary}</p>
                    {item.ref ? (
                      <div className="trace-ref-line">
                        <span className="mono">{item.ref}</span>
                        {item.ref_source ? <span>{item.ref_source}</span> : null}
                        {item.ref_version ? <span>{item.ref_version}</span> : null}
                      </div>
                    ) : null}
                    {isExpanded ? (
                      <dl className="trace-detail-grid">
                        <div>
                          <dt>原始节点</dt>
                          <dd>{item.name}</dd>
                        </div>
                        <div>
                          <dt>类型</dt>
                          <dd>{meta.label}</dd>
                        </div>
                        <div>
                          <dt>状态</dt>
                          <dd>{item.status}</dd>
                        </div>
                        <div>
                          <dt>耗时</dt>
                          <dd>{formatDuration(item.duration_ms)}</dd>
                        </div>
                        <div>
                          <dt>引用</dt>
                          <dd>{item.ref ?? "-"}</dd>
                        </div>
                        <div>
                          <dt>来源</dt>
                          <dd>{item.ref_source ?? "-"}</dd>
                        </div>
                        <div>
                          <dt>版本</dt>
                          <dd>{item.ref_version ?? "-"}</dd>
                        </div>
                      </dl>
                    ) : null}
                  </div>
                  <span className={`status-chip ${statusClass}`}>
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
