"""migrate subscription rules to Remnawave SSR format

Revision ID: 8d1e2f3a4b5c
Revises: 7c4bd5128e62
Create Date: 2026-09-02 23:59:00.000000

"""

import json
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "8d1e2f3a4b5c"
down_revision = "7c4bd5128e62"
branch_labels = None
depends_on = None

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

RESPONSE_TYPE_TO_CONFIG_FORMAT = {
    "MIHOMO": "clash_meta",
    "CLASH": "clash",
    "STASH": "clash",
    "SINGBOX": "sing_box",
    "XRAY_JSON": "xray",
    "XRAY_BASE64": "links_base64",
    "LINKS": "links",
    "WIREGUARD": "wireguard",
    "OUTLINE": "outline",
    "BLOCK": "block",
}


def _upgrade_rule(rule: dict) -> dict:
    if "conditions" in rule and "responseType" in rule:
        return rule

    pattern = rule.get("pattern", ".*")
    target = rule.get("target", "links_base64")
    response_headers = rule.get("response_headers") or {}

    header_list = []
    if isinstance(response_headers, dict):
        for k, v in response_headers.items():
            header_list.append({"key": str(k), "value": v})
    elif isinstance(response_headers, list):
        header_list = response_headers

    resp_type = CONFIG_FORMAT_TO_RESPONSE_TYPE.get(target, "XRAY_BASE64")

    conditions = []
    if pattern and pattern != ".*":
        conditions.append(
            {
                "headerName": "user-agent",
                "operator": "REGEX",
                "value": pattern,
                "caseSensitive": True,
            }
        )

    return {
        "name": rule.get("name") or (f"Rule for {target}" if target else "Subscription Rule"),
        "description": rule.get("description") or "",
        "enabled": rule.get("enabled", True),
        "operator": "AND",
        "conditions": conditions,
        "responseType": resp_type,
        "responseModifications": {
            "subscriptionTemplate": None,
            "headers": header_list,
            "applyHeadersToEnd": False,
            "ignoreHostXrayJsonTemplate": False,
            "ignoreServeJsonAtBaseSubscription": False,
            "disableHwidCheck": False,
        },
    }


def _downgrade_rule(rule: dict) -> dict:
    resp_type = rule.get("responseType", "XRAY_BASE64")
    target = RESPONSE_TYPE_TO_CONFIG_FORMAT.get(resp_type, "links_base64")

    pattern = ".*"
    for cond in rule.get("conditions", []):
        if cond.get("headerName", "").lower() == "user-agent" and cond.get("operator") == "REGEX":
            pattern = cond.get("value", ".*")
            break

    modifications = rule.get("responseModifications") or {}
    raw_headers = modifications.get("headers") or []
    headers_dict = {}
    if isinstance(raw_headers, list):
        for item in raw_headers:
            if isinstance(item, dict) and "key" in item:
                headers_dict[item["key"]] = item.get("value", "")
    elif isinstance(raw_headers, dict):
        headers_dict = raw_headers

    return {
        "pattern": pattern,
        "target": target,
        "response_headers": headers_dict,
    }


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, subscription FROM settings")).fetchall()

    for row in rows:
        settings_id = row[0]
        raw_sub = row[1]
        if raw_sub is None:
            continue

        sub_data = json.loads(raw_sub) if isinstance(raw_sub, str) else dict(raw_sub)
        rules = sub_data.get("rules", [])
        if rules:
            new_rules = [_upgrade_rule(r) for r in rules]
            sub_data["rules"] = new_rules
            new_val = json.dumps(sub_data) if isinstance(raw_sub, str) else sub_data
            connection.execute(
                sa.text("UPDATE settings SET subscription = :sub WHERE id = :id"),
                {"sub": new_val if isinstance(raw_sub, str) else json.dumps(sub_data), "id": settings_id},
            )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, subscription FROM settings")).fetchall()

    for row in rows:
        settings_id = row[0]
        raw_sub = row[1]
        if raw_sub is None:
            continue

        sub_data = json.loads(raw_sub) if isinstance(raw_sub, str) else dict(raw_sub)
        rules = sub_data.get("rules", [])
        if rules:
            old_rules = [_downgrade_rule(r) for r in rules]
            sub_data["rules"] = old_rules
            connection.execute(
                sa.text("UPDATE settings SET subscription = :sub WHERE id = :id"),
                {"sub": json.dumps(sub_data), "id": settings_id},
            )
