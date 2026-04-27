"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { getPackageDetail, importPackageKnowledge, uninstallPackageBundle } from "@/lib/api-client";
import { PackageDependencyGraph } from "@/components/packages/package-dependency-graph";
import { Shell } from "@/components/shared/shell";
import type { KnowledgeImportDeclaration, PackageDetailResponse } from "@/lib/api-client/types";

function statusTone(status: string): string {
  if (status.includes("运行")) return "success";
  if (status.includes("灰度")) return "warning";
  if (status.includes("待")) return "info";
  return "";
}

function formatAttributes(attributes: Record<string, unknown>): string {
  const entries = Object.entries(attributes);
  if (!entries.length) return "无扩展属性";
  return entries
    .map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(" · ");
}

export default function PackageDetailPage() {
  const params = useParams<{ packageId: string }>();
  const router = useRouter();
  const packageId = decodeURIComponent(params.packageId);
  const [packageDetail, setPackageDetail] = useState<PackageDetailResponse | null>(null);
  const [loadError, setLoadError] = useState("");
  const [knowledgeImportMessage, setKnowledgeImportMessage] = useState("");
  const [importingKnowledge, setImportingKnowledge] = useState(false);
  const [uninstallMessage, setUninstallMessage] = useState("");
  const [uninstalling, setUninstalling] = useState(false);
  const [reloadCounter, setReloadCounter] = useState(0);

  useEffect(() => {
    let alive = true;

    async function loadPackageDetail() {
      setLoadError("");
      try {
        const response = await getPackageDetail(packageId);
        if (!alive) return;
        setPackageDetail(response);
      } catch (exc) {
        if (!alive) return;
        setPackageDetail(null);
        setLoadError(exc instanceof Error ? exc.message : "业务包详情加载失败");
      }
    }

    void loadPackageDetail();
    return () => {
      alive = false;
    };
  }, [packageId, reloadCounter]);

  async function handleImportKnowledge(autoOnly: boolean) {
    if (!packageDetail) return;
    const declarations = packageDetail.knowledge_imports ?? [];
    const targets = autoOnly ? declarations.filter((item) => item.auto_import) : declarations;
    if (!targets.length) {
      setKnowledgeImportMessage(autoOnly ? "没有 auto_import=true 的知识声明。" : "当前业务包没有 knowledge_imports 声明。");
      return;
    }
    const confirmed = window.confirm(
      `即将从业务包 ${packageDetail.package_id} 导入 ${targets.length} 份知识文件。\n\n导入后会写入知识库，确认继续？`,
    );
    if (!confirmed) return;

    setImportingKnowledge(true);
    setKnowledgeImportMessage("");
    try {
      const result = await importPackageKnowledge(packageDetail.package_id, { autoOnly });
      setKnowledgeImportMessage(
        `已导入 ${result.imported_count} 份知识文件${result.skipped_count ? `，跳过 ${result.skipped_count} 份` : ""}。`,
      );
      setReloadCounter((value) => value + 1);
    } catch (exc) {
      setKnowledgeImportMessage(exc instanceof Error ? exc.message : "知识导入失败");
    } finally {
      setImportingKnowledge(false);
    }
  }

  async function handleUninstallBundle() {
    if (!packageDetail) return;
    const confirmed = window.confirm(
      `即将卸载业务包 ${packageDetail.name} (${packageDetail.package_id})。\n\n该操作会删除本地安装的 bundle 文件，并刷新能力/Skill 注册表；不会删除已导入知识库的数据。确认继续？`,
    );
    if (!confirmed) return;

    setUninstalling(true);
    setUninstallMessage("");
    try {
      await uninstallPackageBundle(packageDetail.package_id);
      router.push("/packages");
      router.refresh();
    } catch (exc) {
      setUninstallMessage(exc instanceof Error ? exc.message : "卸载失败");
      setUninstalling(false);
    }
  }

  if (!packageDetail) {
    return (
      <Shell activeKey="packages" title="业务包详情" searchPlaceholder="搜索依赖、Skill 或插件...">
        <section className="page-section">
          <div className="page-head">
            <div className="page-head-meta">
              <div className="breadcrumbs">
                <span>能力中心</span>
                <span className="material-symbols-outlined">chevron_right</span>
                <Link href="/packages" className="current">
                  业务包管理
                </Link>
              </div>
              <h1>业务包详情</h1>
              <p>{packageId}</p>
            </div>
            <div className="page-head-actions">
              <Link href="/packages" className="secondary-button">
                <span className="material-symbols-outlined">arrow_back</span>
                返回列表
              </Link>
            </div>
          </div>
          <div className="trace-empty-state">
            <span className="material-symbols-outlined">inventory_2</span>
            <p>{loadError || "正在加载业务包详情..."}</p>
          </div>
        </section>
      </Shell>
    );
  }

  const knowledgeImports: KnowledgeImportDeclaration[] = packageDetail.knowledge_imports ?? [];
  const autoImportCount = knowledgeImports.filter((item) => item.auto_import).length;
  const isInstalledBundle = packageDetail.source_kind === "bundle" || Boolean(packageDetail.bundle_path);

  return (
    <Shell activeKey="packages" title="业务包详情" searchPlaceholder="搜索依赖、Skill 或插件...">
      <section className="page-section">
        <div className="page-head">
          <div className="page-head-meta">
            <div className="breadcrumbs">
              <span>能力中心</span>
              <span className="material-symbols-outlined">chevron_right</span>
              <Link href="/packages" className="current">
                业务包管理
              </Link>
              <span className="material-symbols-outlined">chevron_right</span>
              <span className="current">{packageDetail.name}</span>
            </div>
            <h1>{packageDetail.name}</h1>
            <p>
              {packageDetail.package_id} · {packageDetail.version} · 负责人 {packageDetail.owner}
            </p>
          </div>
          <div className="page-head-actions">
            <Link href="/packages" className="secondary-button">
              <span className="material-symbols-outlined">arrow_back</span>
              返回列表
            </Link>
            {isInstalledBundle ? (
              <button
                type="button"
                className="ghost-button"
                disabled={uninstalling}
                onClick={() => void handleUninstallBundle()}
              >
                <span className="material-symbols-outlined">delete</span>
                {uninstalling ? "卸载中..." : "卸载 bundle"}
              </button>
            ) : null}
            <span className={`status-chip ${statusTone(packageDetail.status)}`}>{packageDetail.status}</span>
          </div>
        </div>
        {uninstallMessage ? <p className="inline-error">{uninstallMessage}</p> : null}

        <div className="bento-grid four">
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">平台 Skill</span>
              <span className="stat-icon material-symbols-outlined">auto_awesome</span>
            </div>
            <strong>{packageDetail.dependency_summary.platform_skills}</strong>
            <p>由平台统一注册与灰度。</p>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">通用包</span>
              <span className="stat-icon material-symbols-outlined">deployed_code</span>
            </div>
            <strong>{packageDetail.dependency_summary.common_packages}</strong>
            <p>可被多个行业包复用。</p>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">插件</span>
              <span className="stat-icon material-symbols-outlined">extension</span>
            </div>
            <strong>{packageDetail.dependency_summary.plugins}</strong>
            <p>外部系统能力接入点。</p>
          </article>
          <article className="stat-card">
            <div className="stat-card-head">
              <span className="stat-card-label">平台 Tool</span>
              <span className="stat-icon material-symbols-outlined">build</span>
            </div>
            <strong>{packageDetail.dependency_summary.tools}</strong>
            <p>无业务规则的原子工具。</p>
          </article>
        </div>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>依赖详情</h3>
              <p>按依赖类型、版本范围和当前版本检查兼容状态。</p>
            </div>
          </div>
          <PackageDependencyGraph dependencies={packageDetail.dependencies} />
        </section>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>Bundle 知识导入</h3>
              <p>展示 manifest.knowledge_imports 声明；导入动作必须由管理员显式确认。</p>
            </div>
            <div className="panel-actions">
              <button
                type="button"
                className="ghost-button"
                disabled={importingKnowledge || !knowledgeImports.length || autoImportCount === 0 || !isInstalledBundle}
                onClick={() => void handleImportKnowledge(true)}
              >
                <span className="material-symbols-outlined">playlist_add_check</span>
                仅导入自动项
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={importingKnowledge || !knowledgeImports.length || !isInstalledBundle}
                onClick={() => void handleImportKnowledge(false)}
              >
                <span className="material-symbols-outlined">library_add</span>
                {importingKnowledge ? "导入中..." : "导入声明知识"}
              </button>
            </div>
          </div>
          {knowledgeImportMessage ? <p className="inline-error">{knowledgeImportMessage}</p> : null}
          {!isInstalledBundle ? (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">inventory_2</span>
              <p>当前不是已安装 bundle，不能从 bundle 文件导入知识。</p>
            </div>
          ) : knowledgeImports.length === 0 ? (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">menu_book</span>
              <p>当前业务包没有声明 knowledge_imports。</p>
            </div>
          ) : (
            <div className="stack-list">
              {knowledgeImports.map((item) => (
                <article key={`${item.file}-${item.knowledge_base_code}`} className="stack-item">
                  <div>
                    <strong>{item.name}</strong>
                    <p className="row-meta">
                      {item.file} · {item.source_type} · 写入 {item.knowledge_base_code}
                    </p>
                    <p className="row-meta">{formatAttributes(item.attributes)}</p>
                  </div>
                  <span className={`status-chip ${item.auto_import ? "success" : "plain"}`}>
                    {item.auto_import ? "auto_import" : "manual"}
                  </span>
                </article>
              ))}
            </div>
          )}
        </section>
      </section>
    </Shell>
  );
}
