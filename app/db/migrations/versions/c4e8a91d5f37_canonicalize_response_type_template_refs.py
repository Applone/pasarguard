"""canonicalize subscription rule response types

Normalizes `rules[].responseType` in the subscription settings blob:

* legacy ConfigFormat spellings ("links_base64", "clash_meta", ...) become their
  canonical built-in token ("XRAY_BASE64", "MIHOMO", ...)
* built-in tokens written in mixed case are upper-cased
* a response type naming a Client Template is rewritten to "TEMPLATE:<id>" so that
  renaming the template in the panel no longer breaks the rule
* rule names are clamped to the 50 character bound the models now enforce

`responseModifications.subscriptionTemplate` is deliberately left as a template *name*:
that is the reference spec's contract for the field, and the runtime resolver already
accepts either a name or an id there.

Revision ID: c4e8a91d5f37
Revises: 8d1e2f3a4b5c
Create Date: 2026-09-13 12:00:00.000000

"""

import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4e8a91d5f37"
down_revision = "8d1e2f3a4b5c"
branch_labels = None
depends_on = None

BUILTIN_RESPONSE_TYPES = {
    "MIHOMO",
    "CLASH",
    "STASH",
    "SINGBOX",
    "XRAY_JSON",
    "XRAY_BASE64",
    "LINKS",
    "WIREGUARD",
    "OUTLINE",
    "BROWSER",
    "BLOCK",
    "STATUS_CODE_404",
    "STATUS_CODE_451",
    "SOCKET_DROP",
}

CONFIG_FORMAT_TO_RESPONSE_TYPE = {
    "clash_meta": "MIHOMO",
    "clash": "CLASH",
    "sing_box": "SINGBOX",
    "xray": "XRAY_JSON",
    "links_base64": "XRAY_BASE64",
    "links": "LINKS",
    "wireguard": "WIREGUARD",
    "outline": "OUTLINE",
    "block": "BLOCK",
}

RESPONSE_TEMPLATE_PREFIX = "TEMPLATE:"

RESPONSE_TEMPLATE_TYPE_ORDER = ("xray_subscription", "singbox_subscription", "clash_subscription")


def _load_response_templates(connection) -> tuple[dict[str, int], set[int]]:
    """Return a name -> id map (deterministic on collision) and the set of valid ids."""
    try:
        rows = connection.execute(
            sa.text("SELECT id, name, template_type FROM client_templates ORDER BY id ASC")
        ).fetchall()
    except Exception:
        return {}, set()

    order = {t: i for i, t in enumerate(RESPONSE_TEMPLATE_TYPE_ORDER)}
    usable = [row for row in rows if row[2] in order]
    usable.sort(key=lambda row: (order[row[2]], row[0]))

    by_name: dict[str, int] = {}
    ids: set[int] = set()
    for template_id, name, _ in usable:
        ids.add(template_id)
        key = str(name).strip().lower()
        # First match wins, following the same deterministic type ordering the
        # runtime resolver uses.
        by_name.setdefault(key, template_id)
    return by_name, ids


def _canonicalize_response_type(value, by_name: dict[str, int], ids: set[int]) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{RESPONSE_TEMPLATE_PREFIX}{value}" if value in ids else None
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    upper = raw.upper()
    if upper in BUILTIN_RESPONSE_TYPES:
        return upper
    if raw.lower() in CONFIG_FORMAT_TO_RESPONSE_TYPE:
        return CONFIG_FORMAT_TO_RESPONSE_TYPE[raw.lower()]

    reference = raw[len(RESPONSE_TEMPLATE_PREFIX) :].strip() if upper.startswith(RESPONSE_TEMPLATE_PREFIX) else raw
    if not reference:
        return None
    if reference.isdigit():
        return f"{RESPONSE_TEMPLATE_PREFIX}{int(reference)}" if int(reference) in ids else None

    template_id = by_name.get(reference.lower())
    return f"{RESPONSE_TEMPLATE_PREFIX}{template_id}" if template_id is not None else None


def _rewrite_rules(rules, by_name, ids) -> bool:
    changed = False
    for rule in rules:
        if not isinstance(rule, dict):
            continue

        name = rule.get("name")
        if isinstance(name, str) and len(name) > 50:
            rule["name"] = name[:50]
            changed = True

        current = rule.get("responseType", rule.get("response_type"))
        canonical = _canonicalize_response_type(current, by_name, ids)
        # Unresolvable values are left untouched: the panel surfaces them as a missing
        # template and rejects them on the next save, which is preferable to silently
        # swapping in a different response type.
        if canonical is not None and canonical != current:
            rule["responseType"] = canonical
            rule.pop("response_type", None)
            changed = True
    return changed


def _iter_settings(connection):
    rows = connection.execute(sa.text("SELECT id, subscription FROM settings")).fetchall()
    for row in rows:
        settings_id, raw_sub = row[0], row[1]
        if raw_sub is None:
            continue
        sub_data = json.loads(raw_sub) if isinstance(raw_sub, str) else dict(raw_sub)
        if not isinstance(sub_data, dict):
            continue
        yield settings_id, sub_data


def upgrade() -> None:
    connection = op.get_bind()
    by_name, ids = _load_response_templates(connection)

    for settings_id, sub_data in _iter_settings(connection):
        rules = sub_data.get("rules")
        if not isinstance(rules, list) or not rules:
            continue
        if not _rewrite_rules(rules, by_name, ids):
            continue
        sub_data["rules"] = rules
        connection.execute(
            sa.text("UPDATE settings SET subscription = :sub WHERE id = :id"),
            {"sub": json.dumps(sub_data), "id": settings_id},
        )


def downgrade() -> None:
    """
    Expand TEMPLATE:<id> references back to the template name.

    Built-in tokens are already valid in the previous revision, so only template
    references need rewriting.
    """
    connection = op.get_bind()
    try:
        rows = connection.execute(sa.text("SELECT id, name FROM client_templates")).fetchall()
    except Exception:
        rows = []
    by_id = {row[0]: row[1] for row in rows}

    for settings_id, sub_data in _iter_settings(connection):
        rules = sub_data.get("rules")
        if not isinstance(rules, list) or not rules:
            continue

        changed = False
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            current = rule.get("responseType")
            if not isinstance(current, str) or not current.upper().startswith(RESPONSE_TEMPLATE_PREFIX):
                continue
            reference = current[len(RESPONSE_TEMPLATE_PREFIX) :].strip()
            if not reference.isdigit():
                continue
            name = by_id.get(int(reference))
            rule["responseType"] = name if name else "XRAY_BASE64"
            changed = True

        if changed:
            sub_data["rules"] = rules
            connection.execute(
                sa.text("UPDATE settings SET subscription = :sub WHERE id = :id"),
                {"sub": json.dumps(sub_data), "id": settings_id},
            )
