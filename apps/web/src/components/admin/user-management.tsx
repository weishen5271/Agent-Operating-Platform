"use client";

import { useState, useEffect } from "react";
import { createUser, deleteUser, updateUser } from "@/lib/api-client";
import type { UserProfile } from "@/lib/api-client/types";
import { Modal } from "@/components/shared/modal";

type UserManagementProps = {
  tenantId: string;
  tenantName: string;
  initialUsers: UserProfile[];
  isLoading: boolean;
};

const AVAILABLE_SCOPES = [
  "chat:read",
  "knowledge:read",
  "hr:read",
  "workflow:draft",
  "draft:confirm",
  "admin:read",
];

export function UserManagement({ tenantId, tenantName, initialUsers, isLoading }: UserManagementProps) {
  const [users, setUsers] = useState(initialUsers);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [editUser, setEditUser] = useState<UserProfile | null>(null);
  const [createForm, setCreateForm] = useState({
    email: "",
    password: "Aa111111",
    role: "platform_admin",
    scopes: ["chat:read", "knowledge:read"],
  });

  // Sync with initialUsers when it changes (e.g., when selecting a different tenant)
  useEffect(() => {
    setUsers(initialUsers);
  }, [initialUsers]);

  async function handleCreateUser() {
    if (!createForm.email) {
      setFeedback("请填写用户邮箱");
      return;
    }
    try {
      const newUser = await createUser(tenantId, createForm);
      setUsers((prev) => [...prev, newUser]);
      setIsCreateModalOpen(false);
      setCreateForm({
        email: "",
        password: "Aa111111",
        role: "platform_admin",
        scopes: ["chat:read", "knowledge:read"],
      });
      setFeedback(`用户 ${newUser.email || newUser.user_id} 创建成功`);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "创建用户失败");
    }
  }

  async function handleUpdateUser() {
    if (!editUser) return;
    try {
      const updated = await updateUser(tenantId, editUser.user_id, {
        role: editUser.role,
        scopes: editUser.scopes,
      });
      setUsers((prev) => prev.map((u) => (u.user_id === updated.user_id ? updated : u)));
      setEditUser(null);
      setFeedback(`用户 ${updated.user_id} 更新成功`);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "更新用户失败");
    }
  }

  async function handleDeleteUser(userId: string) {
    if (!confirm("确定要删除该用户吗？")) return;
    try {
      await deleteUser(tenantId, userId);
      setUsers((prev) => prev.filter((u) => u.user_id !== userId));
      setFeedback("用户已删除");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "删除用户失败");
    }
  }

  function toggleScope(form: "create" | "edit", scope: string) {
    const setter = form === "create" ? setCreateForm : setEditUser;
    const getter = form === "create" ? createForm : editUser;

    if (form === "create") {
      setCreateForm((f) => ({
        ...f,
        scopes: f.scopes.includes(scope) ? f.scopes.filter((s) => s !== scope) : [...f.scopes, scope],
      }));
    } else if (editUser) {
      setEditUser({
        ...editUser,
        scopes: editUser.scopes.includes(scope)
          ? editUser.scopes.filter((s) => s !== scope)
          : [...editUser.scopes, scope],
      });
    }
  }

  if (isLoading) {
    return (
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h3>用户列表 - {tenantName}</h3>
            <p>加载中...</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="panel-card">
      <div className="panel-header">
        <div>
          <h3>用户列表 - {tenantName}</h3>
          <p>管理租户下的用户账号与权限范围。</p>
        </div>
        <button type="button" className="primary-button" onClick={() => setIsCreateModalOpen(true)}>
          添加用户
        </button>
      </div>

      <Modal isOpen={isCreateModalOpen} onClose={() => setIsCreateModalOpen(false)} title={`添加用户 - ${tenantName}`}>
        <div className="form-section">
          <div className="form-grid">
            <div className="form-field">
              <label>用户邮箱 *</label>
              <input
                type="email"
                value={createForm.email}
                onChange={(e) => setCreateForm((f) => ({ ...f, email: e.target.value }))}
                placeholder="如: admin@sw.com"
              />
              <p className="row-meta">系统会自动生成用户 ID</p>
            </div>
            <div className="form-field">
              <label>初始密码</label>
              <input
                type="text"
                value={createForm.password}
                onChange={(e) => setCreateForm((f) => ({ ...f, password: e.target.value }))}
                placeholder="默认 Aa111111"
              />
            </div>
            <div className="form-field">
              <label>角色</label>
              <select
                value={createForm.role}
                onChange={(e) => setCreateForm((f) => ({ ...f, role: e.target.value }))}
              >
                <option value="platform_admin">平台管理员</option>
                <option value="auditor">审计员</option>
                <option value="business_admin">业务管理员</option>
                <option value="developer">开发者</option>
              </select>
            </div>
          </div>
          <div className="form-field">
            <label>权限 Scope</label>
            <div className="scope-chips">
              {AVAILABLE_SCOPES.map((scope) => (
                <label key={scope} className="scope-chip">
                  <input
                    type="checkbox"
                    checked={createForm.scopes.includes(scope)}
                    onChange={() => toggleScope("create", scope)}
                  />
                  <span>{scope}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="form-actions">
            <button type="button" className="ghost-button" onClick={() => setIsCreateModalOpen(false)}>
              取消
            </button>
            <button type="button" className="primary-button" onClick={handleCreateUser}>
              添加
            </button>
          </div>
        </div>
      </Modal>

      {editUser && (
        <div className="form-section">
          <h4>编辑用户 - {editUser.user_id}</h4>
          <div className="form-grid">
            <div className="form-field">
              <label>角色</label>
              <select
                value={editUser.role}
                onChange={(e) => setEditUser({ ...editUser, role: e.target.value })}
              >
                <option value="platform_admin">平台管理员</option>
                <option value="auditor">审计员</option>
                <option value="business_admin">业务管理员</option>
                <option value="developer">开发者</option>
              </select>
            </div>
          </div>
          <div className="form-field">
            <label>权限 Scope</label>
            <div className="scope-chips">
              {AVAILABLE_SCOPES.map((scope) => (
                <label key={scope} className="scope-chip">
                  <input
                    type="checkbox"
                    checked={editUser.scopes.includes(scope)}
                    onChange={() => toggleScope("edit", scope)}
                  />
                  <span>{scope}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="form-actions">
            <button type="button" className="ghost-button" onClick={() => setEditUser(null)}>
              取消
            </button>
            <button type="button" className="primary-button" onClick={handleUpdateUser}>
              保存
            </button>
          </div>
        </div>
      )}

      <div className="data-table">
        <div className="data-table-head five-cols">
          <span>邮箱</span>
          <span>用户 ID</span>
          <span>角色</span>
          <span>权限 Scope</span>
          <span>操作</span>
        </div>
        {users.length === 0 ? (
          <div className="empty-state">暂无用户</div>
        ) : (
          users.map((user) => (
            <div key={user.user_id} className="data-table-row five-cols">
              <div>
                <strong>{user.email || user.user_id}</strong>
              </div>
              <span className="row-meta">{user.user_id}</span>
              <span className="role-badge">{user.role}</span>
              <div className="scope-tags">
                {user.scopes.slice(0, 3).map((scope) => (
                  <span key={scope} className="scope-tag">
                    {scope}
                  </span>
                ))}
                {user.scopes.length > 3 && <span className="scope-tag">+{user.scopes.length - 3}</span>}
              </div>
              <div className="row-actions">
                <button type="button" className="ghost-button" onClick={() => setEditUser({ ...user })}>
                  编辑
                </button>
                <button
                  type="button"
                  className="ghost-button danger"
                  onClick={() => handleDeleteUser(user.user_id)}
                >
                  删除
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
