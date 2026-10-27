"""Config flow for the Hitachi refrigerator cloud."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.exceptions import ConfigEntryError

from . import async_create_client
from .api import HitachiAuthError, HitachiError
from .const import CONF_SESSION, DOMAIN

SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})


class HitachiConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _async_login(
        self, email: str, password: str
    ) -> tuple[dict[str, Any] | None, str | None, dict[str, str]]:
        """Log in and list devices. Returns (session, account id, errors)."""
        try:
            client = await async_create_client(self.hass, email, password)
            session = await client.login()
            if not await client.get_devices():
                return None, None, {"base": "no_devices"}
        except ConfigEntryError:
            return None, None, {"base": "missing_keys"}
        except HitachiAuthError:
            return None, None, {"base": "invalid_auth"}
        except HitachiError:
            return None, None, {"base": "cannot_connect"}
        return session.as_dict(), session.cspf_id, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            session, account_id, errors = await self._async_login(email, user_input[CONF_PASSWORD])
            if session is not None:
                await self.async_set_unique_id(account_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=email,
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SESSION: session,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again after it was changed."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            session, account_id, errors = await self._async_login(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if session is not None:
                await self.async_set_unique_id(account_id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD], CONF_SESSION: session},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
