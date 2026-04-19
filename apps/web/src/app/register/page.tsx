"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { register } from "@/lib/api-client";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }

    if (password.length < 6) {
      setError("密码长度至少为 6 位");
      return;
    }

    setIsPending(true);

    try {
      const response = await register({
        email,
        password,
        tenant_id: tenantId,
        role: "platform_admin",
      });
      localStorage.setItem("auth_token", response.access_token);
      localStorage.setItem("auth_user", JSON.stringify(response.user));
      router.push("/");
    } catch {
      setError("注册失败，该邮箱可能已被注册或租户不存在");
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-shell">
        <aside className="auth-hero">
          <div className="auth-hero-top">
            <div className="brand-mark">
              <span className="material-symbols-outlined">workspace_premium</span>
            </div>
            <h2>Agent Platform</h2>
          </div>

          <div className="auth-hero-content">
            <h1>
              打造你的
              <br />
              <em>智能运营中台</em>
            </h1>
            <p>
              通过统一的业务包体系和治理框架，让每一次智能体交互都可追溯、可审批、可回滚。
            </p>
          </div>

          <div className="auth-hero-stats">
            <div>
              <strong>24 × 7</strong>
              <span>全天候运行</span>
            </div>
            <div>
              <strong>GDPR</strong>
              <span>合规就绪</span>
            </div>
          </div>
        </aside>

        <section className="auth-form-panel">
          <h3>申请成为平台管理员</h3>
          <p className="auth-form-sub">首位管理员将负责激活对应租户的业务包与权限。</p>

          <form onSubmit={handleSubmit}>
            {error && <div className="auth-error">{error}</div>}

            <div className="form-field">
              <label htmlFor="email">邮箱</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                required
              />
            </div>

            <div className="form-field">
              <label htmlFor="tenantId">租户 ID</label>
              <input
                id="tenantId"
                type="text"
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                placeholder="如: tenant-default"
                required
              />
              <span className="field-hint">联系管理员获取租户 ID</span>
            </div>

            <div className="form-field">
              <label htmlFor="password">密码</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 6 位"
                required
                minLength={6}
              />
            </div>

            <div className="form-field">
              <label htmlFor="confirmPassword">确认密码</label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="请再次输入密码"
                required
              />
            </div>

            <button type="submit" className="primary-button full-width" disabled={isPending}>
              {isPending ? "注册中..." : "创建管理员账号"}
            </button>

            <div className="auth-footer">
              已有账号？<Link href="/login">立即登录</Link>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
