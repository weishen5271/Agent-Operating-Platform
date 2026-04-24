"use client";

import { FormEvent, useMemo, useState } from "react";

import { createKnowledgeBase, deleteKnowledgeBase, updateKnowledgeBase } from "@/lib/api-client";
import { Modal } from "@/components/shared/modal";
import type { AdminKnowledgeBasesResponse } from "@/lib/api-client/types";

type KnowledgeBaseManagerProps = {
  knowledgeBases: AdminKnowledgeBasesResponse["items"];
  selectedKnowledgeBase: string;
};

export function KnowledgeBaseManager({
  knowledgeBases,
  selectedKnowledgeBase,
}: KnowledgeBaseManagerProps) {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const editingItem = useMemo(
    () => knowledgeBases.find((item) => item.knowledge_base_code === editingCode) ?? null,
    [editingCode, knowledgeBases],
  );

  function openCreateModal() {
    setCode("");
    setName("");
    setDescription("");
    setIsCreateOpen(true);
  }

  function openEditModal(item: AdminKnowledgeBasesResponse["items"][number]) {
    setEditingCode(item.knowledge_base_code);
    setCode(item.knowledge_base_code);
    setName(item.name);
    setDescription(item.description);
  }

  function gotoKnowledgeBase(knowledgeBaseCode: string) {
    window.location.href = `/knowledge?tab=wiki&knowledgeBase=${encodeURIComponent(knowledgeBaseCode)}`;
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await createKnowledgeBase({
      knowledge_base_code: code.trim(),
      name: name.trim(),
      description: description.trim(),
    });
    setIsCreateOpen(false);
    gotoKnowledgeBase(code.trim());
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingItem) {
      return;
    }
    await updateKnowledgeBase(editingItem.knowledge_base_code, {
      name: name.trim(),
      description: description.trim(),
      status: editingItem.status,
    });
    setEditingCode(null);
    window.location.reload();
  }

  async function handleToggle(item: AdminKnowledgeBasesResponse["items"][number]) {
    await updateKnowledgeBase(item.knowledge_base_code, {
      name: item.name,
      description: item.description,
      status: item.status === "active" ? "archived" : "active",
    });
    window.location.reload();
  }

  async function handleDelete(item: AdminKnowledgeBasesResponse["items"][number]) {
    await deleteKnowledgeBase(item.knowledge_base_code);
    window.location.href = "/knowledge?tab=wiki&knowledgeBase=knowledge";
  }

  return (
    <section className="panel-card">
      <div className="panel-header">
        <div>
          <h3>知识库管理</h3>
          <p>点击知识库可直接进入该知识库详情，查看对应的 Wiki 文件空间与分布状态。</p>
        </div>
        <button type="button" className="primary-button" onClick={openCreateModal}>
          <span className="material-symbols-outlined">library_add</span>
          新建知识库
        </button>
      </div>
      <div className="stack-list">
        {knowledgeBases.map((item) => (
          <article
            key={item.knowledge_base_code}
            className={`stack-item stack-button ${item.knowledge_base_code === selectedKnowledgeBase ? "active" : ""}`}
            onClick={() => gotoKnowledgeBase(item.knowledge_base_code)}
          >
            <div>
              <strong>{item.name}</strong>
              <p>{item.knowledge_base_code}</p>
              <p className="stack-subtle">{item.description || "暂无描述"}</p>
            </div>
            <div className="stack-meta">
              <span className={`status-chip ${item.knowledge_base_code === selectedKnowledgeBase ? "success" : ""}`}>
                {item.status}
              </span>
              <button
                type="button"
                className="secondary-button"
                onClick={(event) => {
                  event.stopPropagation();
                  openEditModal(item);
                }}
              >
                编辑
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={(event) => {
                  event.stopPropagation();
                  void handleToggle(item);
                }}
              >
                {item.status === "active" ? "归档" : "启用"}
              </button>
              {item.knowledge_base_code !== "knowledge" ? (
                <button
                  type="button"
                  className="secondary-button danger-lite"
                  onClick={(event) => {
                    event.stopPropagation();
                    void handleDelete(item);
                  }}
                >
                  删除
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>

      <Modal isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="新建知识库">
        <form className="knowledge-ingest-form" onSubmit={handleCreate}>
          <label>
            <span>知识库编码</span>
            <input value={code} required onChange={(event) => setCode(event.target.value)} placeholder="例如 finance" />
          </label>
          <label>
            <span>知识库名称</span>
            <input value={name} required onChange={(event) => setName(event.target.value)} placeholder="例如 财务知识库" />
          </label>
          <label className="full">
            <span>描述</span>
            <textarea value={description} rows={4} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <div className="knowledge-ingest-footer">
            <span className="stack-subtle">创建后会进入该知识库详情页。</span>
            <button type="submit" className="primary-button">创建知识库</button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={Boolean(editingItem)}
        onClose={() => setEditingCode(null)}
        title={editingItem ? `编辑知识库：${editingItem.name}` : "编辑知识库"}
      >
        <form className="knowledge-ingest-form" onSubmit={handleEdit}>
          <label>
            <span>知识库编码</span>
            <input value={code} disabled />
          </label>
          <label>
            <span>知识库名称</span>
            <input value={name} required onChange={(event) => setName(event.target.value)} placeholder="例如 财务知识库" />
          </label>
          <label className="full">
            <span>描述</span>
            <textarea value={description} rows={4} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <div className="knowledge-ingest-footer">
            <span className="stack-subtle">保存后保留当前知识库详情上下文。</span>
            <button type="submit" className="primary-button">保存修改</button>
          </div>
        </form>
      </Modal>
    </section>
  );
}
