"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { getPackageDetail } from "@/lib/api-client";
import { PackageDependencyGraph } from "@/components/packages/package-dependency-graph";
import { Shell } from "@/components/shared/shell";
import type { PackageDetailResponse } from "@/lib/api-client/types";

function statusTone(status: string): string {
  if (status.includes("运行")) return "success";
  if (status.includes("灰度")) return "warning";
  if (status.includes("待")) return "info";
  return "";
}

export default function PackageDetailPage() {
  const params = useParams<{ packageId: string }>();
  const packageId = decodeURIComponent(params.packageId);
  const [packageDetail, setPackageDetail] = useState<PackageDetailResponse | null>(null);
  const [loadError, setLoadError] = useState("");

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
  }, [packageId]);

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
            <span className={`status-chip ${statusTone(packageDetail.status)}`}>{packageDetail.status}</span>
          </div>
        </div>

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
      </section>
    </Shell>
  );
}
