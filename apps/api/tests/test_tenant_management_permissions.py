import asyncio

import pytest

from agent_platform.domain.models import TenantProfile, UserContext
from agent_platform.runtime.chat_service import ChatService


class FakeUsers:
    def __init__(self, scopes: list[str]) -> None:
        self.scopes = scopes

    async def get(self, tenant_id: str, user_id: str) -> UserContext:
        return UserContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role="platform_admin",
            scopes=self.scopes,
            email="admin@example.com",
        )


class FakeTenants:
    def __init__(self) -> None:
        self.items = [
            TenantProfile(
                tenant_id="tenant-default",
                name="默认租户",
                package="通用业务包",
                environment="生产",
                budget="100k",
            )
        ]

    async def list_all(self) -> list[TenantProfile]:
        return list(self.items)

    async def create(self, tenant: TenantProfile) -> TenantProfile:
        self.items.append(tenant)
        return tenant

    async def update(self, tenant: TenantProfile) -> TenantProfile:
        self.items = [tenant if item.tenant_id == tenant.tenant_id else item for item in self.items]
        return tenant

    async def delete(self, tenant_id: str) -> bool:
        before = len(self.items)
        self.items = [item for item in self.items if item.tenant_id != tenant_id]
        return len(self.items) < before


def build_service(scopes: list[str]) -> ChatService:
    service = ChatService.__new__(ChatService)
    service._users = FakeUsers(scopes)
    service._tenants = FakeTenants()
    return service


def test_list_tenants_requires_tenant_management_scope() -> None:
    service = build_service(scopes=["admin:read"])

    with pytest.raises(PermissionError, match="tenant:manage"):
        asyncio.run(service.list_tenants(tenant_id="tenant-default", user_id="user-admin"))


def test_tenant_crud_requires_tenant_management_scope() -> None:
    service = build_service(scopes=["admin:read"])

    with pytest.raises(PermissionError, match="tenant:manage"):
        asyncio.run(
            service.create_tenant(
                name="新租户",
                package="通用业务包",
                environment="生产",
                budget="100k",
                tenant_id="tenant-default",
                user_id="user-admin",
            )
        )

    with pytest.raises(PermissionError, match="tenant:manage"):
        asyncio.run(
            service.update_tenant(
                tenant_id="tenant-default",
                name="默认租户",
                package="通用业务包",
                environment="生产",
                budget="100k",
                active=True,
                auth_tenant_id="tenant-default",
                user_id="user-admin",
            )
        )

    with pytest.raises(PermissionError, match="tenant:manage"):
        asyncio.run(
            service.delete_tenant(
                "tenant-default",
                auth_tenant_id="tenant-default",
                user_id="user-admin",
            )
        )


def test_tenant_management_scope_allows_listing_and_creating_tenants() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])

    tenants = asyncio.run(service.list_tenants(tenant_id="tenant-default", user_id="user-admin"))
    created = asyncio.run(
        service.create_tenant(
            name="新租户",
            package="通用业务包",
            environment="生产",
            budget="100k",
            tenant_id="tenant-default",
            user_id="user-admin",
        )
    )

    assert [tenant.tenant_id for tenant in tenants] == ["tenant-default"]
    assert created.name == "新租户"
