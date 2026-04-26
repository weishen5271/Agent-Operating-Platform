"use client";

import { useMemo, useState } from "react";

import { getPackageImpact } from "@/lib/api-client";
import type { AdminPackagesResponse, PackageImpactResponse } from "@/lib/api-client/types";

export function PackageImpactView({ packages }: { packages: AdminPackagesResponse["packages"] }) {
  const dependencyNames = useMemo(() => {
    const names = new Set<string>();
    for (const item of packages) {
      for (const dependency of item.dependencies ?? []) {
        names.add(dependency.name);
      }
    }
    return [...names].sort();
  }, [packages]);

  const [targetName, setTargetName] = useState(dependencyNames[0] ?? "");
  const [targetVersion, setTargetVersion] = useState("1.0.0");
  const [impact, setImpact] = useState<PackageImpactResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function queryImpact() {
    if (!targetName || !targetVersion) return;
    setLoading(true);
    setError(null);
    try {
      setImpact(await getPackageImpact(`${targetName}@${targetVersion}`));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "影响分析失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel-card">
      <div className="panel-header">
        <div>
          <h3>升级影响分析</h3>
          <p>选择目标依赖和版本，扫描业务包反向依赖与兼容风险。</p>
        </div>
      </div>

      <div className="impact-toolbar">
        <label>
          <span>目标依赖</span>
          <select value={targetName} onChange={(event) => setTargetName(event.target.value)}>
            {dependencyNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>目标版本</span>
          <input value={targetVersion} onChange={(event) => setTargetVersion(event.target.value)} />
        </label>
        <button type="button" className="primary-button compact" disabled={!targetName || loading} onClick={queryImpact}>
          <span className="material-symbols-outlined">travel_explore</span>
          {loading ? "分析中..." : "分析影响"}
        </button>
      </div>

      {error ? <p className="inline-error">{error}</p> : null}

      {impact ? (
        <div className="stack-list">
          {impact.affected_packages.length ? (
            impact.affected_packages.map((item) => (
              <article key={`${item.package_id}-${item.dependency.name}`} className="stack-item">
                <div>
                  <strong>{item.name}</strong>
                  <p>
                    {item.package_id} · {item.dependency.kind} · 要求 {item.dependency.version_range} · {item.reason}
                  </p>
                </div>
                <span className={`risk-level ${item.compatible ? "low" : "high"}`}>
                  {item.compatible ? "低风险" : "高风险"}
                </span>
              </article>
            ))
          ) : (
            <article className="stack-item">
              <div>
                <strong>未发现反向依赖</strong>
                <p>{impact.target.name}@{impact.target.version} 当前不影响业务包目录。</p>
              </div>
              <span className="status-chip plain">empty</span>
            </article>
          )}
        </div>
      ) : null}
    </section>
  );
}
