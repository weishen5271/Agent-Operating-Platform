from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_platform.runtime.package_loader import PackageLoader

MAX_BUNDLE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_BUNDLE_FILES = 500
ALLOWED_EXTENSIONS = {".json", ".txt", ".md", ".yaml", ".yml"}
REQUIRED_MANIFEST_FIELDS = ("package_id", "name", "version", "owner", "status", "domain")


class PackageInstallError(ValueError):
    """上传的业务包 bundle 未通过安全或结构校验时抛出。"""


class PackageInstaller:
    """安装以 zip 上传的业务包 bundle。

    这里是业务包进入平台的安全边界：
    - 只接受 json/yaml/txt/md 等声明式文件。
    - 不解压或导入 Python 代码，避免上传即获得执行能力。
    - 所有路径都经过安全拼接校验，拒绝 ``..`` 越界写入。
    - 校验通过后才移动到 ``packages/installed/<package_id>/``。
    """

    def __init__(self, installed_dir: Path, *, temp_dir: Path | None = None) -> None:
        self._installed_dir = installed_dir
        self._temp_dir = temp_dir

    @classmethod
    def default(cls) -> "PackageInstaller":
        loader = PackageLoader.default()
        return cls(installed_dir=loader.installed_dir)

    def install_zip(self, zip_bytes: bytes, *, overwrite: bool = False) -> dict[str, Any]:
        if len(zip_bytes) > MAX_BUNDLE_BYTES:
            raise PackageInstallError(
                f"Bundle exceeds size limit ({MAX_BUNDLE_BYTES // (1024 * 1024)}MB)"
            )

        # 先解压到临时目录并完成完整校验，避免半成品 bundle 出现在 installed 目录中。
        temp_parent = self._temp_dir or Path(tempfile.gettempdir())
        temp_root = temp_parent / f"aop_bundle_{uuid4().hex[:12]}"
        try:
            temp_root.mkdir(parents=True, exist_ok=False)
            staging = temp_root / "extract"
            staging.mkdir(parents=True, exist_ok=True)
            self._extract_zip(zip_bytes, staging)
            bundle_root = self._locate_bundle_root(staging)
            manifest = self._validate_bundle(bundle_root)

            package_id = str(manifest["package_id"])
            self._installed_dir.mkdir(parents=True, exist_ok=True)
            target_dir = self._installed_dir / self._safe_dir_name(package_id)

            if target_dir.exists():
                if not overwrite:
                    raise PackageInstallError(
                        f"Package already installed: {package_id} (pass overwrite=true to replace)"
                    )
                # 覆盖安装只在 manifest 和引用文件全部校验通过后执行，降低误删可用版本的概率。
                shutil.rmtree(target_dir)

            shutil.move(str(bundle_root), str(target_dir))
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        return {
            "package_id": package_id,
            "version": manifest["version"],
            "name": manifest["name"],
            "installed_path": str(target_dir),
            "skills": len(manifest.get("provides", {}).get("skills", [])),
            "tools": len(manifest.get("provides", {}).get("tools", [])),
            "plugins": len(manifest.get("provides", {}).get("plugins", [])),
        }

    def uninstall(self, package_id: str) -> bool:
        target_dir = self._installed_dir / self._safe_dir_name(package_id)
        if not target_dir.exists():
            return False
        shutil.rmtree(target_dir)
        return True

    @staticmethod
    def _extract_zip(zip_bytes: bytes, staging: Path) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
                names = archive.namelist()
                if len(names) > MAX_BUNDLE_FILES:
                    raise PackageInstallError(
                        f"Bundle contains too many files (>{MAX_BUNDLE_FILES})"
                    )
                total = 0
                for member in archive.infolist():
                    name = member.filename
                    if not name or name.endswith("/"):
                        continue
                    # 先解析到目标目录下，再校验相对关系，阻止绝对路径和父目录穿越。
                    candidate = (staging / name).resolve()
                    try:
                        candidate.relative_to(staging.resolve())
                    except ValueError as exc:
                        raise PackageInstallError(f"Unsafe path in bundle: {name}") from exc
                    suffix = Path(name).suffix.lower()
                    if suffix and suffix not in ALLOWED_EXTENSIONS:
                        raise PackageInstallError(
                            f"Disallowed file extension in bundle: {name}"
                        )
                    total += member.file_size
                    if total > MAX_BUNDLE_BYTES:
                        raise PackageInstallError("Bundle uncompressed size exceeds limit")
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as src, candidate.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
        except zipfile.BadZipFile as exc:
            raise PackageInstallError("Uploaded file is not a valid zip archive") from exc

    @staticmethod
    def _locate_bundle_root(staging: Path) -> Path:
        # 兼容两种常见压缩方式：manifest 在 zip 根目录，或在唯一一级顶层目录内。
        if (staging / "manifest.json").exists():
            return staging
        children = [p for p in staging.iterdir() if p.is_dir()]
        if len(children) == 1 and (children[0] / "manifest.json").exists():
            return children[0]
        raise PackageInstallError("Bundle is missing manifest.json at root")

    @staticmethod
    def _validate_bundle(bundle_root: Path) -> dict[str, Any]:
        manifest_path = bundle_root / "manifest.json"
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        if not isinstance(manifest, dict):
            raise PackageInstallError("manifest.json must be an object")
        missing = [field for field in REQUIRED_MANIFEST_FIELDS if not str(manifest.get(field, "")).strip()]
        if missing:
            raise PackageInstallError(f"manifest.json missing fields: {', '.join(missing)}")

        provides = manifest.get("provides") or {}
        if not isinstance(provides, dict):
            raise PackageInstallError("manifest.provides must be an object")
        # provides 中声明的能力文件必须真实存在且是 JSON 对象，后续注册表会直接读取这些声明。
        for kind in ("skills", "tools", "plugins"):
            for rel_path in provides.get(kind, []) or []:
                if not isinstance(rel_path, str):
                    raise PackageInstallError(f"provides.{kind} entries must be strings")
                target = (bundle_root / rel_path).resolve()
                try:
                    target.relative_to(bundle_root.resolve())
                except ValueError as exc:
                    raise PackageInstallError(
                        f"provides.{kind} path escapes bundle: {rel_path}"
                    ) from exc
                if not target.exists():
                    raise PackageInstallError(
                        f"provides.{kind} references missing file: {rel_path}"
                    )
                with target.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if not isinstance(payload, dict) or not str(payload.get("name", "")).strip():
                    raise PackageInstallError(
                        f"{kind[:-1]} artefact missing 'name': {rel_path}"
                    )

        knowledge_imports = manifest.get("knowledge_imports", []) or []
        if not isinstance(knowledge_imports, list):
            raise PackageInstallError("manifest.knowledge_imports must be a list")
        # 知识导入只校验文件与元数据结构，不在安装阶段静默写入知识库。
        for index, item in enumerate(knowledge_imports):
            if not isinstance(item, dict):
                raise PackageInstallError(f"knowledge_imports[{index}] must be an object")
            rel_path = item.get("file")
            if not isinstance(rel_path, str) or not rel_path.strip():
                raise PackageInstallError(f"knowledge_imports[{index}].file is required")
            target = (bundle_root / rel_path).resolve()
            try:
                target.relative_to(bundle_root.resolve())
            except ValueError as exc:
                raise PackageInstallError(
                    f"knowledge_imports[{index}] path escapes bundle: {rel_path}"
                ) from exc
            if not target.exists():
                raise PackageInstallError(
                    f"knowledge_imports[{index}] references missing file: {rel_path}"
                )
            attributes = item.get("attributes", {})
            if attributes is not None and not isinstance(attributes, dict):
                raise PackageInstallError(f"knowledge_imports[{index}].attributes must be an object")
            if "auto_import" in item and not isinstance(item["auto_import"], bool):
                raise PackageInstallError(f"knowledge_imports[{index}].auto_import must be a boolean")
        return manifest

    @staticmethod
    def _safe_dir_name(package_id: str) -> str:
        cleaned = package_id.strip()
        if not cleaned or any(c in cleaned for c in ("/", "\\", "..")):
            raise PackageInstallError(f"Invalid package_id: {package_id!r}")
        return cleaned
