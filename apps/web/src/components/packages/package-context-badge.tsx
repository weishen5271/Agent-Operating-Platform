"use client";

import type { TenantPackagesResponse } from "@/lib/api-client/types";

function packageLabel(packages: TenantPackagesResponse | null, packageId: string | null | undefined): string {
  if (!packageId) return "未选择业务包";
  const item = packages?.available_packages.find((candidate) => candidate.package_id === packageId);
  return item ? `${item.name}${item.version ? ` ${item.version}` : ""}` : packageId;
}

export function PackageContextBadge({
  packages,
  primaryPackage,
  commonPackages,
}: {
  packages: TenantPackagesResponse | null;
  primaryPackage: string | null;
  commonPackages: string[];
}) {
  const primary = packageLabel(packages, primaryPackage);
  const status = packages?.available_packages.find((item) => item.package_id === primaryPackage)?.status;
  const commonTitle = commonPackages.map((item) => packageLabel(packages, item)).join("\n");

  return (
    <div
      className="package-context-badge"
      title={commonTitle ? `叠加通用包:\n${commonTitle}` : "未叠加通用包"}
    >
      <span className="material-symbols-outlined">deployed_code</span>
      <span>{primary}</span>
      {status ? <span className="package-context-muted">· {status}</span> : null}
      {commonPackages.length ? (
        <span className="status-chip plain info">+{commonPackages.length} 通用包</span>
      ) : null}
    </div>
  );
}
