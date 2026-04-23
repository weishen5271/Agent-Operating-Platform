"use client";

import { FormEvent, useState } from "react";

import { ingestKnowledgeSource } from "@/lib/api-client";

type Status = {
  tone: "idle" | "success" | "error";
  message: string;
};

export function KnowledgeIngestPanel() {
  const [name, setName] = useState("");
  const [owner, setOwner] = useState("知识平台组");
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<Status>({ tone: "idle", message: "" });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setStatus({ tone: "idle", message: "" });
    try {
      const response = await ingestKnowledgeSource({
        name,
        owner,
        source_type: "Markdown",
        content,
      });
      setStatus({
        tone: "success",
        message: `已入库 ${response.source.chunk_count} 个知识切片，检索索引已发布。`,
      });
      setName("");
      setContent("");
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
          <p>提交 Markdown 或纯文本后，系统会完成切片、向量创建、索引发布，并进入 RAG 检索链路。</p>
        </div>
      </div>
      <form className="knowledge-ingest-form" onSubmit={handleSubmit}>
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
        <label className="full">
          <span>文档内容</span>
          <textarea
            required
            value={content}
            rows={8}
            placeholder="粘贴需要入库的 Markdown 或纯文本内容..."
            onChange={(event) => setContent(event.target.value)}
          />
        </label>
        <div className="knowledge-ingest-footer">
          {status.message ? <span className={`form-status ${status.tone}`}>{status.message}</span> : <span />}
          <button type="submit" className="primary-button" disabled={submitting}>
            <span className="material-symbols-outlined">{submitting ? "hourglass_top" : "cloud_upload"}</span>
            {submitting ? "入库中" : "创建索引"}
          </button>
        </div>
      </form>
    </section>
  );
}
