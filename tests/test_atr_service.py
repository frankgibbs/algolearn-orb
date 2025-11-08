"""
Unit tests for ATRService

Tests ATR calculation, caching, configuration validation, and error handling.
"""
import pytest
import pandas as pd
from datetime import datetime, date
from unittest.mock import Mock, MagicMock, patch
from src.stocks.services.atr_service import ATRService
from src.core.constants import CONFIG_ATR_PERIOD, CONFIG_ATR_STOP_MULTIPLIER


class TestATRServiceInitialization:
    """Test ATRService initialization"""

    def test_valid_initialization(self):
        """Test successful initialization with valid context"""
        # Arrange
        mock_context = Mock()
        mock_context.client = Mock()
        mock_context.state_manager = Mock()

        # Act
        service = ATRService(mock_context)

        # Assert
        assert service.client == mock_context.client
        assert service.state_manager == mock_context.state_manager
        assert service.application_context == mock_context

    def test_null_context_raises_error(self):
        """Test that None context raises ValueError"""
        # Act & Assert
        with pytest.raises(ValueError, match="application_context is REQUIRED"):
            ATRService(None)


class TestATRCalculation:
    """Test ATR calculation logic"""

    def setup_method(self):
        """Set up test fixtures"""
        # Clear cache before each test
        ATRService.clear_cache()

        # Create mock context
        self.mock_context = Mock()
        self.mock_client = Mock()
        self.mock_state_manager = Mock()

        self.mock_context.client = self.mock_client
        self.mock_context.state_manager = self.mock_state_manager

        # Configure ATR period
        self.mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_ATR_PERIOD: 14,
            CONFIG_ATR_STOP_MULTIPLIER: 0.10
        }.get(key)

        self.service = ATRService(self.mock_context)

    def test_valid_atr_calculation(self):
        """Test ATR calculation with valid historical data"""
        # Arrange
        symbol = "AAPL"

        # Create mock bars with known values for predictable ATR
        # 15 bars (14 period + 1 for previous close)
        bars_data = []
        for i in range(15):
            bars_data.append({
                'date': pd.Timestamp('2024-01-01') + pd.Timedelta(days=i),
                'open': 100.0,
                'high': 102.0 + i * 0.1,  # Gradually increasing volatility
                'low': 98.0 - i * 0.1,
                'close': 100.0,
                'volume': 1000000
            })

        mock_bars = pd.DataFrame(bars_data)

        # Mock IB client responses
        self.mock_client.get_stock_contract.return_value = Mock()
        self.mock_client.get_historic_data.return_value = mock_bars

        # Act
        atr = self.service.get_atr(symbol)

        # Assert
        assert isinstance(atr, float)
        assert atr > 0
        # Verify IB client was called correctly
        self.mock_client.get_stock_contract.assert_called_once_with(symbol)
        self.mock_client.get_historic_data.assert_called_once()

    def test_atr_cache_hit(self):
        """Test that second call uses cache"""
        # Arrange
        symbol = "AAPL"
        mock_bars = self._create_valid_bars(15)

        self.mock_client.get_stock_contract.return_value = Mock()
        self.mock_client.get_historic_data.return_value = mock_bars

        # Act
        atr1 = self.service.get_atr(symbol)
        atr2 = self.service.get_atr(symbol)

        # Assert
        assert atr1 == atr2
        # IB client should only be called once (second call uses cache)
        assert self.mock_client.get_historic_data.call_count == 1

    def test_missing_symbol_raises_error(self):
        """Test that missing symbol raises ValueError"""
        # Act & Assert
        with pytest.raises(ValueError, match="symbol is REQUIRED"):
            self.service.get_atr("")

        with pytest.raises(ValueError, match="symbol is REQUIRED"):
            self.service.get_atr(None)

    def test_missing_atr_period_config_raises_error(self):
        """Test that missing ATR_PERIOD config raises ValueError"""
        # Arrange - Clear side_effect first, then set return_value
        self.mock_state_manager.get_config_value.side_effect = None
        self.mock_state_manager.get_config_value.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="ATR_PERIOD is REQUIRED"):
            self.service.get_atr("AAPL")

    def test_invalid_atr_period_raises_error(self):
        """Test that invalid ATR_PERIOD raises ValueError"""
        # Arrange - Test negative period
        self.mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_ATR_PERIOD: -5,
            CONFIG_ATR_STOP_MULTIPLIER: 0.10
        }.get(key)

        # Act & Assert
        with pytest.raises(ValueError, match="ATR_PERIOD must be positive"):
            self.service.get_atr("AAPL")

    def test_ib_timeout_raises_error(self):
        """Test that IB timeout raises TimeoutError"""
        # Arrange
        self.mock_client.get_stock_contract.return_value = Mock()
        self.mock_client.get_historic_data.return_value = None  # Timeout

        # Act & Assert
        with pytest.raises(TimeoutError, match="Timeout getting historical data"):
            self.service.get_atr("AAPL")

    def test_no_historical_data_raises_error(self):
        """Test that empty bars raises RuntimeError"""
        # Arrange
        self.mock_client.get_stock_contract.return_value = Mock()
        self.mock_client.get_historic_data.return_value = pd.DataFrame()  # Empty

        # Act & Assert
        with pytest.raises(RuntimeError, match="No historical data received"):
            self.service.get_atr("AAPL")

    def test_insufficient_data_raises_error(self):
        """Test that insufficient bars raises RuntimeError"""
        # Arrange
        mock_bars = self._create_valid_bars(5)  # Only 5 bars, need 14

        self.mock_client.get_stock_contract.return_value = Mock()
        self.mock_client.get_historic_data.return_value = mock_bars

        # Act & Assert
        with pytest.raises(RuntimeError, match="Insufficient data for 14-day ATR"):
            self.service.get_atr("AAPL")

    def test_true_range_calculation(self):
        """Test True Range calculation formula"""
        # Arrange
        symbol = "AAPL"

        # Create specific bars to verify TR calculation
        bars_data = [
            # Bar 0 (previous for TR calculation)
            {'date': pd.Timestamp('2024-01-01'), 'high': 100.0, 'low': 98.0, 'close': 99.0, 'open': 99.0, 'volume': 1000},
            # Bar 1: TR = max(high-low, high-prev_close, prev_close-low)
            #       = max(103-97=6, 103-99=4, 99-97=2) = 6
            {'date': pd.Timestamp('2024-01-02'), 'high': 103.0, 'low': 97.0, 'close': 100.0, 'open': 100.0, 'volume': 1000},
        ]

        # Add 13 more bars with simple TR values for 14-period ATR
        for i in range(13):
            bars_data.append({
                'date': pd.Timestamp('2024-01-03') + pd.Timedelta(days=i),
                'high': 102.0,
                'low': 98.0,
                'close': 100.0,
                'open': 100.0,
                'volume': 1000
            })

        mock_bars = pd.DataFrame(bars_data)

        self.mock_client.get_stock_contract.return_value = Mock()
        self.mock_client.get_historic_data.return_value = mock_bars

        # Act
        atr = self.service.get_atr(symbol)

        # Assert - ATR should be average of 14 TRs
        # First TR = 6.0, remaining 13 TRs = 4.0 each
        # Expected ATR = (6.0 + 13*4.0) / 14 = 58.0 / 14 ≈ 4.14
        assert atr > 4.0
        assert atr < 5.0

    def _create_valid_bars(self, count: int) -> pd.DataFrame:
        """Helper to create valid bars DataFrame"""
        bars_data = []
        for i in range(count):
            bars_data.append({
                'date': pd.Timestamp('2024-01-01') + pd.Timedelta(days=i),
                'open': 100.0,
                'high': 102.0,
                'low': 98.0,
                'close': 100.0,
                'volume': 1000000
            })
        return pd.DataFrame(bars_data)


class TestStopDistanceCalculation:
    """Test stop distance calculation"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_context = Mock()
        self.mock_state_manager = Mock()
        self.mock_context.state_manager = self.mock_state_manager
        self.mock_context.client = Mock()

        # Configure stop multiplier
        self.mock_state_manager.get_config_value.return_value = 0.10

        self.service = ATRService(self.mock_context)

    def test_valid_stop_distance_calculation(self):
        """Test stop distance calculation with valid inputs"""
        # Arrange
        atr_value = 2.50

        # Act
        stop_distance = self.service.calculate_stop_distance(atr_value)

        # Assert
        assert stop_distance == pytest.approx(0.25, rel=1e-6)  # 2.50 * 0.10

    def test_invalid_atr_value_raises_error(self):
        """Test that invalid ATR value raises ValueError"""
        # Test None
        with pytest.raises(ValueError, match="atr_value must be positive"):
            self.service.calculate_stop_distance(None)

        # Test negative
        with pytest.raises(ValueError, match="atr_value must be positive"):
            self.service.calculate_stop_distance(-1.0)

        # Test zero
        with pytest.raises(ValueError, match="atr_value must be positive"):
            self.service.calculate_stop_distance(0.0)

    def test_missing_stop_multiplier_config_raises_error(self):
        """Test that missing ATR_STOP_MULTIPLIER config raises ValueError"""
        # Arrange
        self.mock_state_manager.get_config_value.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="ATR_STOP_MULTIPLIER is REQUIRED"):
            self.service.calculate_stop_distance(2.50)

    def test_invalid_stop_multiplier_raises_error(self):
        """Test that invalid ATR_STOP_MULTIPLIER raises ValueError"""
        # Arrange - Test negative multiplier
        self.mock_state_manager.get_config_value.return_value = -0.10

        # Act & Assert
        with pytest.raises(ValueError, match="ATR_STOP_MULTIPLIER must be positive"):
            self.service.calculate_stop_distance(2.50)


class TestCacheManagement:
    """Test cache management functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        # Clear cache before each test
        ATRService.clear_cache()

    def test_clear_cache(self):
        """Test cache clearing"""
        # Arrange - Manually add entries to cache
        ATRService._cache[("AAPL", date.today(), 14)] = 2.50
        ATRService._cache[("TSLA", date.today(), 14)] = 5.00
        assert len(ATRService._cache) == 2

        # Act
        ATRService.clear_cache()

        # Assert
        assert len(ATRService._cache) == 0

    def test_get_cache_stats(self):
        """Test cache statistics retrieval"""
        # Arrange - Add some cache entries
        today = date.today()
        ATRService._cache[("AAPL", today, 14)] = 2.50
        ATRService._cache[("TSLA", today, 14)] = 5.00

        # Act
        stats = ATRService.get_cache_stats()

        # Assert
        assert stats['size'] == 2
        assert ("AAPL", today, 14) in stats['entries']
        assert ("TSLA", today, 14) in stats['entries']

    def test_cache_key_includes_date(self):
        """Test that cache key includes date for daily expiration"""
        # Arrange
        mock_context = Mock()
        mock_client = Mock()
        mock_state_manager = Mock()

        mock_context.client = mock_client
        mock_context.state_manager = mock_state_manager

        mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_ATR_PERIOD: 14,
            CONFIG_ATR_STOP_MULTIPLIER: 0.10
        }.get(key)

        service = ATRService(mock_context)

        # Create mock bars
        bars_data = []
        for i in range(15):
            bars_data.append({
                'date': pd.Timestamp('2024-01-01') + pd.Timedelta(days=i),
                'open': 100.0,
                'high': 102.0,
                'low': 98.0,
                'close': 100.0,
                'volume': 1000000
            })
        mock_bars = pd.DataFrame(bars_data)

        mock_client.get_stock_contract.return_value = Mock()
        mock_client.get_historic_data.return_value = mock_bars

        # Act - Calculate ATR
        service.get_atr("AAPL")

        # Assert - Check cache key structure
        stats = ATRService.get_cache_stats()
        assert stats['size'] == 1
        cache_key = stats['entries'][0]
        assert cache_key[0] == "AAPL"  # Symbol
        assert isinstance(cache_key[1], date)  # Date
        assert cache_key[2] == 14  # Period

    def test_cache_isolation_between_dates(self):
        """Test that cache entries are date-specific"""
        # Arrange - Manually add entries for different dates
        today = date.today()
        yesterday = date(2024, 1, 1)

        ATRService._cache[("AAPL", today, 14)] = 2.50
        ATRService._cache[("AAPL", yesterday, 14)] = 2.60

        # Assert - Both entries coexist
        assert len(ATRService._cache) == 2
        assert ATRService._cache[("AAPL", today, 14)] == 2.50
        assert ATRService._cache[("AAPL", yesterday, 14)] == 2.60


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def setup_method(self):
        """Set up test fixtures"""
        ATRService.clear_cache()

        self.mock_context = Mock()
        self.mock_client = Mock()
        self.mock_state_manager = Mock()

        self.mock_context.client = self.mock_client
        self.mock_context.state_manager = self.mock_state_manager

        self.mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_ATR_PERIOD: 14,
            CONFIG_ATR_STOP_MULTIPLIER: 0.10
        }.get(key)

        self.service = ATRService(self.mock_context)

    def test_very_low_volatility_stock(self):
        """Test ATR calculation for low volatility (narrow ranges)"""
        # Arrange - Create bars with very tight ranges
        bars_data = []
        for i in range(15):
            bars_data.append({
                'date': pd.Timestamp('2024-01-01') + pd.Timedelta(days=i),
                'open': 100.0,
                'high': 100.01,  # Very tight range
                'low': 99.99,
                'close': 100.0,
                'volume': 1000000
            })

        mock_bars = pd.DataFrame(bars_data)
        self.mock_client.get_stock_contract.return_value = Mock()
        self.mock_client.get_historic_data.return_value = mock_bars

        # Act
        atr = self.service.get_atr("AAPL")

        # Assert - ATR should be very small but positive
        assert atr > 0
        assert atr < 0.1

    def test_very_high_volatility_stock(self):
        """Test ATR calculation for high volatility (wide ranges)"""
        # Arrange - Create bars with very wide ranges
        bars_data = []
        for i in range(15):
            bars_data.append({
                'date': pd.Timestamp('2024-01-01') + pd.Timedelta(days=i),
                'open': 100.0,
                'high': 110.0,  # Very wide range
                'low': 90.0,
                'close': 100.0,
                'volume': 1000000
            })

        mock_bars = pd.DataFrame(bars_data)
        self.mock_client.get_stock_contract.return_value = Mock()
        self.mock_client.get_historic_data.return_value = mock_bars

        # Act
        atr = self.service.get_atr("AAPL")

        # Assert - ATR should be large
        assert atr > 10.0

    def test_gap_up_true_range(self):
        """Test True Range calculation with gap up"""
        # Arrange - Create bars with gap up
        bars_data = [
            # Previous day close at 100
            {'date': pd.Timestamp('2024-01-01'), 'high': 100.0, 'low': 98.0, 'close': 100.0, 'open': 99.0, 'volume': 1000},
            # Gap up to 110 (high-prev_close should be max)
            {'date': pd.Timestamp('2024-01-02'), 'high': 112.0, 'low': 110.0, 'close': 111.0, 'open': 110.0, 'volume': 1000},
        ]

        # Add more bars
        for i in range(13):
            bars_data.append({
                'date': pd.Timestamp('2024-01-03') + pd.Timedelta(days=i),
                'high': 102.0,
                'low': 98.0,
                'close': 100.0,
                'open': 100.0,
                'volume': 1000
            })

        mock_bars = pd.DataFrame(bars_data)
        self.mock_client.get_stock_contract.return_value = Mock()
        self.mock_client.get_historic_data.return_value = mock_bars

        # Act
        atr = self.service.get_atr("AAPL")

        # Assert - First TR should capture the gap
        # TR = max(112-110=2, 112-100=12, 110-100=10) = 12
        # ATR should be influenced by this large TR
        assert atr > 4.0  # Should be elevated due to gap
