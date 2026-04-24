"use client";

import Link from "next/link";
import { useLinkStatus } from "next/dist/client/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getCurrentUser } from "@/lib/api-client";

type NavKey =
  | "overview"
  | "chat"
  | "packages"
  | "security"
  | "audit"
  | "knowledge"
  | "system";

type NavHref =
  | "/"
  | "/chat"
  | "/packages"
  | "/security"
  | "/audit"
  | "/knowledge"
  | "/system";

type ConsoleNavItem = {
  key: NavKey;
  href: NavHref;
  label: string;
  icon: string;
};

type ConsoleNavGroup = {
  label: string;
  items: ConsoleNavItem[];
};

type ConsoleTab = {
  label: string;
  href?: string;
  active?: boolean;
  onClick?: () => void;
};

type AuthUser = {
  user_id: string;
  tenant_id?: string;
  role?: string;
  email?: string;
  tenant_name?: string;
};

const navGroups: ConsoleNavGroup[] = [
  {
    label: "运营驾驶舱",
    items: [
      { key: "overview", href: "/", label: "运营总览", icon: "dashboard" },
      { key: "chat", href: "/chat", label: "对话演示", icon: "forum" },
    ],
  },
  {
    label: "能力中心",
    items: [
      { key: "packages", href: "/packages", label: "业务包管理", icon: "inventory_2" },
      { key: "knowledge", href: "/knowledge", label: "知识库治理", icon: "library_books" },
    ],
  },
  {
    label: "治理与合规",
    items: [
      { key: "security", href: "/security", label: "安全治理", icon: "policy" },
      { key: "audit", href: "/audit", label: "审计合规", icon: "history_edu" },
      { key: "system", href: "/system", label: "租户与权限", icon: "domain" },
    ],
  },
];

function Icon({ name }: { name: string }) {
  return <span className="material-symbols-outlined">{name}</span>;
}

function NavPendingIndicator() {
  const { pending } = useLinkStatus();
  if (!pending) return null;
  return <span className="nav-spinner" aria-hidden="true" />;
}

export function Shell({
  activeKey,
  title,
  searchPlaceholder,
  tabs = [],
  children,
}: {
  activeKey: string;
  title: string;
  searchPlaceholder: string;
  tabs?: ConsoleTab[];
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const [progressKey, setProgressKey] = useState(0);
  const [navigating, setNavigating] = useState(false);
  useEffect(() => {
    setProgressKey((k) => k + 1);
    setNavigating(false);
  }, [pathname]);

  useEffect(() => {
    const userStr = localStorage.getItem("auth_user");
    if (userStr) {
      try {
        setUser(JSON.parse(userStr));
      } catch {
        // ignore
      }
    }

    getCurrentUser()
      .then((freshUser) => {
        localStorage.setItem("auth_user", JSON.stringify(freshUser));
        setUser(freshUser);
      })
      .catch(() => {
        // Existing auth guard handles invalid or missing tokens.
      });
  }, []);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (!userMenuRef.current?.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  function handleLogout() {
    setIsUserMenuOpen(false);
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    router.push("/login");
  }

  function getUserInitials() {
    if (!user) return "SW";
    return user.user_id.slice(0, 2).toUpperCase();
  }

  const displayRole = user?.role ? user.role.replace(/_/g, " ").toUpperCase() : "ADMIN";
  const displayName = user?.email || user?.user_id || "运营管理员";
  const tenantName = user?.tenant_name || user?.tenant_id || "未绑定租户";

  return (
    <div className="console-shell">
      <aside className="console-sidebar" aria-label="侧边导航">
        <div className="console-brand">
          <div className="brand-mark">
            <Icon name="workspace_premium" />
          </div>
          <div>
            <h1>Agent Platform</h1>
            <p>Enterprise OS</p>
          </div>
        </div>

        {navGroups.map((group) => (
          <nav key={group.label} className="console-nav" aria-label={group.label}>
            <div className="nav-group-label">{group.label}</div>
            {group.items.map((item) => {
              const isActive = item.key === activeKey;
              return (
                <Link
                  key={item.key}
                  href={item.href}
                  prefetch
                  className={`console-nav-item ${isActive ? "active" : ""}`}
                  onClick={() => {
                    if (!isActive) setNavigating(true);
                  }}
                >
                  <Icon name={item.icon} />
                  <span>{item.label}</span>
                  <NavPendingIndicator />
                </Link>
              );
            })}
          </nav>
        ))}

        <div className="console-sidebar-footer">
          <button type="button" className="primary-cta">
            <Icon name="add_circle" />
            <span>部署新智能体</span>
          </button>
        </div>
      </aside>

      <div className="console-main">
        <span
          key={progressKey}
          className={`top-nav-progress ${navigating ? "is-navigating" : ""}`}
          aria-hidden="true"
        />
        {navigating ? <div className="nav-loading-overlay" aria-hidden="true" /> : null}
        <header className="console-header">
          <div className="console-header-left">
            <h2>{title}</h2>
            {tabs.length ? (
              <>
                <div className="header-divider" />
                <nav className="console-tabs" aria-label="页签">
                  {tabs.map((tab) =>
                    tab.href ? (
                      <Link
                        key={tab.label}
                        href={tab.href as never}
                        className={`console-tab ${tab.active ? "active" : ""}`}
                      >
                        {tab.label}
                      </Link>
                    ) : tab.onClick ? (
                      <button
                        key={tab.label}
                        type="button"
                        className={`console-tab ${tab.active ? "active" : ""}`}
                        onClick={tab.onClick}
                      >
                        {tab.label}
                      </button>
                    ) : (
                      <span
                        key={tab.label}
                        className={`console-tab ${tab.active ? "active" : ""}`}
                      >
                        {tab.label}
                      </span>
                    ),
                  )}
                </nav>
              </>
            ) : null}
          </div>

          <div className="console-header-right">
            <div className="search-shell">
              <Icon name="search" />
              <input type="text" placeholder={searchPlaceholder} />
            </div>
            <button type="button" className="icon-button" aria-label="通知">
              <Icon name="notifications" />
            </button>
            <button type="button" className="icon-button" aria-label="服务拓扑">
              <Icon name="account_tree" />
            </button>
            <button type="button" className="icon-button" aria-label="应用切换">
              <Icon name="apps" />
            </button>
            <div className="header-user-menu" ref={userMenuRef}>
              <button
                type="button"
                className="user-avatar"
                aria-label="用户菜单"
                aria-expanded={isUserMenuOpen}
                aria-haspopup="menu"
                onClick={() => setIsUserMenuOpen((open) => !open)}
              >
                {getUserInitials()}
              </button>
              {isUserMenuOpen ? (
                <div className="user-menu-panel" role="menu" aria-label={displayName}>
                  <div className="user-menu-profile">
                    <strong>{displayName}</strong>
                    <span>{tenantName}</span>
                    <span>{displayRole}</span>
                  </div>
                  <button type="button" className="user-menu-item danger" role="menuitem" onClick={handleLogout}>
                    <Icon name="logout" />
                    <span>退出登录</span>
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <main className="console-content">{children}</main>
      </div>
    </div>
  );
}
