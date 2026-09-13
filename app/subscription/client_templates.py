from dataclasses import dataclass

from aiocache import cached

from app.db import GetDB
from app.db.crud.client_template import (
    get_all_client_templates_map,
    get_client_template_contents_by_type,
    get_client_template_values,
    get_response_templates,
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


@cached()
async def response_templates() -> list[dict]:
    """Every client template that is selectable as a subscription response type."""
    async with GetDB() as db:
        return await get_response_templates(db)


@dataclass(slots=True, frozen=True)
class ResolvedResponseTemplate:
    id: int
    name: str
    template_type: str
    content: str


async def resolve_response_template(reference: str | int | None) -> ResolvedResponseTemplate | None:
    """
    Resolve a response-type template reference to the backing template.

    A reference may be a numeric id (canonical, survives renames) or a template name
    (accepted for hand-written API payloads and legacy data). Name lookups are
    case-insensitive and resolve against the deterministic ordering from
    `get_response_templates`, so the same name always resolves to the same template.
    """
    if reference is None:
        return None

    ref = str(reference).strip()
    if not ref:
        return None

    templates = await response_templates()
    if not templates:
        return None

    if ref.isdigit():
        ref_id = int(ref)
        for template in templates:
            if template["id"] == ref_id:
                return ResolvedResponseTemplate(
                    id=template["id"],
                    name=template["name"],
                    template_type=template["template_type"],
                    content=template["content"],
                )
        return None

    ref_lower = ref.lower()
    for template in templates:
        if template["name"].lower() == ref_lower:
            return ResolvedResponseTemplate(
                id=template["id"],
                name=template["name"],
                template_type=template["template_type"],
                content=template["content"],
            )
    return None


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
    await response_templates.cache.clear()


async def handle_client_template_message(_: dict) -> None:
    """Handle client template update messages from NATS router."""
    await refresh_client_templates_cache()
