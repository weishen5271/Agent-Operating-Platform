from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PackageLoader:
    """Load business package manifests from the repository package catalog."""

    def __init__(self, manifest_dir: Path) -> None:
        self._manifest_dir = manifest_dir

    @classmethod
    def default(cls) -> "PackageLoader":
        repo_root = Path(__file__).resolve().parents[5]
        return cls(repo_root / "packages" / "catalog")

    def list_packages(self) -> list[dict[str, Any]]:
        packages: list[dict[str, Any]] = []
        if not self._manifest_dir.exists():
            return []
        for manifest_path in sorted(self._manifest_dir.glob("*.json")):
            packages.append(self._load_manifest(manifest_path))
        return packages

    def get_package(self, package_id: str) -> dict[str, Any] | None:
        normalized = package_id.strip()
        for package in self.list_packages():
            if package.get("package_id") == normalized:
                return package
        return None

    def _load_manifest(self, manifest_path: Path) -> dict[str, Any]:
        with manifest_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError(f"Package manifest must be an object: {manifest_path}")
        return self._normalize_manifest(raw, manifest_path)

    @staticmethod
    def _normalize_manifest(raw: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
        required = ["package_id", "name", "version", "owner", "status", "domain"]
        missing = [field for field in required if not str(raw.get(field, "")).strip()]
        if missing:
            raise ValueError(f"Package manifest {manifest_path} missing fields: {', '.join(missing)}")
        dependencies = raw.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise ValueError(f"Package manifest dependencies must be a list: {manifest_path}")
        skills = raw.get("skills", [])
        if not isinstance(skills, list):
            raise ValueError(f"Package manifest skills must be a list: {manifest_path}")
        return {
            "package_id": str(raw["package_id"]),
            "name": str(raw["name"]),
            "version": str(raw["version"]),
            "owner": str(raw["owner"]),
            "status": str(raw["status"]),
            "domain": str(raw["domain"]),
            "dependencies": [dict(item) for item in dependencies if isinstance(item, dict)],
            "intents": [dict(item) for item in raw.get("intents", []) if isinstance(item, dict)],
            "skills": [dict(item) for item in skills if isinstance(item, dict)],
        }
