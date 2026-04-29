from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agent_platform.domain.models import KnowledgeBase, KnowledgeSource, UserContext, utc_now
from agent_platform.runtime.chat_service import ChatService
from agent_platform.runtime.package_installer import PackageInstallError, PackageInstaller
from agent_platform.runtime.package_loader import PackageLoader
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.runtime.skill_registry import SkillRegistry


@pytest.fixture
def workspace_tmp() -> Path:
    root = Path.cwd() / ".pytest-workspace-tmp" / f"bundle-{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def make_zip(files: dict[str, str | dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in files.items():
            content = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload
            archive.writestr(name, content)
    return buffer.getvalue()


def make_zip_with_cp437_mojibake_name(files: dict[str, str | dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in files.items():
            content = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload
            mojibake_name = name.encode("utf-8").decode("cp437")
            archive.writestr(mojibake_name, content)
    return buffer.getvalue()


def manifest(*, package_id: str = "pkg.pipeline", version: str = "1.0.0") -> dict[str, Any]:
    return {
        "package_id": package_id,
        "name": "Pipeline Test Package",
        "version": version,
        "owner": "test",
        "domain": "common",
        "provides": {
            "skills": ["skills/lookup.json"],
            "tools": [],
            "plugins": ["plugins/lookup.json"],
        },
        "prompts": {"answer": "prompts/answer.md"},
        "knowledge_imports": [],
    }


def plugin_contract(*, capability_name: str = "pkg.pipeline.lookup") -> dict[str, Any]:
    return {
        "name": "pkg.pipeline.plugin",
        "executor": "stub",
        "config_schema": {
            "endpoint": {"type": "string", "required": True, "label": "接口地址"},
        },
        "capabilities": [
            {
                "name": capability_name,
                "description": "Protocol fixture capability",
                "risk_level": "low",
                "side_effect_level": "read",
                "required_scope": "pipeline:read",
                "input_schema": {"required": ["query"]},
                "output_schema": {"required": ["answer"]},
            }
        ],
    }


def skill_contract(*, capability_name: str = "pkg.pipeline.lookup") -> dict[str, Any]:
    return {
        "name": "pipeline_lookup",
        "description": "Protocol fixture skill",
        "version": "1.0.0",
        "depends_on_capabilities": [capability_name],
        "depends_on_tools": [],
        "steps": [
            {
                "id": "lookup",
                "capability": capability_name,
                "input": {"query": "$inputs.query"},
            }
        ],
        "outputs_mapping": {"answer": "$steps.lookup.answer"},
    }


def bundle_zip(*, package_id: str = "pkg.pipeline", version: str = "1.0.0") -> bytes:
    return make_zip(
        {
            "manifest.json": manifest(package_id=package_id, version=version),
            "plugins/lookup.json": plugin_contract(),
            "skills/lookup.json": skill_contract(),
            "prompts/answer.md": "Use registered capability results.",
        }
    )


class FakeUsers:
    async def get(self, tenant_id: str, user_id: str) -> UserContext:
        return UserContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role="platform_admin",
            scopes=["admin:read", "tenant:manage"],
            email="admin@example.com",
        )


class RecordingKnowledgeRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def ingest_text(
        self,
        *,
        tenant_id: str,
        name: str,
        content: str,
        source_type: str,
        owner: str,
        knowledge_base_code: str,
        attributes: dict[str, object] | None = None,
    ) -> KnowledgeSource:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "name": name,
                "content": content,
                "source_type": source_type,
                "owner": owner,
                "knowledge_base_code": knowledge_base_code,
                "attributes": attributes,
            }
        )
        return KnowledgeSource(
            source_id=f"ks-{len(self.calls)}",
            tenant_id=tenant_id,
            knowledge_base_code=knowledge_base_code,
            name=name,
            source_type=source_type,
            owner=owner,
            chunk_count=1,
            status="运行中",
        )


class RecordingKnowledgeBaseRepository:
    def __init__(self, items: list[KnowledgeBase] | None = None) -> None:
        self.items = list(items or [])
        self.created: list[KnowledgeBase] = []
        self.deleted: list[dict[str, str]] = []

    async def list_by_tenant(self, tenant_id: str) -> list[KnowledgeBase]:
        return [item for item in self.items if item.tenant_id == tenant_id]

    async def create(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        self.items.append(knowledge_base)
        self.created.append(knowledge_base)
        return knowledge_base

    async def delete(self, tenant_id: str, knowledge_base_code: str) -> bool:
        self.deleted.append(
            {
                "tenant_id": tenant_id,
                "knowledge_base_code": knowledge_base_code,
            }
        )
        before = len(self.items)
        self.items = [
            item
            for item in self.items
            if not (item.tenant_id == tenant_id and item.knowledge_base_code == knowledge_base_code)
        ]
        return len(self.items) != before


def test_bundle_install_load_and_registers_capability_and_skill(workspace_tmp: Path) -> None:
    installed_dir = workspace_tmp / "installed"
    catalog_dir = workspace_tmp / "catalog"
    catalog_dir.mkdir()
    installer = PackageInstaller(installed_dir, temp_dir=workspace_tmp)

    install_result = installer.install_zip(bundle_zip())
    loader = PackageLoader(catalog_dir=catalog_dir, installed_dir=installed_dir)
    packages = loader.list_packages()
    registry = CapabilityRegistry(loader=loader)
    skills = SkillRegistry(loader=loader)

    assert install_result["package_id"] == "pkg.pipeline"
    assert install_result["plugins"] == 1
    assert install_result["skills"] == 1
    assert packages[0]["package_id"] == "pkg.pipeline"
    assert packages[0]["source_kind"] == "bundle"
    assert packages[0]["plugins"][0]["name"] == "pkg.pipeline.plugin"
    assert packages[0]["skills"][0]["name"] == "pipeline_lookup"
    assert packages[0]["prompts"] == {"answer": "Use registered capability results."}
    assert packages[0]["knowledge_imports"] == []
    assert registry.get("pkg.pipeline.lookup").package_id == "pkg.pipeline"
    assert registry.get_plugin("pkg.pipeline.plugin").config_schema == {
        "endpoint": {"type": "string", "required": True, "label": "接口地址"},
    }
    assert skills.get("pkg.pipeline::pipeline_lookup") is not None


def test_bundle_loads_knowledge_imports_without_auto_ingesting(workspace_tmp: Path) -> None:
    installed_dir = workspace_tmp / "installed"
    catalog_dir = workspace_tmp / "catalog"
    catalog_dir.mkdir()
    installer = PackageInstaller(installed_dir, temp_dir=workspace_tmp)
    bundle = make_zip(
        {
            "manifest.json": {
                **manifest(package_id="pkg.knowledge"),
                "knowledge_imports": [
                    {
                        "file": "knowledge/sop.md",
                        "source": "equipment_sop",
                        "attributes": {"equipment_model": "MX-1"},
                    }
                ],
            },
            "plugins/lookup.json": plugin_contract(),
            "skills/lookup.json": skill_contract(),
            "prompts/answer.md": "prompt",
            "knowledge/sop.md": "# SOP\n\nUse the real bundle document.",
        }
    )

    installer.install_zip(bundle)
    package = PackageLoader(catalog_dir=catalog_dir, installed_dir=installed_dir).get_package("pkg.knowledge")

    assert package is not None
    assert package["knowledge_imports"] == [
        {
            "file": "knowledge/sop.md",
            "name": "sop.md",
            "source_type": "equipment_sop",
            "knowledge_base_code": "pkg-pkg-knowledge",
            "owner": "bundle:pkg.knowledge",
            "auto_import": False,
            "attributes": {"equipment_model": "MX-1"},
        }
    ]


def test_bundle_discovers_knowledge_files_when_imports_not_declared(workspace_tmp: Path) -> None:
    installed_dir = workspace_tmp / "installed"
    catalog_dir = workspace_tmp / "catalog"
    catalog_dir.mkdir()
    installer = PackageInstaller(installed_dir, temp_dir=workspace_tmp)
    manifest_payload = manifest(package_id="pkg.knowledge.discovery")
    manifest_payload.pop("knowledge_imports")
    installer.install_zip(
        make_zip(
            {
                "manifest.json": manifest_payload,
                "plugins/lookup.json": plugin_contract(),
                "skills/lookup.json": skill_contract(),
                "prompts/answer.md": "prompt",
                "knowledge/sop.md": "# SOP\n\nUse the real bundle document.",
                "knowledge/runbook.txt": "Check alarm and dispatch work order.",
            }
        )
    )

    package = PackageLoader(catalog_dir=catalog_dir, installed_dir=installed_dir).get_package(
        "pkg.knowledge.discovery"
    )

    assert package is not None
    assert package["knowledge_imports"] == [
        {
            "file": "knowledge/runbook.txt",
            "name": "runbook",
            "source_type": "Text",
            "knowledge_base_code": "pkg-pkg-knowledge-discovery",
            "owner": "bundle:pkg.knowledge.discovery",
            "auto_import": True,
            "attributes": {},
        },
        {
            "file": "knowledge/sop.md",
            "name": "sop",
            "source_type": "Markdown",
            "knowledge_base_code": "pkg-pkg-knowledge-discovery",
            "owner": "bundle:pkg.knowledge.discovery",
            "auto_import": True,
            "attributes": {},
        },
    ]


def test_bundle_install_repairs_utf8_zip_names_without_utf8_flag(workspace_tmp: Path) -> None:
    installed_dir = workspace_tmp / "installed"
    catalog_dir = workspace_tmp / "catalog"
    catalog_dir.mkdir()
    installer = PackageInstaller(installed_dir, temp_dir=workspace_tmp)
    manifest_payload = manifest(package_id="pkg.knowledge.filename")
    manifest_payload.pop("knowledge_imports")

    installer.install_zip(
        make_zip_with_cp437_mojibake_name(
            {
                "manifest.json": manifest_payload,
                "plugins/lookup.json": plugin_contract(),
                "skills/lookup.json": skill_contract(),
                "prompts/answer.md": "prompt",
                "knowledge/故障代码库-AX系列伺服.md": "# 故障代码库\n\nAX-203: 伺服报警。",
            }
        )
    )

    package = PackageLoader(catalog_dir=catalog_dir, installed_dir=installed_dir).get_package(
        "pkg.knowledge.filename"
    )

    assert package is not None
    assert package["knowledge_imports"] == [
        {
            "file": "knowledge/故障代码库-AX系列伺服.md",
            "name": "故障代码库-AX系列伺服",
            "source_type": "Markdown",
            "knowledge_base_code": "pkg-pkg-knowledge-filename",
            "owner": "bundle:pkg.knowledge.filename",
            "auto_import": True,
            "attributes": {},
        }
    ]
    assert (installed_dir / "pkg.knowledge.filename" / "knowledge" / "故障代码库-AX系列伺服.md").exists()


def test_bundle_install_rejects_knowledge_import_path_escape(workspace_tmp: Path) -> None:
    installer = PackageInstaller(workspace_tmp / "installed", temp_dir=workspace_tmp)
    unsafe_zip = make_zip(
        {
            "manifest.json": {
                **manifest(package_id="pkg.knowledge.escape"),
                "knowledge_imports": [{"file": "../outside.md"}],
            },
            "plugins/lookup.json": plugin_contract(),
            "skills/lookup.json": skill_contract(),
            "prompts/answer.md": "prompt",
        }
    )

    with pytest.raises(PackageInstallError, match="path escapes bundle"):
        installer.install_zip(unsafe_zip)


def test_import_package_knowledge_requires_explicit_service_call(
    workspace_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_dir = workspace_tmp / "installed"
    catalog_dir = workspace_tmp / "catalog"
    catalog_dir.mkdir()
    installer = PackageInstaller(installed_dir, temp_dir=workspace_tmp)
    installer.install_zip(
        make_zip(
            {
                "manifest.json": {
                    **manifest(package_id="pkg.knowledge.import"),
                    "knowledge_imports": [
                        {
                            "file": "knowledge/sop.md",
                            "name": "设备 SOP",
                            "source_type": "equipment_sop",
                            "knowledge_base_code": "maintenance",
                            "owner": "bundle:pkg.knowledge.import",
                            "auto_import": True,
                            "attributes": {"equipment_model": "MX-1"},
                        }
                    ],
                },
                "plugins/lookup.json": plugin_contract(),
                "skills/lookup.json": skill_contract(),
                "prompts/answer.md": "prompt",
                "knowledge/sop.md": "# SOP\n\nUse the real bundle document.",
            }
        )
    )
    loader = PackageLoader(catalog_dir=catalog_dir, installed_dir=installed_dir)
    monkeypatch.setattr(PackageLoader, "default", classmethod(lambda cls: loader))
    knowledge = RecordingKnowledgeRepository()
    knowledge_bases = RecordingKnowledgeBaseRepository()
    service = ChatService(
        registry=object(),
        skills=object(),
        tools=object(),
        conversations=object(),
        traces=object(),
        tenants=object(),
        tool_overrides=object(),
        output_guard_rules=object(),
        plugin_configs=object(),
        releases=object(),
        users=FakeUsers(),
        drafts=object(),
        security_events=object(),
        knowledge_sources=knowledge,
        knowledge_bases=knowledge_bases,
        wiki_service=object(),
        llm_config=object(),
        llm_client=object(),
    )

    import asyncio

    result = asyncio.run(
        service.import_package_knowledge(
            "pkg.knowledge.import",
            tenant_id="tenant-a",
            user_id="admin",
            auto_only=True,
        )
    )

    assert result["imported_count"] == 1
    assert knowledge.calls == [
        {
            "tenant_id": "tenant-a",
            "name": "设备 SOP",
            "content": "# SOP\n\nUse the real bundle document.",
            "source_type": "equipment_sop",
            "owner": "bundle:pkg.knowledge.import",
            "knowledge_base_code": "maintenance",
            "attributes": {"equipment_model": "MX-1"},
        }
    ]
    assert [item.knowledge_base_code for item in knowledge_bases.created] == ["maintenance"]


def test_uninstall_package_bundle_deletes_managed_knowledge_base(
    workspace_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_dir = workspace_tmp / "installed"
    catalog_dir = workspace_tmp / "catalog"
    catalog_dir.mkdir()
    installer = PackageInstaller(installed_dir, temp_dir=workspace_tmp)
    installer.install_zip(
        make_zip(
            {
                "manifest.json": {
                    **manifest(package_id="pkg.knowledge.cleanup"),
                },
                "plugins/lookup.json": plugin_contract(),
                "skills/lookup.json": skill_contract(),
                "prompts/answer.md": "prompt",
                "knowledge/sop.md": "# SOP\n\nUse the real bundle document.",
            }
        )
    )
    loader = PackageLoader(catalog_dir=catalog_dir, installed_dir=installed_dir)
    monkeypatch.setattr(PackageLoader, "default", classmethod(lambda cls: loader))
    monkeypatch.setattr(PackageInstaller, "default", classmethod(lambda cls: installer))
    now = utc_now()
    knowledge_bases = RecordingKnowledgeBaseRepository(
        [
            KnowledgeBase(
                knowledge_base_id="kb-cleanup",
                knowledge_base_code="pkg-pkg-knowledge-cleanup",
                tenant_id="tenant-a",
                name="Pipeline Test Package",
                description="",
                status="active",
                created_by="admin",
                updated_by="admin",
                created_at=now,
                updated_at=now,
            )
        ]
    )
    service = ChatService(
        registry=CapabilityRegistry(loader=loader),
        skills=SkillRegistry(loader=loader),
        tools=object(),
        conversations=object(),
        traces=object(),
        tenants=object(),
        tool_overrides=object(),
        output_guard_rules=object(),
        plugin_configs=object(),
        releases=object(),
        users=FakeUsers(),
        drafts=object(),
        security_events=object(),
        knowledge_sources=object(),
        knowledge_bases=knowledge_bases,
        wiki_service=object(),
        llm_config=object(),
        llm_client=object(),
    )

    import asyncio

    result = asyncio.run(
        service.uninstall_package_bundle(
            "pkg.knowledge.cleanup",
            tenant_id="tenant-a",
            user_id="admin",
        )
    )

    assert result["removed"] is True
    assert result["knowledge_base_code"] == "pkg-pkg-knowledge-cleanup"
    assert result["knowledge_base_deleted"] is True
    assert knowledge_bases.deleted == [
        {
            "tenant_id": "tenant-a",
            "knowledge_base_code": "pkg-pkg-knowledge-cleanup",
        }
    ]


def test_bundle_install_requires_overwrite_for_existing_package(workspace_tmp: Path) -> None:
    installer = PackageInstaller(workspace_tmp / "installed", temp_dir=workspace_tmp)
    first = installer.install_zip(bundle_zip(version="1.0.0"))

    with pytest.raises(PackageInstallError, match="already installed"):
        installer.install_zip(bundle_zip(version="1.0.1"))

    overwritten = installer.install_zip(bundle_zip(version="1.0.1"), overwrite=True)

    assert first["version"] == "1.0.0"
    assert overwritten["version"] == "1.0.1"


def test_bundle_install_ignores_macos_archive_metadata(workspace_tmp: Path) -> None:
    installer = PackageInstaller(workspace_tmp / "installed", temp_dir=workspace_tmp)
    bundle = make_zip(
        {
            "industry.mfg_maintenance/manifest.json": manifest(package_id="pkg.macos"),
            "industry.mfg_maintenance/plugins/lookup.json": plugin_contract(),
            "industry.mfg_maintenance/skills/lookup.json": skill_contract(),
            "industry.mfg_maintenance/prompts/answer.md": "prompt",
            "__MACOSX/._industry.mfg_maintenance": "macOS resource fork metadata",
            "industry.mfg_maintenance/.DS_Store": "Finder metadata",
            "industry.mfg_maintenance/prompts/._answer.md": "macOS resource fork metadata",
        }
    )

    install_result = installer.install_zip(bundle)

    assert install_result["package_id"] == "pkg.macos"


def test_bundle_install_rejects_unsafe_zip_path(workspace_tmp: Path) -> None:
    installer = PackageInstaller(workspace_tmp / "installed", temp_dir=workspace_tmp)
    unsafe_zip = make_zip(
        {
            "manifest.json": manifest(),
            "../escape.json": {"name": "escape"},
            "plugins/lookup.json": plugin_contract(),
            "skills/lookup.json": skill_contract(),
            "prompts/answer.md": "prompt",
        }
    )

    with pytest.raises(PackageInstallError, match="Unsafe path"):
        installer.install_zip(unsafe_zip)


def test_loader_installed_bundle_wins_over_catalog_manifest(workspace_tmp: Path) -> None:
    catalog_dir = workspace_tmp / "catalog"
    installed_dir = workspace_tmp / "installed"
    catalog_dir.mkdir()
    installer = PackageInstaller(installed_dir, temp_dir=workspace_tmp)
    (catalog_dir / "pkg.pipeline.json").write_text(
        json.dumps(
            {
                **manifest(package_id="pkg.pipeline", version="0.9.0"),
                "provides": {},
                "status": "灰度中",
                "plugins": [
                    plugin_contract(capability_name="pkg.pipeline.catalog_only"),
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    installer.install_zip(bundle_zip(package_id="pkg.pipeline", version="1.0.0"))
    loader = PackageLoader(catalog_dir=catalog_dir, installed_dir=installed_dir)
    packages = loader.list_packages()
    registry = CapabilityRegistry(loader=loader)

    assert len([item for item in packages if item["package_id"] == "pkg.pipeline"]) == 1
    assert packages[0]["version"] == "1.0.0"
    assert packages[0]["status"] == "运行中"
    assert registry.get("pkg.pipeline.lookup").package_id == "pkg.pipeline"
    with pytest.raises(KeyError):
        registry.get("pkg.pipeline.catalog_only")


def test_registry_does_not_allow_bundle_to_shadow_builtin_capability(workspace_tmp: Path) -> None:
    installed_dir = workspace_tmp / "installed"
    catalog_dir = workspace_tmp / "catalog"
    catalog_dir.mkdir()
    installer = PackageInstaller(installed_dir, temp_dir=workspace_tmp)
    installer.install_zip(
        make_zip(
            {
                "manifest.json": manifest(package_id="pkg.shadow"),
                "plugins/lookup.json": plugin_contract(capability_name="knowledge.search"),
                "skills/lookup.json": skill_contract(capability_name="knowledge.search"),
                "prompts/answer.md": "prompt",
            }
        )
    )

    registry = CapabilityRegistry(loader=PackageLoader(catalog_dir=catalog_dir, installed_dir=installed_dir))

    capability = registry.get("knowledge.search")
    assert capability.source == "_platform"
    assert capability.package_id is None
