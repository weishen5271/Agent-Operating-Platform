"use client";

import { useState, useEffect } from "react";
import {
  createTenant,
  deleteTenant,
  getAdminSystem,
  listTenantUsers,
  updateTenant,
} from "@/lib/api-client";
import type { TenantProfile, UserProfile } from "@/lib/api-client/types";
import { UserManagement } from "./user-management";
import { LLMRuntimeForm } from "./llm-runtime-form";
import { Modal } from "@/components/shared/modal";

export function TenantManagement() {
  const [tenants, setTenants] = useState<TenantProfile[]>([]);
  const [selectedTenant, setSelectedTenant] = useState<TenantProfile | null>(null);
  const [tenantUsers, setTenantUsers] = useState<UserProfile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editForm, setEditForm] = useState<TenantProfile | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createForm, setCreateForm] = useState({
    tenant_id: "",
    name: "",
    package: "",
    environment: "生产",
    budget: "",
  });

  useEffect(() => {
    loadTenants();
  }, []);

  async function loadTenants() {
    setIsLoading(true);
    try {
      const res = await getAdminSystem();
      setTenants(res.tenants.map((t) => ({
        tenant_id: t.tenant_id,
        name: t.name,
        package: t.package,
        environment: t.environment,
        budget: t.budget,
        active: t.active,
      })));
    } catch {
      setFeedback("加载租户列表失败");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSelectTenant(tenant: TenantProfile) {
    setSelectedTenant(tenant);
    setIsLoadingUsers(true);
    setFeedback(null);
    try {
      const res = await listTenantUsers(tenant.tenant_id);
      setTenantUsers(res.users);
    } catch {
      setTenantUsers([]);
    } finally {
      setIsLoadingUsers(false);
    }
  }

  async function handleCreateTenant() {
    if (!createForm.tenant_id || !createForm.name || !createForm.package) {
      setFeedback("请填写必填字段");
      return;
    }
    try {
      const newTenant = await createTenant(createForm);
      setTenants((prev) => [...prev, newTenant]);
      setIsCreateModalOpen(false);
      setCreateForm({ tenant_id: "", name: "", package: "", environment: "生产", budget: "" });
      setFeedback(`租户 ${newTenant.name} 创建成功`);
    } catch {
      setFeedback("创建租户失败");
    }
  }

  async function handleUpdateTenant() {
    if (!editForm) return;
    try {
      const updated = await updateTenant(editForm.tenant_id, {
        name: editForm.name,
        package: editForm.package,
        environment: editForm.environment,
        budget: editForm.budget,
        active: editForm.active,
      });
      setTenants((prev) => prev.map((t) => (t.tenant_id === updated.tenant_id ? updated : t)));
      setSelectedTenant(updated);
      setIsEditModalOpen(false);
      setFeedback(`租户 ${updated.name} 更新成功`);
    } catch {
      setFeedback("更新租户失败");
    }
  }

  async function handleDeleteTenant(tenantId: string) {
    if (!confirm("确定要删除该租户吗？此操作不可恢复。")) return;
    try {
      await deleteTenant(tenantId);
      setTenants((prev) => prev.filter((t) => t.tenant_id !== tenantId));
      if (selectedTenant?.tenant_id === tenantId) {
        setSelectedTenant(null);
        setTenantUsers([]);
      }
      setFeedback("租户已删除");
    } catch {
      setFeedback("删除租户失败");
    }
  }

  function startEdit(tenant: TenantProfile) {
    setEditForm({ ...tenant });
    setIsEditModalOpen(true);
  }

  if (isLoading) {
    return (
      <section className="panel-card">
        <div className="panel-header">
          <h3>租户列表</h3>
        </div>
        <p>加载中...</p>
      </section>
    );
  }

  return (
    <div className="management-sections">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>租户列表</h3>
            <p>管理生产、试点、沙箱租户的用户规模与预算配额。</p>
          </div>
          <button type="button" className="primary-button" onClick={() => setIsCreateModalOpen(true)}>
            新建租户
          </button>
        </div>

        <div className="data-table">
          <div className="data-table-head five-cols">
            <span>租户</span>
            <span>业务包</span>
            <span>环境</span>
            <span>状态</span>
            <span>操作</span>
          </div>
          {tenants.map((tenant) => (
            <div
              key={tenant.tenant_id}
              className={`data-table-row five-cols ${selectedTenant?.tenant_id === tenant.tenant_id ? "selected" : ""}`}
              onClick={() => handleSelectTenant(tenant)}
              style={{ cursor: "pointer" }}
            >
              <div>
                <strong>{tenant.name}</strong>
                <p className="row-meta">{tenant.tenant_id}</p>
              </div>
              <span>{tenant.package}</span>
              <span className="env-badge">{tenant.environment}</span>
              <span className={`status-chip ${tenant.active ? "success" : ""}`}>
                {tenant.active ? "运行中" : "停用"}
              </span>
              <div className="row-actions" onClick={(e) => e.stopPropagation()}>
                <button type="button" className="ghost-button" onClick={() => startEdit(tenant)}>
                  编辑
                </button>
                <button
                  type="button"
                  className="ghost-button danger"
                  onClick={() => handleDeleteTenant(tenant.tenant_id)}
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Create Tenant Modal */}
      <Modal isOpen={isCreateModalOpen} onClose={() => setIsCreateModalOpen(false)} title="新建租户">
        <div className="form-section">
          <div className="form-grid">
            <div className="form-field">
              <label>租户 ID *</label>
              <input
                type="text"
                value={createForm.tenant_id}
                onChange={(e) => setCreateForm((f) => ({ ...f, tenant_id: e.target.value }))}
                placeholder="如: tenant-xxx"
              />
            </div>
            <div className="form-field">
              <label>租户名称 *</label>
              <input
                type="text"
                value={createForm.name}
                onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="如: 华东试点租户"
              />
            </div>
            <div className="form-field">
              <label>业务包 *</label>
              <input
                type="text"
                value={createForm.package}
                onChange={(e) => setCreateForm((f) => ({ ...f, package: e.target.value }))}
                placeholder="如: 财务业务包"
              />
            </div>
            <div className="form-field">
              <label>环境</label>
              <select
                value={createForm.environment}
                onChange={(e) => setCreateForm((f) => ({ ...f, environment: e.target.value }))}
              >
                <option value="生产">生产</option>
                <option value="试点">试点</option>
                <option value="沙箱">沙箱</option>
              </select>
            </div>
            <div className="form-field">
              <label>预算池</label>
              <input
                type="text"
                value={createForm.budget}
                onChange={(e) => setCreateForm((f) => ({ ...f, budget: e.target.value }))}
                placeholder="如: ¥ 100k"
              />
            </div>
          </div>
          <div className="form-actions">
            <button type="button" className="ghost-button" onClick={() => setIsCreateModalOpen(false)}>
              取消
            </button>
            <button type="button" className="primary-button" onClick={handleCreateTenant}>
              创建
            </button>
          </div>
        </div>
      </Modal>

      {/* Edit Tenant Modal */}
      <Modal isOpen={isEditModalOpen} onClose={() => setIsEditModalOpen(false)} title="编辑租户">
        {editForm && (
          <div className="form-section">
            <div className="form-grid">
              <div className="form-field">
                <label>租户 ID</label>
                <input type="text" value={editForm.tenant_id} disabled />
              </div>
              <div className="form-field">
                <label>租户名称 *</label>
                <input
                  type="text"
                  value={editForm.name}
                  onChange={(e) => setEditForm((f) => f && { ...f, name: e.target.value })}
                />
              </div>
              <div className="form-field">
                <label>业务包 *</label>
                <input
                  type="text"
                  value={editForm.package}
                  onChange={(e) => setEditForm((f) => f && { ...f, package: e.target.value })}
                />
              </div>
              <div className="form-field">
                <label>环境</label>
                <select
                  value={editForm.environment}
                  onChange={(e) => setEditForm((f) => f && { ...f, environment: e.target.value })}
                >
                  <option value="生产">生产</option>
                  <option value="试点">试点</option>
                  <option value="沙箱">沙箱</option>
                </select>
              </div>
              <div className="form-field">
                <label>预算池</label>
                <input
                  type="text"
                  value={editForm.budget}
                  onChange={(e) => setEditForm((f) => f && { ...f, budget: e.target.value })}
                />
              </div>
              <div className="form-field">
                <label>状态</label>
                <select
                  value={editForm.active ? "true" : "false"}
                  onChange={(e) => setEditForm((f) => f && { ...f, active: e.target.value === "true" })}
                >
                  <option value="true">运行中</option>
                  <option value="false">停用</option>
                </select>
              </div>
            </div>
            <div className="form-actions">
              <button type="button" className="ghost-button" onClick={() => setIsEditModalOpen(false)}>
                取消
              </button>
              <button type="button" className="primary-button" onClick={handleUpdateTenant}>
                保存
              </button>
            </div>
          </div>
        )}
      </Modal>

      {selectedTenant && (
        <>
          <UserManagement
            tenantId={selectedTenant.tenant_id}
            tenantName={selectedTenant.name}
            initialUsers={tenantUsers}
            isLoading={isLoadingUsers}
          />

          <section className="panel-card">
            <div className="panel-header">
              <div>
                <h3>LLM 配置 - {selectedTenant.name}</h3>
                <p>为此租户配置专属的 LLM 运行时设置。</p>
              </div>
            </div>
            <LLMRuntimeForm tenantId={selectedTenant.tenant_id} />
          </section>
        </>
      )}

      {feedback && <p className="inline-feedback">{feedback}</p>}
    </div>
  );
}
