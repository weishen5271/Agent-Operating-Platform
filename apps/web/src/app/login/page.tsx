"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api-client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsPending(true);

    try {
      const response = await login({ email, password });
      localStorage.setItem("auth_token", response.access_token);
      localStorage.setItem("auth_user", JSON.stringify(response.user));
      router.push("/");
    } catch {
      setError("邮箱或密码错误");
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
              精准对齐业务的
              <br />
              <em>Precision Architect</em>
            </h1>
            <p>
              一体化的运营控制台，统一管理业务包、知识库、对话链路与治理审批，帮助企业以更稳健的节奏推进智能体落地。
            </p>
          </div>

          <div className="auth-hero-stats">
            <div>
              <strong>99.98%</strong>
              <span>请求成功率</span>
            </div>
            <div>
              <strong>256-bit</strong>
              <span>企业级加密</span>
            </div>
          </div>
        </aside>

        <section className="auth-form-panel">
          <h3>欢迎回到 Agent 平台</h3>
          <p className="auth-form-sub">使用企业邮箱登录，开启今天的运营工作。</p>

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
              <label htmlFor="password">密码</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                required
                minLength={6}
              />
            </div>

            <button type="submit" className="primary-button full-width" disabled={isPending}>
              {isPending ? "登录中..." : "进入平台"}
            </button>

            <div className="auth-divider">或通过第三方登录</div>
            <div className="auth-sso-grid">
              <button type="button" disabled>
                <span className="material-symbols-outlined">corporate_fare</span>
                企业微信
              </button>
              <button type="button" disabled>
                <span className="material-symbols-outlined">vpn_key</span>
                LDAP · SSO
              </button>
            </div>

            <div className="auth-footer">
              还没有账号？<Link href="/register">立即注册</Link>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
