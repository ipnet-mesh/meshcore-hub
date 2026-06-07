"""Tests for RadioConfig schema."""

from meshcore_hub.common.schemas.network import RadioConfig


class TestRadioConfigConstruction:
    """Tests for RadioConfig direct construction."""

    def test_defaults_all_none(self) -> None:
        config = RadioConfig()
        assert config.profile is None
        assert config.frequency is None
        assert config.bandwidth is None
        assert config.spreading_factor is None
        assert config.coding_rate is None
        assert config.tx_power is None

    def test_eu_uk_narrow_defaults(self) -> None:
        config = RadioConfig(
            profile="EU/UK Narrow",
            frequency=869.618,
            bandwidth=62.5,
            spreading_factor=8,
            coding_rate=8,
            tx_power=22.0,
        )
        assert config.profile == "EU/UK Narrow"
        assert config.frequency == 869.618
        assert config.bandwidth == 62.5
        assert config.spreading_factor == 8
        assert config.coding_rate == 8
        assert config.tx_power == 22.0

    def test_custom_float_values(self) -> None:
        config = RadioConfig(
            profile="US 915",
            frequency=915.0,
            bandwidth=125.0,
            spreading_factor=7,
            coding_rate=5,
            tx_power=30.0,
        )
        assert config.frequency == 915.0
        assert config.tx_power == 30.0

    def test_from_config_string_does_not_exist(self) -> None:
        assert not hasattr(RadioConfig, "from_config_string")


class TestRadioConfigFormatForDisplay:
    """Tests for RadioConfig.format_for_display()."""

    def test_full_config_formatting(self) -> None:
        config = RadioConfig(
            profile="EU/UK Narrow",
            frequency=869.618,
            bandwidth=62.5,
            spreading_factor=8,
            coding_rate=8,
            tx_power=22.0,
        )
        result = config.format_for_display()

        assert result["profile"] == "EU/UK Narrow"
        assert result["frequency"] == "869.618MHz"
        assert result["bandwidth"] == "62.5kHz"
        assert result["spreading_factor"] == 8
        assert result["coding_rate"] == 8
        assert result["tx_power"] == "22dBm"

    def test_trailing_zeros_stripped(self) -> None:
        config = RadioConfig(
            profile="Test",
            frequency=915.0,
            bandwidth=125.0,
            spreading_factor=7,
            coding_rate=5,
            tx_power=30.0,
        )
        result = config.format_for_display()

        assert result["frequency"] == "915MHz"
        assert result["bandwidth"] == "125kHz"
        assert result["tx_power"] == "30dBm"

    def test_none_values_return_none(self) -> None:
        config = RadioConfig()
        result = config.format_for_display()

        assert result["profile"] is None
        assert result["frequency"] is None
        assert result["bandwidth"] is None
        assert result["spreading_factor"] is None
        assert result["coding_rate"] is None
        assert result["tx_power"] is None
