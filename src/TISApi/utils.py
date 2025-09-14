from .api import TISApi
from homeassistant.const import Platform


async def async_get_switches(tis_api: TISApi) -> list[dict]:
    """Fetch switches from TIS API and normalize to a list of dictionaries.

    Returns a list with items like:
    {
        "switch_name": str,
        "channel_number": int,
        "device_id": list[int],
        "is_protected": bool,
        "gateway": str,
    }

    Having this helper makes the setup code easier to test and keeps the
    API parsing logic in one place.
    """
    raw = await tis_api.get_entities(platform=Platform.SWITCH)
    if not raw:
        return []

    result: list[dict] = []
    for appliance in raw:
        channel_number = int(list(appliance["channels"][0].values())[0])
        result.append(
            {
                "switch_name": appliance.get("name"),
                "channel_number": channel_number,
                "device_id": appliance.get("device_id"),
                "is_protected": appliance.get("is_protected", False),
                "gateway": appliance.get("gateway"),
            }
        )

    return result
