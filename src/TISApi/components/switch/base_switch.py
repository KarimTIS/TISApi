from collections.abc import Callable
from math import ceil
from typing import Any, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import MATCH_ALL, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import Event, callback

from ...api import TISApi
from ...BytesHelper import int_to_8_bit_binary
from ...Protocols.udp.ProtocolHandler import TISProtocolHandler, TISPacket


class BaseTISSwitch(SwitchEntity):
    """Base class for TIS switches."""

    def __init__(
        self,
        tis_api: TISApi,
        *,
        channel_number: int,
        device_id: list[int],
        gateway: str,
        is_protected: bool = False,
        **kwargs: Any,
    ) -> None:
        """Initialize the base switch attributes."""
        super().__init__(**kwargs)

        self.api = tis_api
        self._state = STATE_UNKNOWN
        self._attr_is_on: Optional[bool] = None

        # Unique id
        self._attr_unique_id = (
            f"tis_{'_'.join(map(str, device_id))}_ch{int(channel_number)}"
        )

        self.device_id = device_id
        self.gateway = gateway
        self.channel_number = int(channel_number)
        self.is_protected = is_protected
        self._listener: Optional[Callable] = None

        # Create packets once
        self.on_packet: TISPacket = TISProtocolHandler.generate_control_on_packet(self)
        self.off_packet: TISPacket = TISProtocolHandler.generate_control_off_packet(
            self
        )
        self.update_packet: TISPacket = (
            TISProtocolHandler.generate_control_update_packet(self)
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to events when entity is added to hass."""

        @callback
        def _handle_event(event: Event) -> None:
            """Handle incoming TIS events and update state."""

            # check if event is for this switch
            if event.event_type == str(self.device_id):
                feedback_type = event.data.get("feedback_type")
                if feedback_type == "control_response":
                    channel_value = event.data["additional_bytes"][2]
                    channel_number = event.data["channel_number"]
                    if int(channel_number) == self.channel_number:
                        self._state = (
                            STATE_ON if int(channel_value) == 100 else STATE_OFF
                        )

                elif feedback_type == "binary_feedback":
                    n_bytes = ceil(event.data["additional_bytes"][0] / 8)
                    channels_status = "".join(
                        int_to_8_bit_binary(event.data["additional_bytes"][i])
                        for i in range(1, n_bytes + 1)
                    )
                    self._state = (
                        STATE_ON
                        if channels_status[self.channel_number - 1] == "1"
                        else STATE_OFF
                    )

                elif feedback_type == "update_response":
                    additional_bytes = event.data["additional_bytes"]
                    channel_status = int(additional_bytes[self.channel_number])
                    self._state = STATE_ON if channel_status > 0 else STATE_OFF

                elif feedback_type == "offline_device":
                    self._state = STATE_UNKNOWN

            self.schedule_update_ha_state()

        self._listener = self.hass.bus.async_listen(MATCH_ALL, _handle_event)
        await self.api.protocol.sender.send_packet(self.update_packet)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from events when entity is removed from hass."""
        if callable(self._listener):
            try:
                self._listener()
            finally:
                self._listener = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        ack_status = await self.api.protocol.sender.send_packet_with_ack(self.on_packet)
        if ack_status:
            self._state = STATE_ON
        else:
            self._state = STATE_UNKNOWN
            event_data = {
                "device_id": self.device_id,
                "feedback_type": "offline_device",
            }
            self.hass.bus.async_fire(str(self.device_id), event_data)
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        ack_status = await self.api.protocol.sender.send_packet_with_ack(
            self.off_packet
        )
        self._state = STATE_OFF if ack_status else STATE_UNKNOWN
        self.schedule_update_ha_state()
