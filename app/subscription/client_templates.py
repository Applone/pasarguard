from aiocache import cached

from app.db import GetDB
from app.db.crud.client_template import (
    get_all_client_templates_map,
    get_client_template_contents_by_type,
    get_client_template_values,
)
from app.models.client_template import ClientTemplateType


@cached()
async def subscription_client_templates() -> dict[str, str]:
    async with GetDB() as db:
        return await get_client_template_values(db)


@cached()
async def subscription_xray_templates() -> dict[int, str]:
    async with GetDB() as db:
        return await get_client_template_contents_by_type(db, ClientTemplateType.xray_subscription)


@cached()
async def subscription_templates_lookup() -> dict[str, dict[str, str]]:
    async with GetDB() as db:
        return await get_all_client_templates_map(db)


async def resolve_client_template_content(
    template_type: ClientTemplateType | str,
    identifier: str | int | None,
) -> str | None:
    if not identifier:
        return None
    type_str = template_type.value if isinstance(template_type, ClientTemplateType) else str(template_type)
    templates_map = await subscription_templates_lookup()
    type_map = templates_map.get(type_str, {})
    ident_str = str(identifier).strip()
    if ident_str in type_map.get("by_id", {}):
        return type_map["by_id"][ident_str]
    if ident_str.lower() in type_map.get("by_name", {}):
        return type_map["by_name"][ident_str.lower()]
    return None


async def refresh_client_templates_cache() -> None:
    await subscription_client_templates.cache.clear()
    await subscription_xray_templates.cache.clear()
    await subscription_templates_lookup.cache.clear()


async def handle_client_template_message(_: dict) -> None:
    """Handle client template update messages from NATS router."""
    await refresh_client_templates_cache()
