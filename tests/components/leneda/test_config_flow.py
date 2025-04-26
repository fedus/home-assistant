"""Test the Leneda config flow."""

from __future__ import annotations

import asyncio
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

from leneda.exceptions import ForbiddenException, UnauthorizedException
from leneda.obis_codes import ObisCode
import pytest

from homeassistant import config_entries
from homeassistant.components.leneda.const import (
    CONF_API_TOKEN,
    CONF_ENERGY_ID,
    DOMAIN,
    SENSOR_TYPES,
)
from homeassistant.components.recorder.core import Recorder
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry

# Mock values for testing
MOCK_API_TOKEN = "test_api_token"
MOCK_ENERGY_ID = "test_energy_id"
MOCK_METERING_POINT = "MP001"
MOCK_OBIS_CODES = [ObisCode.ELEC_CONSUMPTION_ACTIVE, ObisCode.GAS_CONSUMPTION_VOLUME]
MOCK_NEW_API_TOKEN = "new_test_api_token"


@pytest.fixture(autouse=True)
async def recorder_mock(
    recorder_mock: Recorder,
    hass: HomeAssistant,
) -> None:
    """Set up the recorder with a temporary SQLite database."""
    await hass.async_block_till_done()


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_TOKEN: MOCK_API_TOKEN,
            CONF_ENERGY_ID: MOCK_ENERGY_ID,
        },
        options={},
        unique_id=MOCK_ENERGY_ID,
    )


async def test_form_user_success(hass: HomeAssistant, recorder_mock: Recorder) -> None:
    """Test successful user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.probe_metering_point_obis_code",
        new_callable=AsyncMock,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_TOKEN: MOCK_API_TOKEN,
                CONF_ENERGY_ID: MOCK_ENERGY_ID,
            },
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == MOCK_ENERGY_ID
    assert result2["data"] == {
        CONF_API_TOKEN: MOCK_API_TOKEN,
        CONF_ENERGY_ID: MOCK_ENERGY_ID,
    }


async def test_form_user_unauthorized(
    hass: HomeAssistant, recorder_mock: Recorder
) -> None:
    """Test user flow with unauthorized error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.probe_metering_point_obis_code",
        new_callable=AsyncMock,
        side_effect=UnauthorizedException,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_TOKEN: MOCK_API_TOKEN,
                CONF_ENERGY_ID: MOCK_ENERGY_ID,
            },
        )

        assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": "unauthorized"}


async def test_form_user_forbidden(
    hass: HomeAssistant, recorder_mock: Recorder
) -> None:
    """Test user flow with forbidden error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.probe_metering_point_obis_code",
        new_callable=AsyncMock,
        side_effect=ForbiddenException,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_TOKEN: MOCK_API_TOKEN,
                CONF_ENERGY_ID: MOCK_ENERGY_ID,
            },
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": "forbidden"}


async def test_form_user_duplicate(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test user flow with duplicate entry."""
    # Add a mock existing entry
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.probe_metering_point_obis_code",
        new_callable=AsyncMock,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_TOKEN: MOCK_API_TOKEN,
                CONF_ENERGY_ID: MOCK_ENERGY_ID,
            },
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_subentry_init_happyflow(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test subentry initialization."""
    # Add a mock parent entry
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Start subentry flow
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, "metering_point"),
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    # Configure the metering point
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "metering_point": MOCK_METERING_POINT,
        },
    )

    assert result2["type"] == FlowResultType.MENU
    assert result2["step_id"] == "setup_type"


async def test_subentry_init_invalid_metering_point(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test subentry initialization with invalid metering point."""
    # Add a mock parent entry
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Start subentry flow
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, "metering_point"),
        context={"source": config_entries.SOURCE_USER},
    )

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "metering_point": "",
        },
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "init"
    assert result2["errors"] == {"base": "invalid_metering_point"}


async def test_subentry_init_duplicate_metering_point(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test subentry initialization with duplicate metering point."""
    # Add a mock parent entry with existing subentry
    mock_config_entry.add_to_hass(hass)

    # Create and add the subentry
    subentry = config_entries.ConfigSubentry(
        data=MappingProxyType(
            {
                "metering_point": MOCK_METERING_POINT,
                "sensors": list(SENSOR_TYPES.keys())[:2],
            }
        ),
        subentry_type="metering_point",
        title=MOCK_METERING_POINT,
        unique_id=MOCK_METERING_POINT,
    )

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.get_aggregated_metering_data",
        return_value=MagicMock(),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert hass.config_entries.async_add_subentry(mock_config_entry, subentry)
        await hass.async_block_till_done()

    # Start subentry flow
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, "metering_point"),
        context={"source": config_entries.SOURCE_USER},
    )

    # Configure with duplicate metering point
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "metering_point": MOCK_METERING_POINT,
        },
    )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "duplicate_metering_point"


async def test_subentry_setup_type(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test subentry setup type selection."""
    # Add a mock parent entry
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Start subentry flow
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, "metering_point"),
        context={"source": config_entries.SOURCE_USER},
    )

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "metering_point": MOCK_METERING_POINT,
        },
    )

    assert result2["type"] == FlowResultType.MENU
    assert result2["step_id"] == "setup_type"
    assert "probe" in result2["menu_options"]
    assert "manual" in result2["menu_options"]


async def test_subentry_probe_success(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test successful probing of metering point."""
    # Add a mock parent entry
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Start subentry flow
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, "metering_point"),
        context={"source": config_entries.SOURCE_USER},
    )

    # Enter metering point
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "metering_point": MOCK_METERING_POINT,
        },
    )

    # Should show setup type menu
    assert result2["type"] == FlowResultType.MENU
    assert result2["step_id"] == "setup_type"
    assert "probe" in result2["menu_options"]
    assert "manual" in result2["menu_options"]

    future: asyncio.Future = asyncio.Future()

    async def wait_for_result(*args, **kwargs):
        return await future

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.get_supported_obis_codes",
        new_callable=AsyncMock,
        side_effect=wait_for_result,
    ):
        # Select probe setup type
        result3 = await hass.config_entries.subentries.async_configure(
            result2["flow_id"],
            {"next_step_id": "probe"},
        )

        assert result3["type"] == FlowResultType.SHOW_PROGRESS
        assert result3["progress_action"] == "fetch_obis"

        # Complete the probing
        future.set_result(MOCK_OBIS_CODES)
        await hass.async_block_till_done()

        # Complete the progress step
        result4 = await hass.config_entries.subentries.async_configure(
            result3["flow_id"],
            {"next_step_id": "manual"},
        )

        assert result4["type"] == FlowResultType.FORM
        assert result4["step_id"] == "manual"
        assert result4["description_placeholders"] is not None
        assert "probed_text" in result4["description_placeholders"]


async def test_subentry_probe_no_sensors(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test probing with no sensors found."""
    # Add a mock parent entry
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Start subentry flow
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, "metering_point"),
        context={"source": config_entries.SOURCE_USER},
    )

    # Enter metering point
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "metering_point": MOCK_METERING_POINT,
        },
    )

    # Should show setup type menu
    assert result2["type"] == FlowResultType.MENU
    assert result2["step_id"] == "setup_type"
    assert "probe" in result2["menu_options"]
    assert "manual" in result2["menu_options"]

    future: asyncio.Future = asyncio.Future()

    async def wait_for_result(*args, **kwargs):
        return await future

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.get_supported_obis_codes",
        new_callable=AsyncMock,
        side_effect=wait_for_result,
    ):
        # Select probe setup type
        result3 = await hass.config_entries.subentries.async_configure(
            result2["flow_id"],
            {"next_step_id": "probe"},
        )

        assert result3["type"] == FlowResultType.SHOW_PROGRESS
        assert result3["progress_action"] == "fetch_obis"

        # Complete the probing
        future.set_result([])
        await hass.async_block_till_done()

        # Complete the progress step
        result4 = await hass.config_entries.subentries.async_configure(
            result3["flow_id"],
            {"next_step_id": "probe"},
        )

        assert result4["type"] == FlowResultType.MENU
        assert result4["step_id"] == "probe_no_sensors"
        assert "manual" in result4["menu_options"]


async def test_subentry_probe_unauthorized(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test probing with unauthorized error."""
    # Add a mock parent entry
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Start subentry flow
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, "metering_point"),
        context={"source": config_entries.SOURCE_USER},
    )

    # Enter metering point
    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "metering_point": MOCK_METERING_POINT,
        },
    )

    # Should show setup type menu
    assert result2["type"] == FlowResultType.MENU
    assert result2["step_id"] == "setup_type"
    assert "probe" in result2["menu_options"]
    assert "manual" in result2["menu_options"]

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.get_supported_obis_codes",
        new_callable=AsyncMock,
        side_effect=UnauthorizedException,
    ):
        # Select probe setup type
        result3 = await hass.config_entries.subentries.async_configure(
            result2["flow_id"],
            {"next_step_id": "probe"},
        )

        assert result3["type"] == FlowResultType.ABORT
        assert result3["reason"] == "unauthorized"


async def test_subentry_probe_forbidden(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test probing with forbidden error."""
    # Add a mock parent entry
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Start subentry flow
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, "metering_point"),
        context={"source": config_entries.SOURCE_USER},
    )

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "metering_point": MOCK_METERING_POINT,
        },
    )

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.get_supported_obis_codes",
        new_callable=AsyncMock,
        side_effect=ForbiddenException,
    ):
        # Complete the progress step
        result3 = await hass.config_entries.subentries.async_configure(
            result2["flow_id"],
            {"next_step_id": "probe"},
        )

        assert result3["type"] == FlowResultType.ABORT
        assert result3["reason"] == "forbidden"


async def test_subentry_manual_success(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test successful manual sensor selection."""
    # Add a mock parent entry
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Start subentry flow
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, "metering_point"),
        context={"source": config_entries.SOURCE_USER},
    )

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "metering_point": MOCK_METERING_POINT,
        },
    )

    result3 = await hass.config_entries.subentries.async_configure(
        result2["flow_id"],
        {"next_step_id": "manual"},
    )

    assert result3["type"] == FlowResultType.FORM
    assert result3["step_id"] == "manual"

    # Select some sensors
    selected_sensors = list(SENSOR_TYPES.keys())[:2]
    result4 = await hass.config_entries.subentries.async_configure(
        result3["flow_id"],
        {"sensors": selected_sensors},
    )

    assert result4["type"] == FlowResultType.CREATE_ENTRY
    assert result4["title"] == MOCK_METERING_POINT
    assert result4["data"] == {
        "metering_point": MOCK_METERING_POINT,
        "sensors": selected_sensors,
    }


async def test_subentry_manual_no_sensors(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test manual sensor selection with no sensors selected."""
    # Add a mock parent entry
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Start subentry flow
    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, "metering_point"),
        context={"source": config_entries.SOURCE_USER},
    )

    result2 = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "metering_point": MOCK_METERING_POINT,
        },
    )

    result3 = await hass.config_entries.subentries.async_configure(
        result2["flow_id"],
        {"next_step_id": "manual"},
    )

    assert result3["type"] == FlowResultType.FORM
    assert result3["step_id"] == "manual"

    # Try to submit without selecting sensors
    result4 = await hass.config_entries.subentries.async_configure(
        result3["flow_id"],
        {"sensors": []},
    )

    assert result4["type"] == FlowResultType.FORM
    assert result4["step_id"] == "manual"
    assert result4["errors"] == {"base": "select_at_least_one"}


async def test_subentry_reconfigure(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test reconfiguring an existing subentry."""
    # Add a mock parent entry
    mock_config_entry.add_to_hass(hass)

    # Add a mock subentry
    subentry = config_entries.ConfigSubentry(
        data=MappingProxyType(
            {
                "metering_point": MOCK_METERING_POINT,
                "sensors": [list(SENSOR_TYPES.keys())[0]],
            }
        ),
        subentry_type="metering_point",
        title=MOCK_METERING_POINT,
        unique_id=MOCK_METERING_POINT,
    )

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.get_aggregated_metering_data",
        return_value=MagicMock(),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert hass.config_entries.async_add_subentry(mock_config_entry, subentry)
        await hass.async_block_till_done()

    # Start reconfiguration flow
    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.get_aggregated_metering_data",
        return_value=MagicMock(),
    ):
        result = await hass.config_entries.subentries.async_init(
            (mock_config_entry.entry_id, "metering_point"),
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "subentry_id": subentry.subentry_id,
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "configure_sensors"

        # Update sensors
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                "sensors": list(SENSOR_TYPES.keys())[:2],
            },
        )

        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "reconfigure_successful"

        # Verify subentry was updated
        updated_subentry = mock_config_entry.subentries[subentry.subentry_id]
        assert updated_subentry.data["sensors"] == list(SENSOR_TYPES.keys())[:2]


async def test_reauth_success(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test successful reauthentication flow."""
    # Add a mock existing entry
    mock_config_entry.add_to_hass(hass)

    # Start reauth flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.probe_metering_point_obis_code",
        new_callable=AsyncMock,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_TOKEN: MOCK_NEW_API_TOKEN,
            },
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"

    # Verify the config entry was updated with the new token
    assert mock_config_entry.data[CONF_API_TOKEN] == MOCK_NEW_API_TOKEN


async def test_reauth_unauthorized(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test reauthentication flow with unauthorized error."""
    # Add a mock existing entry
    mock_config_entry.add_to_hass(hass)

    # Start reauth flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.probe_metering_point_obis_code",
        new_callable=AsyncMock,
        side_effect=UnauthorizedException,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_TOKEN: MOCK_NEW_API_TOKEN,
            },
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "reauth_confirm"
    assert result2["errors"] == {"base": "unauthorized"}

    # Verify the config entry was not updated
    assert mock_config_entry.data[CONF_API_TOKEN] == MOCK_API_TOKEN


async def test_reauth_forbidden(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test reauthentication flow with forbidden error."""
    # Add a mock existing entry
    mock_config_entry.add_to_hass(hass)

    # Start reauth flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "homeassistant.components.leneda.config_flow.LenedaClient.probe_metering_point_obis_code",
        new_callable=AsyncMock,
        side_effect=ForbiddenException,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_TOKEN: MOCK_NEW_API_TOKEN,
            },
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "reauth_confirm"
    assert result2["errors"] == {"base": "forbidden"}

    # Verify the config entry was not updated
    assert mock_config_entry.data[CONF_API_TOKEN] == MOCK_API_TOKEN


async def test_reauth_flow_description(
    hass: HomeAssistant, recorder_mock: Recorder, mock_config_entry: MockConfigEntry
) -> None:
    """Test reauthentication flow description contains energy ID."""
    # Add a mock existing entry
    mock_config_entry.add_to_hass(hass)

    # Start reauth flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert "energy_id" in result["description_placeholders"]
    assert result["description_placeholders"]["energy_id"] == MOCK_ENERGY_ID
