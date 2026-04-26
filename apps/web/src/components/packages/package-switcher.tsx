"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { getTenantPackages, updateTenantPackages } from "@/lib/api-client";
import type { TenantPackagesResponse } from "@/lib/api-client/types";

function parseQuerySelection(defaults: TenantPackagesResponse | null) {
  if (typeof window === "undefined") {
    return {
      primary: defaults?.primary_package ?? "",
      commons: defaults?.common_packages ?? [],
    };
  }
  const params = new URLSearchParams(window.location.search);
  const primary = params.get("primary") || defaults?.primary_package || "";
  const commons = params.get("commons")?.split(",").filter(Boolean) ?? defaults?.common_packages ?? [];
  return { primary, commons };
}

export function PackageSwitcher({
  tenantId,
  packages,
  onPackagesChange,
}: {
  tenantId: string | null | undefined;
  packages: TenantPackagesResponse | null;
  onPackagesChange: (packages: TenantPackagesResponse) => void;
}) {
  const router = useRouter();
  const [primary, setPrimary] = useState("");
  const [commons, setCommons] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tenantId) return;
    getTenantPackages(tenantId)
      .then((data) => {
        onPackagesChange(data);
        const selected = parseQuerySelection(data);
        setPrimary(selected.primary);
        setCommons(selected.commons);
      })
      .catch((exc: Error) => setError(exc.message));
  }, [tenantId, onPackagesChange]);

  useEffect(() => {
    if (!packages) return;
    const selected = parseQuerySelection(packages);
    const fallbackPrimary =
      selected.primary || packages.available_packages.find((item) => item.domain === "industry")?.package_id || "";
    setPrimary(fallbackPrimary);
    setCommons(selected.commons);
  }, [packages]);

  const industryPackages = useMemo(
    () => packages?.available_packages.filter((item) => item.domain === "industry") ?? [],
    [packages],
  );
  const commonOptions = useMemo(
    () => packages?.available_packages.filter((item) => item.domain === "common") ?? [],
    [packages],
  );

  function syncQuery(nextPrimary: string, nextCommons: string[]) {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (nextPrimary) params.set("primary", nextPrimary);
    if (nextCommons.length) {
      params.set("commons", nextCommons.join(","));
    } else {
      params.delete("commons");
    }
    router.replace(`${window.location.pathname}?${params.toString()}` as never);
  }

  function selectPrimary(value: string) {
    setPrimary(value);
    syncQuery(value, commons);
  }

  function toggleCommon(packageId: string) {
    const next = commons.includes(packageId)
      ? commons.filter((item) => item !== packageId)
      : [...commons, packageId];
    setCommons(next);
    syncQuery(primary, next);
  }

  async function saveDefaults() {
    if (!tenantId || !primary) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateTenantPackages(tenantId, {
        primary_package: primary,
        common_packages: commons,
      });
      onPackagesChange(updated);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="package-switcher-panel">
      <div className="package-switcher-section">
        <label htmlFor="primary-package">主行业包</label>
        <select id="primary-package" value={primary} onChange={(event) => selectPrimary(event.target.value)}>
          <option value="" disabled>
            选择主行业包
          </option>
          {industryPackages.map((item) => (
            <option key={item.package_id} value={item.package_id}>
              {item.name} {item.version ?? ""}
            </option>
          ))}
        </select>
      </div>

      <div className="package-switcher-section">
        <span className="package-switcher-label">通用包叠加</span>
        <div className="package-chip-list">
          {commonOptions.map((item) => (
            <button
              key={item.package_id}
              type="button"
              className={`package-chip ${commons.includes(item.package_id) ? "active" : ""}`}
              onClick={() => toggleCommon(item.package_id)}
            >
              {item.name}
            </button>
          ))}
        </div>
      </div>

      {error ? <p className="inline-error">{error}</p> : null}
      <button type="button" className="primary-button compact" disabled={!primary || saving} onClick={saveDefaults}>
        <span className="material-symbols-outlined">save</span>
        {saving ? "保存中..." : "保存为默认"}
      </button>
    </div>
  );
}
