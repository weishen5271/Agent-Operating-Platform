"use client";

import { ChangeEvent, FormEvent, useState } from "react";

import { ingestKnowledgeSource, ingestWikiSource } from "@/lib/api-client";
import type { AdminKnowledgeBasesResponse } from "@/lib/api-client/types";

type Status = {
  tone: "idle" | "success" | "error";
  message: string;
};

type KnowledgeIngestPanelProps = {
  knowledgeBaseCode?: string;
  knowledgeBases?: AdminKnowledgeBasesResponse["items"];
  target?: "rag" | "wiki";
};

export function KnowledgeIngestPanel({
  knowledgeBaseCode = "knowledge",
  knowledgeBases = [],
  target = "rag",
}: KnowledgeIngestPanelProps) {
  const availableKnowledgeBases = knowledgeBases;
  const [mode, setMode] = useState<"text" | "file">("file");
  const [name, setName] = useState("");
  const [owner, setOwner] = useState("知识平台组");
  const [content, setContent] = useState("");
  const [sourceType, setSourceType] = useState("Markdown");
  const [selectedKnowledgeBaseCode, setSelectedKnowledgeBaseCode] = useState(knowledgeBaseCode);
  const [selectedFileName, setSelectedFileName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<Status>({ tone: "idle", message: "" });

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    try {
      const text = await file.text();
      setName(file.name.replace(/\.[^.]+$/, ""));
      setSelectedFileName(file.name);
      setContent(text);
      const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
      if (extension === "md" || extension === "markdown") {
        setSourceType("Markdown");
      } else if (extension === "txt") {
        setSourceType("Text");
      } else if (extension === "json") {
        setSourceType("JSON");
      } else if (extension === "csv") {
        setSourceType("CSV");
      } else {
        setSourceType("Text");
      }
      setStatus({
        tone: "success",
        message: `已读取文件 ${file.name}，可以直接入库。`,
      });
    } catch (error) {
      setStatus({
        tone: "error",
        message: error instanceof Error ? error.message : "读取文件失败",
      });
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setStatus({ tone: "idle", message: "" });
    try {
      const ingest = target === "wiki" ? ingestWikiSource : ingestKnowledgeSource;
      const response = await ingest({
        knowledge_base_code: selectedKnowledgeBaseCode,
        name,
        owner,
        source_type: sourceType,
        content,
      });
      setStatus({
        tone: "success",
        message: `已入库 ${response.source.chunk_count} 个知识切片，检索索引已发布。`,
      });
      setName("");
      setContent("");
      setSelectedFileName("");
      window.location.reload();
    } catch (error) {
      setStatus({
        tone: "error",
        message: error instanceof Error ? error.message : "知识入库失败",
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel-card">
      <div className="panel-header">
        <div>
          <h3>知识入库</h3>
          <p>先把原始文件放进 Raw Sources，再进入切片、索引和 Wiki 编译链路。支持本地文件上传，也保留文本粘贴方式。</p>
        </div>
      </div>
      {availableKnowledgeBases.length === 0 ? (
        <span className="form-status error">请先创建知识库，再进行知识入库。</span>
      ) : null}
      <div className="console-tabs ingest-tabs">
        <button
          type="button"
          className={`console-tab ${mode === "file" ? "active" : ""}`}
          onClick={() => setMode("file")}
        >
          文件上传
        </button>
        <button
          type="button"
          className={`console-tab ${mode === "text" ? "active" : ""}`}
          onClick={() => setMode("text")}
        >
          文本粘贴
        </button>
      </div>
      <form className="knowledge-ingest-form" onSubmit={handleSubmit}>
        <label>
          <span>目标知识库</span>
          <select
            value={selectedKnowledgeBaseCode}
            disabled={availableKnowledgeBases.length === 0}
            onChange={(event) => setSelectedKnowledgeBaseCode(event.target.value)}
          >
            {availableKnowledgeBases.map((item) => (
              <option key={item.knowledge_base_code} value={item.knowledge_base_code}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>知识源名称</span>
          <input
            required
            value={name}
            maxLength={255}
            placeholder="例如：产品实施手册"
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          <span>负责人</span>
          <input
            required
            value={owner}
            maxLength={255}
            placeholder="知识平台组"
            onChange={(event) => setOwner(event.target.value)}
          />
        </label>
        <label>
          <span>源文件类型</span>
          <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
            <option value="Markdown">Markdown</option>
            <option value="Text">Text</option>
            <option value="JSON">JSON</option>
            <option value="CSV">CSV</option>
          </select>
        </label>
        {mode === "file" ? (
          <label className="full">
            <span>选择本地文件</span>
            <input type="file" accept=".md,.markdown,.txt,.json,.csv" onChange={handleFileChange} />
            <small className="field-hint">
              {selectedFileName ? `当前文件：${selectedFileName}` : "支持 .md / .txt / .json / .csv，读取后会落到 Raw Sources。"}
            </small>
          </label>
        ) : null}
        <label className="full">
          <span>{mode === "file" ? "文件内容预览" : "文档内容"}</span>
          <textarea
            required
            value={content}
            rows={8}
            placeholder={mode === "file" ? "选择文件后自动填充内容..." : "粘贴需要入库的 Markdown 或纯文本内容..."}
            onChange={(event) => setContent(event.target.value)}
          />
        </label>
        <div className="knowledge-ingest-footer">
          {status.message ? <span className={`form-status ${status.tone}`}>{status.message}</span> : <span />}
          <button
            type="submit"
            className="primary-button"
            disabled={submitting || availableKnowledgeBases.length === 0}
          >
            <span className="material-symbols-outlined">{submitting ? "hourglass_top" : "cloud_upload"}</span>
            {submitting ? "入库中" : "创建索引"}
          </button>
        </div>
      </form>
    </section>
  );
}
