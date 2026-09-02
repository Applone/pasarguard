import re
from enum import Enum, StrEnum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.models.proxy import ShadowsocksMethods

from .notification_enable import NotificationEnable
from .validators import DiscordValidator, ProxyValidator, URLValidator

TELEGRAM_TOKEN_PATTERN = r"^\d{8,12}:[A-Za-z0-9_-]{35}$"
BUILTIN_FORMAT_VARIABLES = {
    "SERVER_IP",
    "SERVER_IPV6",
    "USERNAME",
    "DATA_USAGE",
    "DATA_LIMIT",
    "DATA_LEFT",
    "DAYS_LEFT",
    "EXPIRE_DATE",
    "JALALI_EXPIRE_DATE",
    "TIME_LEFT",
    "STATUS_EMOJI",
    "USAGE_PERCENTAGE",
    "ADMIN_USERNAME",
    "PROFILE_TITLE",
    "PROTOCOL",
    "TRANSPORT",
    "url",
    "format",
}
BUILTIN_CUSTOM_VARIABLE_KEYS = {variable.upper() for variable in BUILTIN_FORMAT_VARIABLES}


class RunMethod(StrEnum):
    WEBHOOK = "webhook"
    LONGPOLLING = "long-polling"


class Telegram(BaseModel):
    enable: bool = Field(default=False)
    token: str | None = Field(default=None)
    webhook_url: str | None = Field(default=None)
    webhook_secret: str | None = Field(default=None)
    proxy_url: str | None = Field(default=None)
    method: RunMethod = Field(default=RunMethod.WEBHOOK)

    mini_app_login: bool = Field(default=True)
    mini_app_web_url: str | None = Field(default="")

    for_admins_only: bool = Field(default=True)

    @field_validator("mini_app_web_url")
    @classmethod
    def validate_mini_app_web_url(cls, v):
        return URLValidator.validate_url(v)

    @field_validator("webhook_url")
    def validate_webhook_url(cls, v, values):
        method = values.data.get("method", "webhook")
        if method == "webhook":
            return URLValidator.validate_url(v)

    @field_validator("proxy_url")
    @classmethod
    def validate_proxy_url(cls, v):
        return ProxyValidator.validate_proxy_url(v)

    @field_validator("token")
    @classmethod
    def token_validation(cls, v):
        if not v:
            return v
        if not re.match(TELEGRAM_TOKEN_PATTERN, v):
            raise ValueError("Invalid telegram token format")
        return v

    @model_validator(mode="after")
    def check_enable_requires_token_and_url(self):
        if self.enable and (
            (self.method == RunMethod.WEBHOOK and (not self.token or not self.webhook_url or not self.webhook_secret))
            or (self.method == RunMethod.LONGPOLLING and not self.token)
        ):
            if self.method == RunMethod.WEBHOOK:
                raise ValueError("Telegram bot cannot be enabled without token, webhook_url and webhook_secret.")
            elif self.method == RunMethod.LONGPOLLING:
                raise ValueError("Telegram bot cannot be enabled without token.")
        return self


class WebhookInfo(BaseModel):
    url: str
    secret: str


class Webhook(BaseModel):
    enable: bool = Field(default=False)
    webhooks: list[WebhookInfo] = Field(default=[])
    days_left: list[int] = Field(default=[])
    usage_percent: list[int] = Field(default=[])
    timeout: int = Field(gt=0)
    recurrent: int = Field(gt=0)
    proxy_url: str | None = Field(default=None)

    @field_validator("proxy_url", mode="before")
    @classmethod
    def validate_proxy_url(cls, v):
        return ProxyValidator.validate_proxy_url(v)

    @model_validator(mode="after")
    def check_enable_requires_webhookinfo(self):
        if self.enable and (not self.webhooks or len(self.webhooks) == 0):
            raise ValueError("Webhook cannot be enabled without at least one WebhookInfo.")
        return self


class NotificationChannel(BaseModel):
    """Channel configuration for sending notifications to a specific entity"""

    telegram_chat_id: int | None = Field(default=None)
    telegram_topic_id: int | None = Field(default=None)
    discord_webhook_url: str | None = Field(default=None)

    @field_validator("discord_webhook_url", mode="before")
    @classmethod
    def validate_discord_webhook(cls, value):
        return DiscordValidator.validate_webhook(value)


class NotificationChannels(BaseModel):
    """Per-object notification channels"""

    admin: NotificationChannel = Field(default_factory=NotificationChannel)
    admin_role: NotificationChannel = Field(default_factory=NotificationChannel)
    core: NotificationChannel = Field(default_factory=NotificationChannel)
    group: NotificationChannel = Field(default_factory=NotificationChannel)
    host: NotificationChannel = Field(default_factory=NotificationChannel)
    node: NotificationChannel = Field(default_factory=NotificationChannel)
    user: NotificationChannel = Field(default_factory=NotificationChannel)
    user_template: NotificationChannel = Field(default_factory=NotificationChannel)
    api_key: NotificationChannel = Field(default_factory=NotificationChannel)


class NotificationSettings(BaseModel):
    # Define Which Notfication System Work's
    notify_telegram: bool = Field(default=False)
    notify_discord: bool = Field(default=False)

    # Telegram Settings
    telegram_api_token: str | None = Field(default=None)

    # Fallback Telegram Channel
    telegram_chat_id: int | None = Field(default=None)
    telegram_topic_id: int | None = Field(default=None)

    # Fallback Discord Settings
    discord_webhook_url: str | None = Field(default=None)

    # Per-object notification channels
    channels: NotificationChannels = Field(default_factory=NotificationChannels)

    # Proxy Settings
    proxy_url: str | None = Field(default=None)

    max_retries: int = Field(gt=1)

    @field_validator("proxy_url", mode="before")
    @classmethod
    def validate_proxy_url(cls, v):
        return ProxyValidator.validate_proxy_url(v)

    @field_validator("discord_webhook_url", mode="before")
    @classmethod
    def validate_discord_webhook(cls, value):
        return DiscordValidator.validate_webhook(value)

    @model_validator(mode="after")
    def check_notify_discord_requires_url(self):
        if self.notify_discord and not self.discord_webhook_url:
            raise ValueError("Discord notification cannot be enabled without webhook url.")
        return self

    @model_validator(mode="after")
    def check_notify_telegram_requires_token_and_id(self):
        if self.notify_telegram and not self.telegram_api_token:
            raise ValueError("Telegram notification cannot be enabled without token.")
        if self.notify_telegram and not self.telegram_chat_id:
            raise ValueError("Telegram notification cannot be enabled without chat id.")
        return self


class ConfigFormat(str, Enum):
    links = "links"
    links_base64 = "links_base64"
    xray = "xray"
    wireguard = "wireguard"
    sing_box = "sing_box"
    clash = "clash"
    clash_meta = "clash_meta"
    outline = "outline"
    block = "block"


class RuleOperator(StrEnum):
    AND = "AND"
    OR = "OR"


class ConditionOperator(StrEnum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    CONTAINS = "CONTAINS"
    NOT_CONTAINS = "NOT_CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    NOT_STARTS_WITH = "NOT_STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    NOT_ENDS_WITH = "NOT_ENDS_WITH"
    REGEX = "REGEX"
    NOT_REGEX = "NOT_REGEX"


class ResponseType(StrEnum):
    MIHOMO = "MIHOMO"
    CLASH = "CLASH"
    STASH = "STASH"
    SINGBOX = "SINGBOX"
    XRAY_JSON = "XRAY_JSON"
    XRAY_BASE64 = "XRAY_BASE64"
    LINKS = "LINKS"
    WIREGUARD = "WIREGUARD"
    OUTLINE = "OUTLINE"
    BROWSER = "BROWSER"
    BLOCK = "BLOCK"
    STATUS_CODE_404 = "STATUS_CODE_404"
    STATUS_CODE_451 = "STATUS_CODE_451"
    SOCKET_DROP = "SOCKET_DROP"


RESPONSE_TYPE_TO_CONFIG_FORMAT: dict[str, ConfigFormat] = {
    ResponseType.MIHOMO.value: ConfigFormat.clash_meta,
    ResponseType.CLASH.value: ConfigFormat.clash,
    ResponseType.STASH.value: ConfigFormat.clash,
    ResponseType.SINGBOX.value: ConfigFormat.sing_box,
    ResponseType.XRAY_JSON.value: ConfigFormat.xray,
    ResponseType.XRAY_BASE64.value: ConfigFormat.links_base64,
    ResponseType.LINKS.value: ConfigFormat.links,
    ResponseType.WIREGUARD.value: ConfigFormat.wireguard,
    ResponseType.OUTLINE.value: ConfigFormat.outline,
    ResponseType.BLOCK.value: ConfigFormat.block,
    ConfigFormat.clash_meta.value: ConfigFormat.clash_meta,
    ConfigFormat.clash.value: ConfigFormat.clash,
    ConfigFormat.sing_box.value: ConfigFormat.sing_box,
    ConfigFormat.xray.value: ConfigFormat.xray,
    ConfigFormat.links_base64.value: ConfigFormat.links_base64,
    ConfigFormat.links.value: ConfigFormat.links,
    ConfigFormat.wireguard.value: ConfigFormat.wireguard,
    ConfigFormat.outline.value: ConfigFormat.outline,
    ConfigFormat.block.value: ConfigFormat.block,
}

CONFIG_FORMAT_TO_RESPONSE_TYPE: dict[str, ResponseType] = {
    ConfigFormat.clash_meta.value: ResponseType.MIHOMO,
    ConfigFormat.clash.value: ResponseType.CLASH,
    ConfigFormat.sing_box.value: ResponseType.SINGBOX,
    ConfigFormat.xray.value: ResponseType.XRAY_JSON,
    ConfigFormat.links_base64.value: ResponseType.XRAY_BASE64,
    ConfigFormat.links.value: ResponseType.LINKS,
    ConfigFormat.wireguard.value: ResponseType.WIREGUARD,
    ConfigFormat.outline.value: ResponseType.OUTLINE,
    ConfigFormat.block.value: ResponseType.BLOCK,
}


class RuleCondition(BaseModel):
    header_name: str = Field(
        default="user-agent",
        validation_alias=AliasChoices("headerName", "header_name"),
        serialization_alias="headerName",
        min_length=1,
        max_length=100,
    )
    operator: ConditionOperator = ConditionOperator.CONTAINS
    value: str = Field(default="", max_length=255)
    case_sensitive: bool = Field(
        default=False,
        validation_alias=AliasChoices("caseSensitive", "case_sensitive"),
        serialization_alias="caseSensitive",
    )

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("operator", mode="before")
    @classmethod
    def normalize_operator(cls, value: Any) -> Any:
        if isinstance(value, str):
            val_upper = value.strip().upper()
            try:
                return ConditionOperator(val_upper)
            except ValueError:
                pass
        return value


class ResponseHeaderItem(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: Any = Field(default="")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class ResponseModifications(BaseModel):
    subscription_template: str | None = Field(
        default=None,
        validation_alias=AliasChoices("subscriptionTemplate", "subscription_template"),
        serialization_alias="subscriptionTemplate",
    )
    headers: list[ResponseHeaderItem] | dict[str, Any] = Field(default_factory=list)
    apply_headers_to_end: bool = Field(
        default=False,
        validation_alias=AliasChoices("applyHeadersToEnd", "apply_headers_to_end"),
        serialization_alias="applyHeadersToEnd",
    )
    ignore_host_xray_json_template: bool = Field(
        default=False,
        validation_alias=AliasChoices("ignoreHostXrayJsonTemplate", "ignore_host_xray_json_template"),
        serialization_alias="ignoreHostXrayJsonTemplate",
    )
    ignore_serve_json_at_base_subscription: bool = Field(
        default=False,
        validation_alias=AliasChoices("ignoreServeJsonAtBaseSubscription", "ignore_serve_json_at_base_subscription"),
        serialization_alias="ignoreServeJsonAtBaseSubscription",
    )
    disable_hwid_check: bool = Field(
        default=False,
        validation_alias=AliasChoices("disableHwidCheck", "disable_hwid_check"),
        serialization_alias="disableHwidCheck",
    )

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class SubRule(BaseModel):
    name: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=250)
    enabled: bool = Field(default=True)
    operator: RuleOperator = Field(default=RuleOperator.AND)
    conditions: list[RuleCondition] = Field(default_factory=list)
    response_type: ResponseType = Field(
        default=ResponseType.XRAY_BASE64,
        validation_alias=AliasChoices("responseType", "response_type"),
        serialization_alias="responseType",
    )
    response_modifications: ResponseModifications = Field(
        default_factory=ResponseModifications,
        validation_alias=AliasChoices("responseModifications", "response_modifications"),
        serialization_alias="responseModifications",
    )

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("response_type", mode="before")
    @classmethod
    def normalize_response_type(cls, value: Any) -> Any:
        if isinstance(value, str):
            val_strip = value.strip()
            val_upper = val_strip.upper()
            try:
                return ResponseType(val_upper)
            except ValueError:
                pass
            if val_strip.lower() in CONFIG_FORMAT_TO_RESPONSE_TYPE:
                return CONFIG_FORMAT_TO_RESPONSE_TYPE[val_strip.lower()]
        elif isinstance(value, ConfigFormat):
            return CONFIG_FORMAT_TO_RESPONSE_TYPE.get(value.value, ResponseType.XRAY_BASE64)
        return value

    @field_validator("operator", mode="before")
    @classmethod
    def normalize_operator(cls, value: Any) -> Any:
        if isinstance(value, str):
            val_upper = value.strip().upper()
            try:
                return RuleOperator(val_upper)
            except ValueError:
                pass
        return value

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_sub_rule(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        pattern = data.get("pattern")
        target = data.get("target")
        response_headers = data.get("response_headers")

        if pattern is not None or target is not None:
            name = data.get("name")
            if not name:
                if target:
                    name = f"Rule for {target}"
                elif pattern:
                    name = f"Rule: {pattern}"[:50]
                else:
                    name = "Legacy Rule"
            data["name"] = str(name)[:100]
            conditions = data.get("conditions")
            if conditions is None and pattern is not None:
                conditions = [
                    {
                        "headerName": "user-agent",
                        "operator": "REGEX",
                        "value": pattern,
                        "caseSensitive": True,
                    }
                ]
            data["conditions"] = conditions or []

            if not data.get("responseType") and not data.get("response_type") and target is not None:
                data["responseType"] = target

            if not data.get("responseModifications") and not data.get("response_modifications") and response_headers:
                data["responseModifications"] = {"headers": response_headers}

        return data

    @computed_field
    @property
    def pattern(self) -> str:
        for cond in self.conditions:
            if cond.header_name.lower() == "user-agent" and cond.operator == ConditionOperator.REGEX:
                return cond.value
        return self.conditions[0].value if self.conditions else ".*"

    @computed_field
    @property
    def target(self) -> ConfigFormat:
        return RESPONSE_TYPE_TO_CONFIG_FORMAT.get(self.response_type.value, ConfigFormat.links_base64)

    @computed_field
    @property
    def response_headers(self) -> dict[str, Any]:
        headers = self.response_modifications.headers
        if isinstance(headers, dict):
            return headers
        if isinstance(headers, list):
            res = {}
            for item in headers:
                if isinstance(item, ResponseHeaderItem):
                    res[item.key] = item.value
                elif isinstance(item, dict) and "key" in item:
                    res[item["key"]] = item.get("value", "")
            return res
        return {}


class SubFormatEnable(BaseModel):
    links: bool = Field(default=True)
    links_base64: bool = Field(default=True)
    xray: bool = Field(default=True)
    wireguard: bool = Field(default=True)
    sing_box: bool = Field(default=True)
    clash: bool = Field(default=True)
    clash_meta: bool = Field(default=True)
    outline: bool = Field(default=True)


class Platform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    APPLETV = "appletv"
    ANDROIDTV = "androidtv"


class Language(StrEnum):
    FA = "fa"
    EN = "en"
    RU = "ru"
    ZH = "zh"


class DownloadLink(BaseModel):
    name: str = Field(max_length=64)
    url: str
    language: Language


class Application(BaseModel):
    name: str = Field(max_length=32)
    icon_url: str = Field(default="", max_length=512)
    import_url: str = Field(default="", max_length=256)
    description: dict[Language, str] = Field(default_factory=dict)
    recommended: bool = Field(False)
    show_when_hwid_enabled: bool = Field(False)
    platform: Platform
    download_links: list[DownloadLink]

    @field_validator("import_url")
    @classmethod
    def validate_import_url(cls, v: str) -> str:
        """Validate import_url contains {url} if not empty."""
        if v and "{url}" not in v:
            raise ValueError("import_url must contain {url} placeholder for URL replacement")
        return v


class CustomVariable(BaseModel):
    key: str = Field(max_length=64)
    value: str = Field(default="", max_length=512)

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value):
        if not isinstance(value, str):
            raise TypeError("Variable key must be a string")
        value = value.strip()
        if value.startswith("{") and value.endswith("}"):
            value = value[1:-1].strip()
        return value.upper()

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", value):
            raise ValueError("Variable key must use uppercase letters, numbers, and underscores")
        return value

    @field_validator("value")
    @classmethod
    def validate_value_format(cls, value: str) -> str:
        try:
            value.format_map({key: "" for key in BUILTIN_FORMAT_VARIABLES})
        except ValueError:
            raise ValueError("Invalid formatting variables")
        except KeyError:
            pass
        return value


def validate_custom_variables(value: list[CustomVariable]) -> list[CustomVariable]:
    seen: set[str] = set()
    for variable in value:
        if variable.key.upper() in BUILTIN_CUSTOM_VARIABLE_KEYS:
            raise ValueError(f"Custom variable {variable.key} conflicts with a built-in variable")
        if variable.key in seen:
            raise ValueError(f"Duplicate custom variable {variable.key}")
        seen.add(variable.key)
    return value


class Subscription(BaseModel):
    url_prefix: str = Field(default="")
    update_interval: int = Field(default=12)
    support_url: str = Field(default="https://t.me/")
    profile_title: str = Field(default="Subscription")
    # only supported by v2RayTun and Happ apps
    announce: str = Field(default="", max_length=128)
    announce_url: str = Field(default="")
    response_headers: dict[str, Any] = Field(default_factory=dict)
    # Rules To Seperate Clients And Send Config As Needed
    rules: list[SubRule]
    manual_sub_request: SubFormatEnable = Field(default_factory=SubFormatEnable)
    applications: list[Application] = Field(default_factory=list)
    allow_browser_config: bool = Field(default=True)
    disable_sub_template: bool = Field(default=False)
    randomize_order: bool = Field(default=False)
    custom_variables: list[CustomVariable] = Field(default_factory=list)

    @field_validator("custom_variables")
    @classmethod
    def validate_custom_variables(cls, value: list[CustomVariable]) -> list[CustomVariable]:
        return validate_custom_variables(value)

    @field_validator("applications")
    @classmethod
    def validate_recommended_apps(cls, v: list[Application]) -> list[Application]:
        """Validate that each platform has at most one recommended app per subscription type."""
        platform_recommended = {}

        for app in v:
            if app.recommended:
                recommendation_key = (app.platform, app.show_when_hwid_enabled)
                if recommendation_key in platform_recommended:
                    subscription_type = "device-bound" if app.show_when_hwid_enabled else "standard"
                    raise ValueError(
                        f"Multiple recommended {subscription_type} applications found for platform '{app.platform}'."
                    )
                platform_recommended[recommendation_key] = app.name

        return v


class HWIDSettings(BaseModel):
    enabled: bool = Field(default=True)
    forced: bool = Field(default=False)
    require_hwid_for_manual_sub: bool = Field(default=False)
    fallback_limit: int | None = Field(default=None, ge=0)
    min_limit: int | None = Field(default=None, ge=0)
    max_limit: int | None = Field(default=None, ge=0)


class General(BaseModel):
    default_method: ShadowsocksMethods = Field(default=ShadowsocksMethods.CHACHA20_POLY1305)
    custom_variables: list[CustomVariable] | None = Field(default=None)

    @field_validator("custom_variables")
    @classmethod
    def validate_custom_variables(cls, value: list[CustomVariable] | None) -> list[CustomVariable] | None:
        if value is None:
            return None
        return validate_custom_variables(value)


class SettingsSchema(BaseModel):
    telegram: Telegram | None = Field(default=None)
    webhook: Webhook | None = Field(default=None)
    notification_settings: NotificationSettings | None = Field(default=None)
    notification_enable: NotificationEnable | None = Field(default=None)
    subscription: Subscription | None = Field(default=None)
    hwid: HWIDSettings | None = Field(default=None)
    general: General | None = Field(default=None)

    model_config = ConfigDict(from_attributes=True)


DEFAULT_SUBSCRIPTION_RULES: list[dict[str, Any]] = [
    {
        "name": "Clash Meta / Mihomo",
        "description": "Serve Mihomo YAML configuration",
        "enabled": True,
        "operator": "AND",
        "conditions": [
            {
                "headerName": "user-agent",
                "operator": "REGEX",
                "value": r"^(?:FlClashX?|Flowvy|[Cc]lash(?:-(?:[Vv]erge|nyanpasu)|X [Mm]eta|-?[Mm]eta)|[Kk]oala-[Cc]lash|[Mm](?:urge|ihomo)|prizrak-box|clash\.meta)",
                "caseSensitive": True,
            }
        ],
        "responseType": "MIHOMO",
        "responseModifications": {},
    },
    {
        "name": "Clash / Stash",
        "description": "Serve Clash YAML configuration",
        "enabled": True,
        "operator": "AND",
        "conditions": [
            {
                "headerName": "user-agent",
                "operator": "REGEX",
                "value": r"^([Cc]lash|[Ss]tash)",
                "caseSensitive": True,
            }
        ],
        "responseType": "CLASH",
        "responseModifications": {},
    },
    {
        "name": "Sing-box",
        "description": "Serve Sing-box JSON configuration",
        "enabled": True,
        "operator": "AND",
        "conditions": [
            {
                "headerName": "user-agent",
                "operator": "REGEX",
                "value": r"^(SFA|SFI|SFM|SFT|[Kk]aring|[Hh]iddify[Nn]ext)|.*[Ss]ing[\-b]?ox.*",
                "caseSensitive": True,
            }
        ],
        "responseType": "SINGBOX",
        "responseModifications": {},
    },
    {
        "name": "Outline / Shadowsocks",
        "description": "Serve Outline / Shadowsocks configuration",
        "enabled": True,
        "operator": "AND",
        "conditions": [
            {
                "headerName": "user-agent",
                "operator": "REGEX",
                "value": r"^(SS|SSR|SSD|SSS|Outline|Shadowsocks|SSconf)",
                "caseSensitive": True,
            }
        ],
        "responseType": "OUTLINE",
        "responseModifications": {},
    },
    {
        "name": "Xray / InHive / V2Ray",
        "description": "Serve Xray JSON configuration",
        "enabled": True,
        "operator": "AND",
        "conditions": [
            {
                "headerName": "user-agent",
                "operator": "REGEX",
                "value": r"^[Ii]n[Hh]ive|^([Vv]2rayNG|[Vv]2rayN|[Ss]treisand|[Hh]app|[Kk]tor\-client)",
                "caseSensitive": True,
            }
        ],
        "responseType": "XRAY_JSON",
        "responseModifications": {},
    },
    {
        "name": "Web Browser",
        "description": "Serve HTML subscription page for browsers",
        "enabled": True,
        "operator": "AND",
        "conditions": [
            {
                "headerName": "accept",
                "operator": "CONTAINS",
                "value": "text/html",
                "caseSensitive": False,
            }
        ],
        "responseType": "BROWSER",
        "responseModifications": {},
    },
    {
        "name": "Default Fallback",
        "description": "Fallback rule for all other clients",
        "enabled": True,
        "operator": "AND",
        "conditions": [],
        "responseType": "XRAY_BASE64",
        "responseModifications": {},
    },
]
