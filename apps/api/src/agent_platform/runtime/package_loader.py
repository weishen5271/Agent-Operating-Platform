from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PackageLoader:
    """加载并归一化业务包清单。

    当前同时支持两类来源：
    - ``packages/catalog/*.json``：内置示例业务包的旧格式平铺清单。
    - ``packages/installed/<package_id>/manifest.json``：通过导入接口安装的 bundle。

    bundle 内的 skills、tools、plugins、prompts、knowledge 会在加载阶段合并进统一清单，
    下游注册表不需要关心业务包来自内置目录还是上传安装目录。
    """

    INSTALLED_DIRNAME = "installed"
    CATALOG_DIRNAME = "catalog"
    DEFAULT_BUNDLE_STATUS = "运行中"

    def __init__(self, catalog_dir: Path, installed_dir: Path | None = None) -> None:
        self._catalog_dir = catalog_dir
        self._installed_dir = installed_dir or catalog_dir.parent / self.INSTALLED_DIRNAME

    @classmethod
    def default(cls) -> "PackageLoader":
        repo_root = Path(__file__).resolve().parents[5]
        packages_root = repo_root / "packages"
        return cls(
            catalog_dir=packages_root / cls.CATALOG_DIRNAME,
            installed_dir=packages_root / cls.INSTALLED_DIRNAME,
        )

    @property
    def installed_dir(self) -> Path:
        return self._installed_dir

    def list_packages(self) -> list[dict[str, Any]]:
        packages: list[dict[str, Any]] = []
        seen: set[str] = set()

        # 同 package_id 同时存在时，安装目录优先于内置示例，便于本地覆盖验证 bundle。
        if self._installed_dir.exists():
            for bundle_dir in sorted(p for p in self._installed_dir.iterdir() if p.is_dir()):
                manifest_path = bundle_dir / "manifest.json"
                if not manifest_path.exists():
                    continue
                manifest = self._load_manifest(manifest_path, bundle_dir=bundle_dir)
                packages.append(manifest)
                seen.add(str(manifest["package_id"]))

        if self._catalog_dir.exists():
            for manifest_path in sorted(self._catalog_dir.glob("*.json")):
                manifest = self._load_manifest(manifest_path, bundle_dir=None)
                if str(manifest["package_id"]) in seen:
                    continue
                packages.append(manifest)

        return packages

    def get_package(self, package_id: str) -> dict[str, Any] | None:
        normalized = package_id.strip()
        for package in self.list_packages():
            if package.get("package_id") == normalized:
                return package
        return None

    def _load_manifest(self, manifest_path: Path, *, bundle_dir: Path | None) -> dict[str, Any]:
        with manifest_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError(f"Package manifest must be an object: {manifest_path}")
        return self._normalize_manifest(raw, manifest_path, bundle_dir=bundle_dir)

    @classmethod
    def _normalize_manifest(
        cls,
        raw: dict[str, Any],
        manifest_path: Path,
        *,
        bundle_dir: Path | None,
    ) -> dict[str, Any]:
        required = ["package_id", "name", "version", "owner", "domain"]
        if bundle_dir is None:
            required.append("status")
        missing = [field for field in required if not str(raw.get(field, "")).strip()]
        if missing:
            raise ValueError(f"Package manifest {manifest_path} missing fields: {', '.join(missing)}")

        # dependencies 是历史字段，requires 是 bundle 阶段字段；归一化后统一给影响分析使用。
        legacy_dependencies = raw.get("dependencies", [])
        requires = raw.get("requires", [])
        if not isinstance(legacy_dependencies, list) or not isinstance(requires, list):
            raise ValueError(f"Package manifest dependencies/requires must be a list: {manifest_path}")
        merged_deps = [dict(item) for item in (*legacy_dependencies, *requires) if isinstance(item, dict)]

        # 内置 catalog 可以直接内联定义能力；bundle 则通过 provides 引用独立声明文件。
        skills = [dict(item) for item in raw.get("skills", []) if isinstance(item, dict)]
        tools: list[dict[str, Any]] = [dict(item) for item in raw.get("tools", []) if isinstance(item, dict)]
        plugins: list[dict[str, Any]] = [dict(item) for item in raw.get("plugins", []) if isinstance(item, dict)]

        provides = raw.get("provides") or {}
        if not isinstance(provides, dict):
            raise ValueError(f"Package manifest provides must be an object: {manifest_path}")

        if bundle_dir is not None:
            skills.extend(cls._load_provided(bundle_dir, provides.get("skills", []), "skill"))
            tools.extend(cls._load_provided(bundle_dir, provides.get("tools", []), "tool"))
            plugins.extend(cls._load_provided(bundle_dir, provides.get("plugins", []), "plugin"))

        knowledge_imports = cls._normalize_knowledge_imports(
            raw.get("knowledge_imports", []),
            manifest_path=manifest_path,
            bundle_dir=bundle_dir,
            package_id=str(raw["package_id"]),
        )
        if not knowledge_imports and bundle_dir is not None:
            knowledge_imports = cls._discover_knowledge_imports(
                bundle_dir=bundle_dir,
                package_id=str(raw["package_id"]),
            )

        prompts: dict[str, str] = {}
        prompt_refs = raw.get("prompts") or {}
        if isinstance(prompt_refs, dict) and bundle_dir is not None:
            for prompt_name, rel_path in prompt_refs.items():
                if not isinstance(rel_path, str) or not rel_path.strip():
                    continue
                prompt_path = cls._safe_join(bundle_dir, rel_path)
                if prompt_path.exists():
                    prompts[str(prompt_name)] = prompt_path.read_text(encoding="utf-8")

        return {
            "package_id": str(raw["package_id"]),
            "name": str(raw["name"]),
            "version": str(raw["version"]),
            "owner": str(raw["owner"]),
            "status": cls.DEFAULT_BUNDLE_STATUS if bundle_dir is not None else str(raw["status"]),
            "domain": str(raw["domain"]),
            "description": str(raw.get("description", "")),
            "dependencies": merged_deps,
            "intents": [dict(item) for item in raw.get("intents", []) if isinstance(item, dict)],
            "knowledge_bindings": [
                dict(item) for item in raw.get("knowledge_bindings", []) if isinstance(item, dict)
            ],
            "knowledge_imports": knowledge_imports,
            "default_outputs": [str(item) for item in raw.get("default_outputs", []) if str(item).strip()],
            "skills": skills,
            "tools": tools,
            "plugins": plugins,
            "prompts": prompts,
            "source_kind": "bundle" if bundle_dir is not None else "catalog",
            "bundle_path": str(bundle_dir) if bundle_dir is not None else None,
        }

    @classmethod
    def _load_provided(
        cls,
        bundle_dir: Path,
        rel_paths: Any,
        artefact_kind: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(rel_paths, list):
            raise ValueError(f"provides.{artefact_kind}s must be a list of paths")
        artefacts: list[dict[str, Any]] = []
        for rel_path in rel_paths:
            if not isinstance(rel_path, str) or not rel_path.strip():
                raise ValueError(f"Invalid {artefact_kind} path: {rel_path!r}")
            artefact_path = cls._safe_join(bundle_dir, rel_path)
            if not artefact_path.exists():
                raise ValueError(f"Missing {artefact_kind} artefact: {rel_path}")
            with artefact_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                raise ValueError(f"{artefact_kind} file must be a JSON object: {rel_path}")
            artefacts.append(payload)
        return artefacts

    @classmethod
    def _normalize_knowledge_imports(
        cls,
        entries: Any,
        *,
        manifest_path: Path,
        bundle_dir: Path | None,
        package_id: str,
    ) -> list[dict[str, Any]]:
        if entries in (None, ""):
            return []
        if not isinstance(entries, list):
            raise ValueError(f"Package manifest knowledge_imports must be a list: {manifest_path}")

        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(entries):
            if not isinstance(item, dict):
                raise ValueError(f"knowledge_imports[{index}] must be an object: {manifest_path}")

            rel_path = str(item.get("file", "")).strip()
            if not rel_path:
                raise ValueError(f"knowledge_imports[{index}].file is required: {manifest_path}")
            if bundle_dir is not None:
                target = cls._safe_join(bundle_dir, rel_path)
                if not target.exists():
                    raise ValueError(f"knowledge_imports[{index}] references missing file: {rel_path}")

            attributes = item.get("attributes", {})
            if attributes is None:
                attributes = {}
            if not isinstance(attributes, dict):
                raise ValueError(f"knowledge_imports[{index}].attributes must be an object: {manifest_path}")

            source_type = str(item.get("source_type") or item.get("source") or "Markdown").strip() or "Markdown"
            knowledge_base_code = str(item.get("knowledge_base_code") or "knowledge").strip() or "knowledge"
            owner = str(item.get("owner") or f"bundle:{package_id}").strip() or f"bundle:{package_id}"
            name = str(item.get("name") or Path(rel_path).name).strip() or Path(rel_path).name

            normalized.append(
                {
                    "file": rel_path,
                    "name": name,
                    "source_type": source_type,
                    "knowledge_base_code": knowledge_base_code,
                    "owner": owner,
                    "auto_import": bool(item.get("auto_import", False)),
                    "attributes": dict(attributes),
                }
            )
        return normalized

    @classmethod
    def _discover_knowledge_imports(cls, *, bundle_dir: Path, package_id: str) -> list[dict[str, Any]]:
        knowledge_dir = cls._safe_join(bundle_dir, "knowledge")
        if not knowledge_dir.is_dir():
            return []

        imports: list[dict[str, Any]] = []
        for path in sorted(item for item in knowledge_dir.rglob("*") if item.is_file()):
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            rel_path = path.relative_to(bundle_dir).as_posix()
            imports.append(
                {
                    "file": rel_path,
                    "name": path.stem,
                    "source_type": "Markdown" if path.suffix.lower() == ".md" else "Text",
                    "knowledge_base_code": "knowledge",
                    "owner": f"bundle:{package_id}",
                    "auto_import": False,
                    "attributes": {},
                }
            )
        return imports

    @staticmethod
    def _safe_join(bundle_dir: Path, rel_path: str) -> Path:
        candidate = (bundle_dir / rel_path).resolve()
        try:
            candidate.relative_to(bundle_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Path escapes bundle: {rel_path}") from exc
        return candidate
