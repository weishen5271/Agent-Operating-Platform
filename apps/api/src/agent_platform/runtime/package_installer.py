from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from agent_platform.runtime.package_loader import PackageLoader

MAX_BUNDLE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_BUNDLE_FILES = 500
ALLOWED_EXTENSIONS = {".json", ".txt", ".md", ".yaml", ".yml"}
REQUIRED_MANIFEST_FIELDS = ("package_id", "name", "version", "owner", "status", "domain")


class PackageInstallError(ValueError):
    """Raised when an uploaded bundle fails validation."""


class PackageInstaller:
    """Install business package bundles uploaded as zip archives.

    The installer is intentionally conservative for the first stage:
    - only declarative artefacts (json / yaml / txt / md) are accepted
    - no Python code is unpacked or imported
    - extraction is sandboxed via a safe-join check that rejects ``..``
    - extracted bundle is moved into ``packages/installed/<package_id>/``
    """

    def __init__(self, installed_dir: Path) -> None:
        self._installed_dir = installed_dir

    @classmethod
    def default(cls) -> "PackageInstaller":
        loader = PackageLoader.default()
        return cls(installed_dir=loader.installed_dir)

    def install_zip(self, zip_bytes: bytes, *, overwrite: bool = False) -> dict[str, Any]:
        if len(zip_bytes) > MAX_BUNDLE_BYTES:
            raise PackageInstallError(
                f"Bundle exceeds size limit ({MAX_BUNDLE_BYTES // (1024 * 1024)}MB)"
            )

        with tempfile.TemporaryDirectory(prefix="aop_bundle_") as tmp:
            staging = Path(tmp) / "extract"
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
                shutil.rmtree(target_dir)

            shutil.move(str(bundle_root), str(target_dir))

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
                    # Reject absolute / parent-traversal paths.
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
        # Manifest may be at the staging root, or one level deep when the zip
        # was created with a top-level directory.
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
        return manifest

    @staticmethod
    def _safe_dir_name(package_id: str) -> str:
        cleaned = package_id.strip()
        if not cleaned or any(c in cleaned for c in ("/", "\\", "..")):
            raise PackageInstallError(f"Invalid package_id: {package_id!r}")
        return cleaned


