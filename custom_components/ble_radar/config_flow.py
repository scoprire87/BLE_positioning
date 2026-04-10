"""Adds config flow for BLE Radar."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from bluetooth_data_tools import monotonic_time_coarse
from homeassistant import config_entries
from homeassistant.config_entries import OptionsFlowWithConfigEntry
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    DeviceSelector,
    DeviceSelectorConfig,
    ObjectSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    ADDR_TYPE_IBEACON,
    ADDR_TYPE_PRIVATE_BLE_DEVICE,
    BDADDR_TYPE_RANDOM_RESOLVABLE,
    CONF_ATTENUATION,
    CONF_DEVICES,
    CONF_DEVTRACK_TIMEOUT,
    CONF_MAX_RADIUS,
    CONF_MAX_VELOCITY,
    CONF_REF_POWER,
    CONF_RSSI_OFFSETS,
    CONF_SAVE_AND_CLOSE,
    CONF_SCANNER_INFO,
    CONF_SCANNERS,
    CONF_SMOOTHING_SAMPLES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ATTENUATION,
    DEFAULT_DEVTRACK_TIMEOUT,
    DEFAULT_MAX_RADIUS,
    DEFAULT_MAX_VELOCITY,
    DEFAULT_REF_POWER,
    DEFAULT_SMOOTHING_SAMPLES,
    DEFAULT_UPDATE_INTERVAL,
    DISTANCE_INFINITE,
    DOMAIN,
    DOMAIN_PRIVATE_BLE_DEVICE,
    NAME,
)
from .util import mac_redact, rssi_to_metres

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
    from homeassistant.config_entries import ConfigFlowResult

    from . import BermudaConfigEntry
    from .bermuda_device import BermudaDevice
    from .coordinator import BermudaDataUpdateCoordinator


class BermudaFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ble radar."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._errors = {}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_show_form(step_id="user", description_placeholders={"name": NAME})

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title=NAME, data={"source": "user"}, description=NAME)

        return self.async_show_form(step_id="user", description_placeholders={"name": NAME})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BermudaOptionsFlowHandler(config_entry)


class BermudaOptionsFlowHandler(OptionsFlowWithConfigEntry):
    """Config flow options handler for BLE Radar."""

    def __init__(self, config_entry: BermudaConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)
        self.coordinator: BermudaDataUpdateCoordinator
        self.devices: dict[str, BermudaDevice]

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        self.coordinator = self.config_entry.runtime_data.coordinator
        self.devices = self.coordinator.devices

        messages = {}
        active_devices = self.coordinator.count_active_devices()
        active_scanners = self.coordinator.count_active_scanners()

        messages["device_counter_active"] = f"{active_devices}"
        messages["device_counter_devices"] = f"{len(self.devices)}"
        messages["scanner_counter_active"] = f"{active_scanners}"
        messages["scanner_counter_scanners"] = f"{len(self.coordinator.scanner_list)}"

        if len(self.coordinator.scanner_list) == 0:
            messages["status"] = (
                "Hai bisogno di almeno uno scanner (es. Shelly o ESPHome) prima di poter tracciare."
            )
        elif active_devices == 0:
            messages["status"] = (
                "Non sto ricevendo segnali dai tuoi dispositivi. Accendi il bluetooth!"
            )
        else:
            messages["status"] = "I radar sono operativi e stanno ricevendo segnali."

        scanner_table = "\n\nStato dei Proxy (Scanner):\n\n|Scanner|Address|Last advertisement|\n|---|---|---:|\n"
        for scanner in self.coordinator.get_active_scanner_summary():
            age = int(scanner.get("last_stamp_age", 999))
            if age < 2:
                status = '🟢'
            elif age < 10:
                status = '🟡'
            else:
                status = '🔴'
            shortmac = mac_redact(scanner.get("address", "ERR"))
            scanner_table += (
                f"| {scanner.get('name', 'NAME_ERR')}| [{shortmac}]"
                f"| {status} {(scanner.get('last_stamp_age', DISTANCE_INFINITE)):.2f}s fa.|\n"
            )
        messages["status"] += scanner_table

        return self.async_show_menu(
            step_id="init",
            menu_options={
                "globalopts": "Opzioni Globali",
                "selectdevices": "Seleziona i Dispositivi da Tracciare",
            },
            description_placeholders=messages,
        )

    async def async_step_globalopts(self, user_input=None):
        """Handle global options flow."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        # Abbiamo rimosso opzioni matematiche inutili per il radar (attenuazione, potenza)
        data_schema = {
            vol.Required(
                CONF_MAX_VELOCITY,
                default=self.options.get(CONF_MAX_VELOCITY, DEFAULT_MAX_VELOCITY),
            ): vol.Coerce(float),
            vol.Required(
                CONF_DEVTRACK_TIMEOUT,
                default=self.options.get(CONF_DEVTRACK_TIMEOUT, DEFAULT_DEVTRACK_TIMEOUT),
            ): vol.Coerce(int),
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=self.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): vol.Coerce(float),
        }

        return self.async_show_form(step_id="globalopts", data_schema=vol.Schema(data_schema))

    async def async_step_selectdevices(self, user_input=None):
        """Scegli quali dispositivi il Radar deve seguire."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        self.devices = self.config_entry.runtime_data.coordinator.devices
        options_list = []
        options_metadevices = []
        options_otherdevices = []
        options_randoms = []

        for device in self.devices.values():
            name = device.name

            if device.is_scanner:
                continue
            if device.address_type == ADDR_TYPE_PRIVATE_BLE_DEVICE:
                continue
            if device.address_type == ADDR_TYPE_IBEACON:
                if len(device.metadevice_sources) > 0:
                    source_mac = f"[{device.metadevice_sources[0].upper()}]"
                else:
                    source_mac = ""

                options_metadevices.append(
                    SelectOptionDict(
                        value=device.address.upper(),
                        label=f"iBeacon: {device.address.upper()} {source_mac} "
                        f"{name if device.address.upper() != name.upper() else ''}",
                    )
                )
                continue

            if device.address_type == BDADDR_TYPE_RANDOM_RESOLVABLE:
                if device.last_seen < monotonic_time_coarse() - (60 * 60 * 2):
                    continue
                options_randoms.append(
                    SelectOptionDict(
                        value=device.address.upper(),
                        label=f"[{device.address.upper()}] {name} (Random MAC)",
                    )
                )
                continue

            options_otherdevices.append(
                SelectOptionDict(
                    value=device.address.upper(),
                    label=f"[{device.address.upper()}] {name}",
                )
            )

        options_metadevices.sort(key=lambda item: item["label"])
        options_otherdevices.sort(key=lambda item: item["label"])
        options_randoms.sort(key=lambda item: item["label"])
        options_list.extend(options_metadevices)
        options_list.extend(options_otherdevices)
        options_list.extend(options_randoms)

        for address in self.options.get(CONF_DEVICES, []):
            if not next(
                (item for item in options_list if item["value"] == address.upper()),
                False,
            ):
                options_list.append(SelectOptionDict(value=address.upper(), label=f"[{address}] (saved)"))

        data_schema = {
            vol.Optional(
                CONF_DEVICES,
                default=self.options.get(CONF_DEVICES, []),
            ): SelectSelector(SelectSelectorConfig(options=options_list, multiple=True)),
        }

        return self.async_show_form(step_id="selectdevices", data_schema=vol.Schema(data_schema))

    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(title=NAME, data=self.options)
