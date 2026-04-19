"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { createChatCompletion, getTrace } from "@/lib/api-client";
import type { ChatCompletionResponse, TraceResponse } from "@/lib/api-client/types";
import { chatData } from "@/lib/workspace-fixtures";

type RenderMessage = {
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

function nowTime(): string {
  return new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function ChatWorkbench() {
  const [messages, setMessages] = useState<RenderMessage[]>(
    chatData.messages.map((item) => ({
      role: item.role as "user" | "assistant",
      content: item.content,
      time: item.time,
    })),
  );
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [input, setInput] = useState(
    "帮我生成这次采购审批的草稿，并标注风险等级和审批链。",
  );
  const [latestResponse, setLatestResponse] = useState<ChatCompletionResponse | null>(null);
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const references = latestResponse
    ? latestResponse.sources.map((item) => ({
        title: item.title,
        snippet: item.snippet,
        type: item.source_type,
      }))
    : chatData.references;

  const hasLatestResponse = latestResponse !== null;
  const hasReferences = references.length > 0;

  const traceSteps: RenderTraceStep[] = trace?.steps
    ? trace.steps.map((item) => ({
        name: item.name,
        summary: item.summary,
        status: item.status,
        timestamp: item.timestamp ?? item.name,
      }))
    : chatData.trace.map((item) => ({
        name: item.step,
        summary: item.summary,
        status: item.status,
        timestamp: item.step,
      }));

  function submitMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed) return;

    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: trimmed, time: nowTime() }]);
    setInput("");

    startTransition(async () => {
      try {
        const completion = await createChatCompletion(trimmed);
        setLatestResponse(completion);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: completion.message.content,
            time: nowTime(),
          },
        ]);
        const traceDetail = await getTrace(completion.trace_id);
        setTrace(traceDetail);
      } catch (err) {
        const message = err instanceof Error ? err.message : "请确认后端 API 已启动。";
        setError(`请求失败：${message}`);
      }
    });
  }

  return (
    <section className="chat-debug-layout">
      <section className="panel-card chat-panel">
        <div className="panel-header">
          <div>
            <h3>对话演练场</h3>
            <p>模拟真实用户环境测试 Agent 的逻辑响应。</p>
          </div>
          <span className={`status-chip ${isPending ? "warning pulse" : "success"}`}>
            {isPending ? "生成中" : "就绪"}
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

        <div className="chat-history">
          {messages.map((message) => (
            <article
              key={`${message.role}-${message.time}-${message.content.slice(0, 12)}`}
              className={`chat-bubble-row ${message.role}`}
            >
              <div className="bubble-avatar">
                <span className="material-symbols-outlined">
                  {message.role === "user" ? "person" : "smart_toy"}
                </span>
              </div>
              <div className="bubble-column">
                <div className={`chat-bubble ${message.role}`}>{message.content}</div>
                <span className="bubble-time">{message.time}</span>
              </div>
            </article>
          ))}
        </div>

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
              disabled={isPending}
              onClick={() => submitMessage(input)}
            >
              <span className="material-symbols-outlined">send</span>
              {isPending ? "处理中..." : "发送请求"}
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
          {traceSteps.map((item, index) => (
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
          ))}
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
