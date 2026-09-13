import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.settings import get_settings, modify_settings
from app.db.models import Settings
from app.models.settings import (
    RESPONSE_TEMPLATE_PREFIX,
    General,
    SettingsSchema,
    Subscription,
)
from app.nats.message import MessageTopic
from app.nats.router import router
from app.notification.client import define_client
from app.settings import refresh_caches
from app.subscription.client_templates import resolve_response_template
from app.telegram import startup_telegram_bot

from . import BaseOperation


class SettingsOperation(BaseOperation):
    async def _validate_subscription_rules(self, subscription: Subscription) -> None:
        """
        Validate rules on write and canonicalize template-backed response types.

        Response types that reference a Client Template are stored as TEMPLATE:<id> so
        that renaming the template in the panel does not break the rule. Unknown
        references are rejected here rather than failing at request time, and condition
        bounds the model deliberately tolerates on read are enforced on write.
        """
        for index, rule in enumerate(subscription.rules):
            label = rule.name or f"#{index + 1}"

            for condition in rule.conditions:
                if not condition.value:
                    await self.raise_error(
                        message=f"Rule '{label}': condition on '{condition.header_name}' requires a value",
                        code=400,
                    )

            reference = rule.template_reference
            if reference is None:
                continue

            template = await resolve_response_template(reference)
            if template is None:
                # raise_error always raises; return keeps the None case explicit.
                return await self.raise_error(
                    message=(
                        f"Rule '{label}': response type '{rule.response_type}' does not match any built-in "
                        "type or client template"
                    ),
                    code=400,
                )
            rule.response_type = f"{RESPONSE_TEMPLATE_PREFIX}{template.id}"

    @staticmethod
    async def reset_services(old_settings: SettingsSchema, new_settings: SettingsSchema):
        if new_settings.telegram != old_settings.telegram:
            await startup_telegram_bot()
        # When webhooks are disabled, send_notifications() already returns early
        # Pending webhook notifications will be processed when webhooks are re-enabled
        if old_settings.notification_settings.proxy_url != new_settings.notification_settings.proxy_url:
            await define_client()

    async def get_settings(self, db: AsyncSession) -> Settings:
        return await get_settings(db)

    async def modify_settings(self, db: AsyncSession, modify: SettingsSchema) -> SettingsSchema:
        db_settings = await get_settings(db)
        old_settings = SettingsSchema.model_validate(db_settings)

        if modify.general and modify.general.custom_variables is not None:
            subscription = modify.subscription or Subscription.model_validate(db_settings.subscription)
            modify.subscription = subscription.model_copy(update={"custom_variables": modify.general.custom_variables})
            modify.general = modify.general.model_copy(update={"custom_variables": None})

        if modify.subscription:
            await self._validate_subscription_rules(modify.subscription)

        db_settings = await modify_settings(db, db_settings, modify)
        new_settings = SettingsSchema.model_validate(db_settings)
        if new_settings.general and new_settings.subscription:
            new_settings.general.custom_variables = new_settings.subscription.custom_variables

        await refresh_caches()
        # Publish settings update via NATS (all workers will refresh their caches)
        await router.publish(MessageTopic.SETTING, {"action": "refresh"})
        asyncio.create_task(self.reset_services(old_settings, new_settings))

        return new_settings

    async def get_general_settings(self, db: AsyncSession):
        settings = await self.get_settings(db)
        general = General.model_validate(settings.general)
        subscription = Subscription.model_validate(settings.subscription)
        return general.model_copy(update={"custom_variables": subscription.custom_variables})
