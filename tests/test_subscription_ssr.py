from unittest.mock import AsyncMock, patch

import pytest

from app.models.client_template import ClientTemplateType
from app.models.settings import (
    ConditionOperator,
    ConfigFormat,
    ResponseHeaderItem,
    ResponseModifications,
    ResponseType,
    RuleCondition,
    RuleOperator,
    SubRule,
)
from app.operation.subscription import (
    SubscriptionOperation,
    evaluate_condition,
    extract_request_headers,
    match_rule,
)


def test_extract_request_headers():
    # Test dictionary input
    headers = {"User-Agent": "Happ/1.0", "X-Device-OS": "Android"}
    extracted = extract_request_headers(headers)
    assert extracted["user-agent"] == "Happ/1.0"
    assert extracted["x-device-os"] == "Android"

    # Test string input
    extracted = extract_request_headers("MyUserAgent/1.0")
    assert extracted["user-agent"] == "MyUserAgent/1.0"


def test_evaluate_condition_operators():
    headers = {
        "user-agent": "Happ/2.5.0 (Android 14; Pixel 8)",
        "x-device-os": "android",
        "x-hwid": "device-uuid-12345",
    }

    # EQUALS & NOT_EQUALS (case-insensitive by default)
    c_eq = RuleCondition(headerName="x-device-os", operator=ConditionOperator.EQUALS, value="Android")
    assert evaluate_condition(c_eq, headers) is True

    c_neq = RuleCondition(headerName="x-device-os", operator=ConditionOperator.NOT_EQUALS, value="iOS")
    assert evaluate_condition(c_neq, headers) is True

    # Case-sensitive check
    c_eq_cs = RuleCondition(
        headerName="x-device-os", operator=ConditionOperator.EQUALS, value="Android", caseSensitive=True
    )
    assert evaluate_condition(c_eq_cs, headers) is False

    # CONTAINS & NOT_CONTAINS
    c_contains = RuleCondition(headerName="user-agent", operator=ConditionOperator.CONTAINS, value="happ")
    assert evaluate_condition(c_contains, headers) is True

    c_not_contains = RuleCondition(headerName="user-agent", operator=ConditionOperator.NOT_CONTAINS, value="iphone")
    assert evaluate_condition(c_not_contains, headers) is True

    # STARTS_WITH & NOT_STARTS_WITH
    c_starts = RuleCondition(headerName="user-agent", operator=ConditionOperator.STARTS_WITH, value="happ/")
    assert evaluate_condition(c_starts, headers) is True

    c_not_starts = RuleCondition(headerName="user-agent", operator=ConditionOperator.NOT_STARTS_WITH, value="v2ray")
    assert evaluate_condition(c_not_starts, headers) is True

    # ENDS_WITH & NOT_ENDS_WITH
    c_ends = RuleCondition(headerName="x-hwid", operator=ConditionOperator.ENDS_WITH, value="12345")
    assert evaluate_condition(c_ends, headers) is True

    c_not_ends = RuleCondition(headerName="x-hwid", operator=ConditionOperator.NOT_ENDS_WITH, value="999")
    assert evaluate_condition(c_not_ends, headers) is True

    # REGEX & NOT_REGEX
    c_regex = RuleCondition(headerName="user-agent", operator=ConditionOperator.REGEX, value=r"Pixel\s+\d+")
    assert evaluate_condition(c_regex, headers) is True

    c_not_regex = RuleCondition(headerName="user-agent", operator=ConditionOperator.NOT_REGEX, value=r"iPhone\s+\d+")
    assert evaluate_condition(c_not_regex, headers) is True


def test_missing_header_skips_rule():
    headers = {"user-agent": "test"}
    # Missing header results in condition evaluating to False
    cond = RuleCondition(headerName="x-missing-header", operator=ConditionOperator.EQUALS, value="val")
    assert evaluate_condition(cond, headers) is False

    cond_neq = RuleCondition(headerName="x-missing-header", operator=ConditionOperator.NOT_EQUALS, value="val")
    assert evaluate_condition(cond_neq, headers) is False


def test_rule_matching_and_or():
    headers = {
        "user-agent": "Happ/1.0",
        "x-device-os": "android",
    }

    cond1 = RuleCondition(headerName="user-agent", operator=ConditionOperator.CONTAINS, value="happ")
    cond2 = RuleCondition(headerName="x-device-os", operator=ConditionOperator.EQUALS, value="android")
    cond3 = RuleCondition(headerName="x-device-os", operator=ConditionOperator.EQUALS, value="ios")

    # AND operator: all conditions match
    rule_and = SubRule(
        name="Happ Android",
        enabled=True,
        operator=RuleOperator.AND,
        conditions=[cond1, cond2],
        responseType=ResponseType.XRAY_JSON,
    )
    assert match_rule(rule_and, headers) is True

    # AND operator: one fails -> rule fails
    rule_and_fail = SubRule(
        name="Happ iOS",
        enabled=True,
        operator=RuleOperator.AND,
        conditions=[cond1, cond3],
        responseType=ResponseType.XRAY_JSON,
    )
    assert match_rule(rule_and_fail, headers) is False

    # OR operator: one matches -> rule matches
    rule_or = SubRule(
        name="Happ Any",
        enabled=True,
        operator=RuleOperator.OR,
        conditions=[cond1, cond3],
        responseType=ResponseType.XRAY_JSON,
    )
    assert match_rule(rule_or, headers) is True

    # Disabled rule never matches
    rule_disabled = SubRule(
        name="Happ Disabled",
        enabled=False,
        operator=RuleOperator.AND,
        conditions=[cond1, cond2],
        responseType=ResponseType.XRAY_JSON,
    )
    assert match_rule(rule_disabled, headers) is False

    # Empty conditions (catch-all) matches everything
    rule_catchall = SubRule(
        name="Fallback",
        enabled=True,
        operator=RuleOperator.AND,
        conditions=[],
        responseType=ResponseType.XRAY_BASE64,
    )
    assert match_rule(rule_catchall, headers) is True


def test_detect_client_rule_order():
    rule_happ_android = SubRule(
        name="Happ Android",
        enabled=True,
        operator=RuleOperator.AND,
        conditions=[
            RuleCondition(headerName="user-agent", operator=ConditionOperator.CONTAINS, value="happ"),
            RuleCondition(headerName="x-device-os", operator=ConditionOperator.EQUALS, value="android"),
        ],
        responseType=ResponseType.XRAY_JSON,
        responseModifications=ResponseModifications(
            subscriptionTemplate="Happ Android Template",
            headers=[ResponseHeaderItem(key="x-provider-id", value="HappTheBestAppOnTheWorld")],
        ),
    )

    rule_happ_ios = SubRule(
        name="Happ iOS",
        enabled=True,
        operator=RuleOperator.AND,
        conditions=[
            RuleCondition(headerName="user-agent", operator=ConditionOperator.CONTAINS, value="happ"),
            RuleCondition(headerName="x-device-os", operator=ConditionOperator.EQUALS, value="ios"),
        ],
        responseType=ResponseType.XRAY_JSON,
        responseModifications=ResponseModifications(
            subscriptionTemplate="Happ iOS Template",
        ),
    )

    rule_fallback = SubRule(
        name="Fallback",
        enabled=True,
        operator=RuleOperator.AND,
        conditions=[],
        responseType=ResponseType.XRAY_BASE64,
    )

    rules = [rule_happ_android, rule_happ_ios, rule_fallback]

    # Test Android client matching
    android_headers = {"user-agent": "Happ/2.0", "x-device-os": "android"}
    matched = SubscriptionOperation.detect_client_rule(android_headers, rules)
    assert matched is not None
    assert matched.name == "Happ Android"
    assert matched.response_modifications.subscription_template == "Happ Android Template"

    # Test iOS client matching
    ios_headers = {"user-agent": "Happ/2.0", "x-device-os": "ios"}
    matched = SubscriptionOperation.detect_client_rule(ios_headers, rules)
    assert matched is not None
    assert matched.name == "Happ iOS"
    assert matched.response_modifications.subscription_template == "Happ iOS Template"

    # Test other client falling through to fallback
    other_headers = {"user-agent": "curl/8.0"}
    matched = SubscriptionOperation.detect_client_rule(other_headers, rules)
    assert matched is not None
    assert matched.name == "Fallback"
    assert matched.response_type == ResponseType.XRAY_BASE64


def test_legacy_sub_rule_compatibility():
    legacy_data = {
        "pattern": r"^LegacyClient$",
        "target": "sing_box",
        "response_headers": {"X-Custom": "Value"},
    }
    rule = SubRule.model_validate(legacy_data)
    assert rule.response_type == ResponseType.SINGBOX
    assert rule.target == ConfigFormat.sing_box
    assert rule.pattern == r"^LegacyClient$"
    assert rule.response_headers == {"X-Custom": "Value"}
    assert len(rule.conditions) == 1
    assert rule.conditions[0].header_name == "user-agent"
    assert rule.conditions[0].operator == ConditionOperator.REGEX
    assert rule.conditions[0].value == r"^LegacyClient$"


@pytest.mark.asyncio
async def test_resolve_client_template_content():
    from app.subscription.client_templates import resolve_client_template_content

    with patch(
        "app.subscription.client_templates.subscription_templates_lookup", new_callable=AsyncMock
    ) as mock_lookup:
        mock_lookup.return_value = {
            "xray_subscription": {
                "by_name": {"happ android": '{"log": {"loglevel": "debug"}}'},
                "by_id": {"10": '{"log": {"loglevel": "debug"}}'},
            }
        }

        # By name (case-insensitive)
        content = await resolve_client_template_content(ClientTemplateType.xray_subscription, "Happ Android")
        assert content == '{"log": {"loglevel": "debug"}}'

        # By ID
        content_id = await resolve_client_template_content(ClientTemplateType.xray_subscription, "10")
        assert content_id == '{"log": {"loglevel": "debug"}}'

        # Missing
        content_none = await resolve_client_template_content(ClientTemplateType.xray_subscription, "NonExistent")
        assert content_none is None


def test_format_rule_response_headers_list_and_dict():
    # List of ResponseHeaderItem
    rule = SubRule(
        name="Header Test",
        enabled=True,
        conditions=[],
        responseType=ResponseType.LINKS,
        responseModifications=ResponseModifications(
            headers=[
                ResponseHeaderItem(key="X-Provider", value="MyProvider"),
                ResponseHeaderItem(key="X-User", value="{USERNAME}"),
            ]
        ),
    )
    headers = SubscriptionOperation._format_rule_response_headers(rule, {"USERNAME": "bob"})
    assert headers["X-Provider"] == "MyProvider"
    assert headers["X-User"] == "bob"

    # Dict of headers (backward compatibility)
    rule_dict = SubRule(
        name="Header Dict Test",
        enabled=True,
        conditions=[],
        responseType=ResponseType.LINKS,
        responseModifications=ResponseModifications(headers={"X-Provider": "MyProvider", "X-User": "{USERNAME}"}),
    )
    headers_dict = SubscriptionOperation._format_rule_response_headers(rule_dict, {"USERNAME": "alice"})
    assert headers_dict["X-Provider"] == "MyProvider"
    assert headers_dict["X-User"] == "alice"


# --- Response types backed by Client Templates -------------------------------------


def test_builtin_response_type_normalization():
    """Built-in tokens, legacy ConfigFormat names and ConfigFormat members all canonicalize."""
    assert SubRule(responseType="xray_json").response_type == "XRAY_JSON"
    assert SubRule(responseType="  singbox ").response_type == "SINGBOX"
    assert SubRule(responseType="links_base64").response_type == "XRAY_BASE64"
    assert SubRule(responseType="clash_meta").response_type == "MIHOMO"
    assert SubRule(responseType=ConfigFormat.wireguard).response_type == "WIREGUARD"
    assert SubRule(responseType=ResponseType.SOCKET_DROP).response_type == "SOCKET_DROP"
    # An empty value falls back to the default rather than producing an invalid rule.
    assert SubRule(responseType="").response_type == "XRAY_BASE64"

    for rule in (SubRule(responseType="XRAY_JSON"), SubRule(responseType="block")):
        assert rule.is_builtin_response is True
        assert rule.template_reference is None


def test_template_response_type_references():
    """Any Client Template is a valid response type, in canonical or bare form."""
    canonical = SubRule(responseType="TEMPLATE:7")
    assert canonical.response_type == "TEMPLATE:7"
    assert canonical.is_builtin_response is False
    assert canonical.template_reference == "7"

    # A bare numeric id is canonicalized.
    assert SubRule(responseType="7").response_type == "TEMPLATE:7"
    assert SubRule(responseType=7).response_type == "TEMPLATE:7"

    # A bare name is preserved verbatim for name-based resolution.
    by_name = SubRule(responseType="Happ Android")
    assert by_name.response_type == "Happ Android"
    assert by_name.is_builtin_response is False
    assert by_name.template_reference == "Happ Android"

    # A template whose name collides with a built-in cannot shadow it.
    assert SubRule(responseType="CLASH").template_reference is None
    assert SubRule(responseType="TEMPLATE:CLASH").template_reference == "CLASH"


def test_rule_name_is_clamped_not_rejected():
    """Over-long stored names must not make the settings blob unloadable."""
    rule = SubRule(name="x" * 80, responseType="LINKS")
    assert len(rule.name) == 50


@pytest.mark.asyncio
async def test_resolve_rule_response_status_types():
    from app.operation.subscription import resolve_rule_response

    expected = {
        "BLOCK": (403, "Forbidden"),
        "STATUS_CODE_404": (404, "Not Found"),
        "STATUS_CODE_451": (451, "Unavailable For Legal Reasons"),
    }
    for resp_type, (code, body) in expected.items():
        resolved = await resolve_rule_response(SubRule(responseType=resp_type))
        assert resolved.kind == "status"
        assert resolved.status_code == code
        assert resolved.body == body

    resolved = await resolve_rule_response(SubRule(responseType="SOCKET_DROP"))
    assert resolved.kind == "socket_drop"

    resolved = await resolve_rule_response(SubRule(responseType="BROWSER"))
    assert resolved.kind == "page"


@pytest.mark.asyncio
async def test_resolve_rule_response_builtin_config():
    from app.operation.subscription import resolve_rule_response

    resolved = await resolve_rule_response(SubRule(responseType="SINGBOX"))
    assert resolved.kind == "config"
    assert resolved.client_type == ConfigFormat.sing_box
    assert resolved.template_content is None


@pytest.mark.asyncio
async def test_resolve_rule_response_template_backed():
    """A template-backed response type derives its format from the template type."""
    from app.operation.subscription import resolve_rule_response
    from app.subscription.client_templates import ResolvedResponseTemplate

    cases = {
        "xray_subscription": ConfigFormat.xray,
        "singbox_subscription": ConfigFormat.sing_box,
        "clash_subscription": ConfigFormat.clash,
    }
    for template_type, expected_format in cases.items():
        template = ResolvedResponseTemplate(id=3, name="Custom", template_type=template_type, content="RENDERED")
        with patch("app.operation.subscription.resolve_response_template", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = template
            resolved = await resolve_rule_response(SubRule(responseType="TEMPLATE:3"))

        assert resolved.kind == "config"
        assert resolved.client_type == expected_format
        assert resolved.template_content == "RENDERED"


@pytest.mark.asyncio
async def test_resolve_rule_response_missing_template_fails_closed():
    """A deleted or renamed template must not silently fall back to another format."""
    from app.operation.subscription import resolve_rule_response

    with patch("app.operation.subscription.resolve_response_template", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None
        resolved = await resolve_rule_response(SubRule(responseType="TEMPLATE:404"))

    assert resolved.kind == "unsupported"
    assert resolved.client_type is None


@pytest.mark.asyncio
async def test_subscription_template_override_beats_response_type_template():
    from app.operation.subscription import resolve_rule_response
    from app.subscription.client_templates import ResolvedResponseTemplate

    template = ResolvedResponseTemplate(
        id=3, name="Custom", template_type="xray_subscription", content="FROM_RESPONSE_TYPE"
    )
    rule = SubRule(
        responseType="TEMPLATE:3",
        responseModifications=ResponseModifications(subscriptionTemplate="Override"),
    )

    with (
        patch("app.operation.subscription.resolve_response_template", new_callable=AsyncMock) as mock_resolve,
        patch("app.operation.subscription.resolve_client_template_content", new_callable=AsyncMock) as mock_override,
    ):
        mock_resolve.return_value = template
        mock_override.return_value = "FROM_OVERRIDE"
        resolved = await resolve_rule_response(rule)

    assert resolved.client_type == ConfigFormat.xray
    assert resolved.template_content == "FROM_OVERRIDE"


@pytest.mark.asyncio
async def test_resolve_response_template_by_id_and_name():
    from app.subscription.client_templates import resolve_response_template

    rows = [
        {"id": 1, "name": "Xray Default", "template_type": "xray_subscription", "content": "X", "is_default": True},
        {"id": 2, "name": "Happ Android", "template_type": "clash_subscription", "content": "C", "is_default": False},
    ]
    with patch("app.subscription.client_templates.response_templates", new_callable=AsyncMock) as mock_rows:
        mock_rows.return_value = rows

        by_id = await resolve_response_template("2")
        assert by_id is not None and by_id.name == "Happ Android"
        assert by_id.content == "C"

        by_name = await resolve_response_template("happ android")
        assert by_name is not None and by_name.id == 2

        assert await resolve_response_template("nope") is None
        assert await resolve_response_template("99") is None
        assert await resolve_response_template(None) is None
        assert await resolve_response_template("  ") is None


# --- Migration: canonicalizing stored response types --------------------------------


def _load_canonicalize_migration():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "app/db/migrations/versions/c4e8a91d5f37_canonicalize_response_type_template_refs.py"
    )
    spec = importlib.util.spec_from_file_location("srr_canonicalize_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_canonicalizes_response_types():
    migration = _load_canonicalize_migration()
    by_name = {"happ android": 4, "xray default": 1}
    ids = {1, 4}

    canon = migration._canonicalize_response_type
    # Built-ins and legacy config-format spellings
    assert canon("links_base64", by_name, ids) == "XRAY_BASE64"
    assert canon("clash_meta", by_name, ids) == "MIHOMO"
    assert canon("xray_json", by_name, ids) == "XRAY_JSON"
    assert canon("SOCKET_DROP", by_name, ids) == "SOCKET_DROP"
    # Template references
    assert canon("Happ Android", by_name, ids) == "TEMPLATE:4"
    assert canon("TEMPLATE:4", by_name, ids) == "TEMPLATE:4"
    assert canon("4", by_name, ids) == "TEMPLATE:4"
    assert canon(4, by_name, ids) == "TEMPLATE:4"
    # Unresolvable values are reported as such so the caller can leave them untouched
    assert canon("Deleted Template", by_name, ids) is None
    assert canon("99", by_name, ids) is None
    assert canon("", by_name, ids) is None


def test_migration_rewrite_rules_leaves_unresolvable_alone():
    migration = _load_canonicalize_migration()
    rules = [
        {"name": "a", "responseType": "links_base64"},
        {"name": "b", "responseType": "Happ Android"},
        {"name": "c", "responseType": "Ghost Template"},
        {"name": "d" * 80, "responseType": "CLASH"},
    ]
    changed = migration._rewrite_rules(rules, {"happ android": 4}, {4})

    assert changed is True
    assert rules[0]["responseType"] == "XRAY_BASE64"
    assert rules[1]["responseType"] == "TEMPLATE:4"
    assert rules[2]["responseType"] == "Ghost Template"
    assert len(rules[3]["name"]) == 50

    # Idempotent: a second pass changes nothing.
    assert migration._rewrite_rules(rules, {"happ android": 4}, {4}) is False
