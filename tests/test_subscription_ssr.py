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
