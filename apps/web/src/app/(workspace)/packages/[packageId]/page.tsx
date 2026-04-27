"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { getPackageDetail, importPackageKnowledge, previewPackageKnowledge, uninstallPackageBundle } from "@/lib/api-client";
import { PackageDependencyGraph } from "@/components/packages/package-dependency-graph";
import { PluginConfigForm } from "@/components/packages/plugin-config-form";
import { Shell } from "@/components/shared/shell";
import type { KnowledgeImportDeclaration, PackageDetailResponse, PackageKnowledgePreviewResponse } from "@/lib/api-client/types";

function formatAttributes(attributes: Record<string, unknown>): string {
  const entries = Object.entries(attributes);
  if (!entries.length) return "无扩展属性";
  return entries
    .map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(" · ");
}

function executorLabel(value: string | undefined): string {
  if (!value) return "未声明执行器";
  const normalized = value.toLowerCase();
  if (normalized === "http") return "HTTP 执行器";
  if (normalized === "mcp") return "MCP 执行器";
  if (normalized === "stub") return "占位执行器";
  if (normalized === "platform") return "平台代理执行器";
  return value;
}

function importModeLabel(autoImport: boolean): string {
  return autoImport ? "自动导入" : "手动导入";
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
  const [selectedPluginName, setSelectedPluginName] = useState("");
  const [selectedKnowledgeFile, setSelectedKnowledgeFile] = useState("");
  const [knowledgePreview, setKnowledgePreview] = useState<PackageKnowledgePreviewResponse | null>(null);
  const [knowledgePreviewStatus, setKnowledgePreviewStatus] = useState<"idle" | "loading" | "error">("idle");
  const [knowledgePreviewError, setKnowledgePreviewError] = useState("");

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

  async function handleOpenKnowledgePreview(item: KnowledgeImportDeclaration) {
    if (!packageDetail) return;
    setSelectedKnowledgeFile(item.file);
    setKnowledgePreview(null);
    setKnowledgePreviewStatus("loading");
    setKnowledgePreviewError("");
    try {
      const response = await previewPackageKnowledge(packageDetail.package_id, item.file);
      setKnowledgePreview(response);
      setKnowledgePreviewStatus("idle");
    } catch (exc) {
      setKnowledgePreviewStatus("error");
      setKnowledgePreviewError(exc instanceof Error ? exc.message : "知识文件详情加载失败");
    }
  }

  function handleCloseKnowledgePreview() {
    setSelectedKnowledgeFile("");
    setKnowledgePreview(null);
    setKnowledgePreviewStatus("idle");
    setKnowledgePreviewError("");
  }

  function handleClosePluginDrawer() {
    setSelectedPluginName("");
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
  const plugins = packageDetail.plugins ?? [];
  const selectedPlugin = selectedPluginName ? plugins.find((item) => item.name === selectedPluginName) : undefined;

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
            <p>由平台统一注册与编排。</p>
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
              <h3>能力组成</h3>
              <p>按平台 Skill、通用包、插件和平台 Tool 分类查看业务包依赖。</p>
            </div>
          </div>
          <PackageDependencyGraph dependencies={packageDetail.dependencies} plugins={plugins} />
        </section>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>外部系统对接</h3>
              <p>按业务包声明的 plugin 配置 HTTP endpoint、密钥或 MCP Server。</p>
            </div>
          </div>
          {!plugins.length ? (
            <div className="trace-empty-state">
              <span className="material-symbols-outlined">extension_off</span>
              <p>当前业务包没有声明 plugin。</p>
            </div>
          ) : (
            <div className="stack-list">
              {plugins.map((plugin) => (
                <button
                  key={plugin.name}
                  type="button"
                  className="stack-item table-row-button"
                  onClick={() => setSelectedPluginName(plugin.name)}
                >
                  <div>
                    <strong>{plugin.name}</strong>
                    <p>
                        {executorLabel(plugin.executor)} · {plugin.version ?? "未声明版本"}
                      </p>
                    {plugin.description ? <p className="row-meta">{plugin.description}</p> : null}
                  </div>
                  <span className="status-chip plain">{plugin.capabilities?.length ?? 0} 个能力</span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="panel-card">
          <div className="panel-header">
            <div>
              <h3>业务包知识导入</h3>
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
                <button
                  key={`${item.file}-${item.knowledge_base_code}`}
                  type="button"
                  className="stack-item table-row-button"
                  onClick={() => void handleOpenKnowledgePreview(item)}
                >
                  <div>
                    <strong>{item.name}</strong>
                    <p className="row-meta">
                      {item.file} · {item.source_type} · 写入 {item.knowledge_base_code}
                    </p>
                    <p className="row-meta">{formatAttributes(item.attributes)}</p>
                  </div>
                  <span className={`status-chip ${item.auto_import ? "success" : "plain"}`}>
                    {importModeLabel(item.auto_import)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
      </section>
      {selectedPlugin ? (
        <div className="knowledge-detail-drawer-backdrop" onClick={handleClosePluginDrawer}>
          <aside className="knowledge-detail-drawer" onClick={(event) => event.stopPropagation()}>
            <div className="knowledge-detail-drawer-header">
              <div>
                <div className="knowledge-detail-drawer-title-row">
                  <h3>外部系统对接</h3>
                  <span className="status-chip plain">{executorLabel(selectedPlugin.executor)}</span>
                </div>
                <p>{selectedPlugin.name}</p>
              </div>
              <button type="button" className="drawer-close-button" onClick={handleClosePluginDrawer}>
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="knowledge-detail-drawer-body">
              <section className="drawer-section">
                <h4>插件信息</h4>
                <div className="drawer-summary-grid">
                  <div>
                    <span>版本</span>
                    <strong>{selectedPlugin.version ?? "未声明版本"}</strong>
                  </div>
                  <div>
                    <span>执行器</span>
                    <strong>{executorLabel(selectedPlugin.executor)}</strong>
                  </div>
                  <div>
                    <span>能力数量</span>
                    <strong>{selectedPlugin.capabilities?.length ?? 0}</strong>
                  </div>
                  <div>
                    <span>配置结构</span>
                    <strong>{selectedPlugin.config_schema ? "已声明" : "未声明"}</strong>
                  </div>
                </div>
                {selectedPlugin.description ? <p className="row-meta">{selectedPlugin.description}</p> : null}
              </section>
              <section className="drawer-section">
                <h4>能力列表</h4>
                {selectedPlugin.capabilities?.length ? (
                  <div className="stack-list">
                    {selectedPlugin.capabilities.map((capability) => (
                      <article key={capability.name} className="stack-item">
                        <div>
                          <strong>{capability.name}</strong>
                          {capability.description ? <p>{capability.description}</p> : null}
                          <p className="row-meta">
                            {capability.required_scope ?? "权限范围未声明"} · {capability.side_effect_level ?? "副作用等级未声明"}
                          </p>
                        </div>
                        <span className="status-chip plain">{capability.risk_level ?? "风险等级未声明"}</span>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-distribution">当前插件没有声明能力。</div>
                )}
              </section>
              <section className="drawer-section">
                <h4>连接配置</h4>
                <PluginConfigForm key={selectedPlugin.name} pluginName={selectedPlugin.name} />
              </section>
            </div>
          </aside>
        </div>
      ) : null}
      {selectedKnowledgeFile ? (
        <div className="knowledge-detail-drawer-backdrop" onClick={handleCloseKnowledgePreview}>
          <aside className="knowledge-detail-drawer" onClick={(event) => event.stopPropagation()}>
            <div className="knowledge-detail-drawer-header">
              <div>
                <div className="knowledge-detail-drawer-title-row">
                  <h3>业务包知识文件</h3>
                  <span className="status-chip plain">{knowledgePreview?.source_type ?? "加载中"}</span>
                </div>
                <p>{knowledgePreview?.file ?? selectedKnowledgeFile}</p>
              </div>
              <button type="button" className="drawer-close-button" onClick={handleCloseKnowledgePreview}>
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="knowledge-detail-drawer-body">
              {knowledgePreviewStatus === "loading" ? (
                <div className="empty-distribution">正在读取 bundle 内知识文件。</div>
              ) : knowledgePreviewStatus === "error" ? (
                <div className="empty-distribution">{knowledgePreviewError || "知识文件详情加载失败。"}</div>
              ) : knowledgePreview ? (
                <>
                  <section className="drawer-section">
                    <h4>基本信息摘要</h4>
                    <div className="drawer-summary-grid">
                      <div>
                        <span>文件名称</span>
                        <strong>{knowledgePreview.name}</strong>
                      </div>
                      <div>
                        <span>写入知识库</span>
                        <strong>{knowledgePreview.knowledge_base_code}</strong>
                      </div>
                      <div>
                        <span>负责人</span>
                        <strong>{knowledgePreview.owner}</strong>
                      </div>
                      <div>
                        <span>导入方式</span>
                        <strong>{importModeLabel(knowledgePreview.auto_import)}</strong>
                      </div>
                    </div>
                  </section>
                  <section className="drawer-section">
                    <h4>扩展属性</h4>
                    <pre className="drawer-code-block">{formatAttributes(knowledgePreview.attributes)}</pre>
                  </section>
                  <section className="drawer-section">
                    <div className="drawer-section-head">
                      <h4>文件内容</h4>
                      <span className="status-chip plain">{knowledgePreview.content.length} 字符</span>
                    </div>
                    <pre className="drawer-code-block">{knowledgePreview.content}</pre>
                  </section>
                </>
              ) : null}
            </div>
          </aside>
        </div>
      ) : null}
    </Shell>
  );
}
