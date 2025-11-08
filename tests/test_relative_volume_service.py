"""
Unit tests for RelativeVolumeService

Tests relative volume calculation, ranking, filtering, and error handling.
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import Mock, MagicMock, patch
from src.stocks.services.relative_volume_service import RelativeVolumeService
from src.core.constants import (
    CONFIG_MIN_RELATIVE_VOLUME,
    CONFIG_RELATIVE_VOLUME_LOOKBACK,
    CONFIG_TOP_N_STOCKS
)


class TestRelativeVolumeServiceInitialization:
    """Test RelativeVolumeService initialization"""

    def test_valid_initialization(self):
        """Test successful initialization with valid context"""
        # Arrange
        mock_context = Mock()
        mock_context.state_manager = Mock()
        mock_context.database_manager = Mock()

        # Act
        service = RelativeVolumeService(mock_context)

        # Assert
        assert service.state_manager == mock_context.state_manager
        assert service.database_manager == mock_context.database_manager
        assert service.application_context == mock_context

    def test_null_context_raises_error(self):
        """Test that None context raises ValueError"""
        # Act & Assert
        with pytest.raises(ValueError, match="application_context is REQUIRED"):
            RelativeVolumeService(None)


class TestRelativeVolumeCalculation:
    """Test relative volume calculation logic"""

    def setup_method(self):
        """Set up test fixtures"""
        # Create mock context
        self.mock_context = Mock()
        self.mock_state_manager = Mock()
        self.mock_database_manager = Mock()

        self.mock_context.state_manager = self.mock_state_manager
        self.mock_context.database_manager = self.mock_database_manager

        # Configure lookback period
        self.mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_RELATIVE_VOLUME_LOOKBACK: 14,
            CONFIG_MIN_RELATIVE_VOLUME: 1.0,
            CONFIG_TOP_N_STOCKS: 5
        }.get(key)

        self.service = RelativeVolumeService(self.mock_context)

    def test_valid_relative_volume_calculation(self):
        """Test relative volume calculation with valid data"""
        # Arrange
        symbol = "AAPL"
        current_volume = 2000000
        historical_volumes = [1000000] * 14  # 14 days of 1M volume

        # Mock database query
        mock_session = Mock()
        mock_ranges = []
        for vol in historical_volumes:
            mock_range = Mock()
            mock_range.volume = vol
            mock_ranges.append(mock_range)

        mock_session.query.return_value.filter.return_value.all.return_value = mock_ranges
        self.mock_database_manager.get_session.return_value = mock_session

        # Act
        rv = self.service.calculate_relative_volume(symbol, current_volume)

        # Assert
        # Expected: 2,000,000 / 1,000,000 = 2.0x
        assert rv == pytest.approx(2.0, rel=1e-6)

    def test_missing_symbol_raises_error(self):
        """Test that missing symbol raises ValueError"""
        # Act & Assert
        with pytest.raises(ValueError, match="symbol is REQUIRED"):
            self.service.calculate_relative_volume("", 1000000)

        with pytest.raises(ValueError, match="symbol is REQUIRED"):
            self.service.calculate_relative_volume(None, 1000000)

    def test_invalid_current_volume_raises_error(self):
        """Test that invalid current_volume raises ValueError"""
        # Test None
        with pytest.raises(ValueError, match="current_volume must be non-negative"):
            self.service.calculate_relative_volume("AAPL", None)

        # Test negative
        with pytest.raises(ValueError, match="current_volume must be non-negative"):
            self.service.calculate_relative_volume("AAPL", -1000)

    def test_missing_lookback_config_raises_error(self):
        """Test that missing RELATIVE_VOLUME_LOOKBACK config raises ValueError"""
        # Arrange - Clear side_effect first, then set return_value
        self.mock_state_manager.get_config_value.side_effect = None
        self.mock_state_manager.get_config_value.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="RELATIVE_VOLUME_LOOKBACK is REQUIRED"):
            self.service.calculate_relative_volume("AAPL", 1000000)

    def test_invalid_lookback_config_raises_error(self):
        """Test that invalid RELATIVE_VOLUME_LOOKBACK raises ValueError"""
        # Arrange - Test negative lookback
        self.mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_RELATIVE_VOLUME_LOOKBACK: -5,
            CONFIG_MIN_RELATIVE_VOLUME: 1.0,
            CONFIG_TOP_N_STOCKS: 5
        }.get(key)

        # Act & Assert
        with pytest.raises(ValueError, match="RELATIVE_VOLUME_LOOKBACK must be positive"):
            self.service.calculate_relative_volume("AAPL", 1000000)

    def test_no_historical_data_raises_error(self):
        """Test that no historical data raises RuntimeError"""
        # Arrange - Mock empty query result
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        self.mock_database_manager.get_session.return_value = mock_session

        # Act & Assert
        with pytest.raises(RuntimeError, match="No historical opening range data found"):
            self.service.calculate_relative_volume("AAPL", 1000000)

    def test_zero_average_volume_returns_zero(self):
        """Test that zero average volume returns 0.0 (edge case)"""
        # Arrange - Mock historical data with all zeros
        mock_session = Mock()
        mock_ranges = []
        for _ in range(14):
            mock_range = Mock()
            mock_range.volume = 0
            mock_ranges.append(mock_range)

        mock_session.query.return_value.filter.return_value.all.return_value = mock_ranges
        self.mock_database_manager.get_session.return_value = mock_session

        # Act
        rv = self.service.calculate_relative_volume("AAPL", 1000000)

        # Assert
        assert rv == 0.0

    def test_varying_historical_volumes(self):
        """Test relative volume with varying historical data"""
        # Arrange
        symbol = "AAPL"
        current_volume = 3000000
        # Varying historical volumes: avg = (2M * 7 + 1M * 7) / 14 = 1.5M
        historical_volumes = [2000000] * 7 + [1000000] * 7

        mock_session = Mock()
        mock_ranges = []
        for vol in historical_volumes:
            mock_range = Mock()
            mock_range.volume = vol
            mock_ranges.append(mock_range)

        mock_session.query.return_value.filter.return_value.all.return_value = mock_ranges
        self.mock_database_manager.get_session.return_value = mock_session

        # Act
        rv = self.service.calculate_relative_volume(symbol, current_volume)

        # Assert
        # Expected: 3,000,000 / 1,500,000 = 2.0x
        assert rv == pytest.approx(2.0, rel=1e-6)


class TestRankingAndFiltering:
    """Test ranking and filtering functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_context = Mock()
        self.mock_state_manager = Mock()
        self.mock_database_manager = Mock()

        self.mock_context.state_manager = self.mock_state_manager
        self.mock_context.database_manager = self.mock_database_manager

        # Configure with standard values
        self.mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_RELATIVE_VOLUME_LOOKBACK: 14,
            CONFIG_MIN_RELATIVE_VOLUME: 1.0,
            CONFIG_TOP_N_STOCKS: 3
        }.get(key)

        self.service = RelativeVolumeService(self.mock_context)

    def test_valid_ranking_and_filtering(self):
        """Test ranking and filtering with valid candidates"""
        # Arrange
        candidates = [
            {'symbol': 'AAPL', 'volume': 3000000},
            {'symbol': 'TSLA', 'volume': 2500000},
            {'symbol': 'MSFT', 'volume': 2000000},
            {'symbol': 'GOOGL', 'volume': 1000000},
            {'symbol': 'AMZN', 'volume': 500000},
        ]

        # Mock relative volume calculations (higher for first 3)
        def mock_calculate_rv(symbol, volume):
            rv_map = {
                'AAPL': 3.0,
                'TSLA': 2.5,
                'MSFT': 2.0,
                'GOOGL': 1.5,
                'AMZN': 0.5  # Below threshold
            }
            return rv_map[symbol]

        self.service.calculate_relative_volume = Mock(side_effect=mock_calculate_rv)

        # Act
        result = self.service.rank_by_relative_volume(candidates)

        # Assert
        assert len(result) == 3  # Top 3 (AMZN filtered out by min threshold)
        assert result[0]['symbol'] == 'AAPL'
        assert result[0]['rank'] == 1
        assert result[0]['relative_volume'] == 3.0
        assert result[1]['symbol'] == 'TSLA'
        assert result[1]['rank'] == 2
        assert result[2]['symbol'] == 'MSFT'
        assert result[2]['rank'] == 3

    def test_empty_candidates_returns_empty_list(self):
        """Test that empty candidates list returns empty list"""
        # Act
        result = self.service.rank_by_relative_volume([])

        # Assert
        assert result == []

    def test_none_candidates_raises_error(self):
        """Test that None candidates raises ValueError"""
        # Act & Assert
        with pytest.raises(ValueError, match="candidates is REQUIRED"):
            self.service.rank_by_relative_volume(None)

    def test_missing_symbol_skipped(self):
        """Test that candidates missing symbol are skipped"""
        # Arrange
        candidates = [
            {'symbol': 'AAPL', 'volume': 3000000},
            {'volume': 2000000},  # Missing symbol
            {'symbol': 'TSLA', 'volume': 2500000},
        ]

        def mock_calculate_rv(symbol, volume):
            return 2.0

        self.service.calculate_relative_volume = Mock(side_effect=mock_calculate_rv)

        # Act
        result = self.service.rank_by_relative_volume(candidates)

        # Assert
        assert len(result) == 2
        assert all('symbol' in c for c in result)

    def test_invalid_volume_skipped(self):
        """Test that candidates with invalid volume are skipped"""
        # Arrange
        candidates = [
            {'symbol': 'AAPL', 'volume': 3000000},
            {'symbol': 'INVALID1', 'volume': None},
            {'symbol': 'INVALID2', 'volume': 0},
            {'symbol': 'INVALID3', 'volume': -1000},
            {'symbol': 'TSLA', 'volume': 2500000},
        ]

        def mock_calculate_rv(symbol, volume):
            return 2.0

        self.service.calculate_relative_volume = Mock(side_effect=mock_calculate_rv)

        # Act
        result = self.service.rank_by_relative_volume(candidates)

        # Assert
        assert len(result) == 2
        assert result[0]['symbol'] == 'AAPL'
        assert result[1]['symbol'] == 'TSLA'

    def test_missing_min_relative_volume_config_raises_error(self):
        """Test that missing MIN_RELATIVE_VOLUME config raises ValueError"""
        # Arrange
        candidates = [{'symbol': 'AAPL', 'volume': 1000000}]
        self.mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_RELATIVE_VOLUME_LOOKBACK: 14,
            CONFIG_MIN_RELATIVE_VOLUME: None,  # Missing
            CONFIG_TOP_N_STOCKS: 3
        }.get(key)

        # Act & Assert
        with pytest.raises(ValueError, match="MIN_RELATIVE_VOLUME is REQUIRED"):
            self.service.rank_by_relative_volume(candidates)

    def test_missing_top_n_config_raises_error(self):
        """Test that missing TOP_N_STOCKS config raises ValueError"""
        # Arrange
        candidates = [{'symbol': 'AAPL', 'volume': 1000000}]
        self.mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_RELATIVE_VOLUME_LOOKBACK: 14,
            CONFIG_MIN_RELATIVE_VOLUME: 1.0,
            CONFIG_TOP_N_STOCKS: None  # Missing
        }.get(key)

        # Act & Assert
        with pytest.raises(ValueError, match="TOP_N_STOCKS is REQUIRED"):
            self.service.rank_by_relative_volume(candidates)

    def test_minimum_threshold_filtering(self):
        """Test that candidates below minimum threshold are filtered out"""
        # Arrange
        candidates = [
            {'symbol': 'AAPL', 'volume': 3000000},  # RV = 3.0
            {'symbol': 'TSLA', 'volume': 2000000},  # RV = 2.0
            {'symbol': 'LOW', 'volume': 500000},    # RV = 0.5, below threshold
        ]

        def mock_calculate_rv(symbol, volume):
            rv_map = {'AAPL': 3.0, 'TSLA': 2.0, 'LOW': 0.5}
            return rv_map[symbol]

        self.service.calculate_relative_volume = Mock(side_effect=mock_calculate_rv)

        # Act
        result = self.service.rank_by_relative_volume(candidates)

        # Assert
        assert len(result) == 2
        assert 'LOW' not in [c['symbol'] for c in result]

    def test_top_n_filtering(self):
        """Test that only top N candidates are returned"""
        # Arrange - 5 candidates but top_n = 3
        candidates = [
            {'symbol': 'AAPL', 'volume': 5000000},   # RV = 5.0
            {'symbol': 'TSLA', 'volume': 4000000},   # RV = 4.0
            {'symbol': 'MSFT', 'volume': 3000000},   # RV = 3.0
            {'symbol': 'GOOGL', 'volume': 2000000},  # RV = 2.0
            {'symbol': 'AMZN', 'volume': 1500000},   # RV = 1.5
        ]

        def mock_calculate_rv(symbol, volume):
            rv_map = {'AAPL': 5.0, 'TSLA': 4.0, 'MSFT': 3.0, 'GOOGL': 2.0, 'AMZN': 1.5}
            return rv_map[symbol]

        self.service.calculate_relative_volume = Mock(side_effect=mock_calculate_rv)

        # Act
        result = self.service.rank_by_relative_volume(candidates)

        # Assert
        assert len(result) == 3  # Only top 3
        assert result[0]['symbol'] == 'AAPL'
        assert result[1]['symbol'] == 'TSLA'
        assert result[2]['symbol'] == 'MSFT'

    def test_calculation_error_skips_candidate(self):
        """Test that candidates with calculation errors are skipped"""
        # Arrange
        candidates = [
            {'symbol': 'AAPL', 'volume': 3000000},
            {'symbol': 'ERROR', 'volume': 2000000},
            {'symbol': 'TSLA', 'volume': 2500000},
        ]

        def mock_calculate_rv(symbol, volume):
            if symbol == 'ERROR':
                raise RuntimeError("No historical data")
            return 2.0

        self.service.calculate_relative_volume = Mock(side_effect=mock_calculate_rv)

        # Act
        result = self.service.rank_by_relative_volume(candidates)

        # Assert
        assert len(result) == 2
        assert 'ERROR' not in [c['symbol'] for c in result]

    def test_custom_volume_key(self):
        """Test ranking with custom volume key"""
        # Arrange
        candidates = [
            {'symbol': 'AAPL', 'current_vol': 3000000},
            {'symbol': 'TSLA', 'current_vol': 2500000},
        ]

        def mock_calculate_rv(symbol, volume):
            return 2.0

        self.service.calculate_relative_volume = Mock(side_effect=mock_calculate_rv)

        # Act
        result = self.service.rank_by_relative_volume(candidates, volume_key='current_vol')

        # Assert
        assert len(result) == 2
        assert all('relative_volume' in c for c in result)


class TestStocksInPlayFilter:
    """Test filter_stocks_in_play functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_context = Mock()
        self.mock_state_manager = Mock()
        self.mock_database_manager = Mock()

        self.mock_context.state_manager = self.mock_state_manager
        self.mock_context.database_manager = self.mock_database_manager

        self.mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_RELATIVE_VOLUME_LOOKBACK: 14,
            CONFIG_MIN_RELATIVE_VOLUME: 1.0,
            CONFIG_TOP_N_STOCKS: 3
        }.get(key)

        self.service = RelativeVolumeService(self.mock_context)

    def test_returns_symbol_list(self):
        """Test that filter_stocks_in_play returns list of symbols"""
        # Arrange
        candidates = [
            {'symbol': 'AAPL', 'volume': 3000000},
            {'symbol': 'TSLA', 'volume': 2500000},
            {'symbol': 'MSFT', 'volume': 2000000},
        ]

        def mock_calculate_rv(symbol, volume):
            return 2.0

        self.service.calculate_relative_volume = Mock(side_effect=mock_calculate_rv)

        # Act
        result = self.service.filter_stocks_in_play(candidates)

        # Assert
        assert result == ['AAPL', 'TSLA', 'MSFT']

    def test_empty_candidates_returns_empty_list(self):
        """Test that empty candidates returns empty list"""
        # Act
        result = self.service.filter_stocks_in_play([])

        # Assert
        assert result == []


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_context = Mock()
        self.mock_state_manager = Mock()
        self.mock_database_manager = Mock()

        self.mock_context.state_manager = self.mock_state_manager
        self.mock_context.database_manager = self.mock_database_manager

        self.mock_state_manager.get_config_value.side_effect = lambda key: {
            CONFIG_RELATIVE_VOLUME_LOOKBACK: 14,
            CONFIG_MIN_RELATIVE_VOLUME: 1.0,
            CONFIG_TOP_N_STOCKS: 3
        }.get(key)

        self.service = RelativeVolumeService(self.mock_context)

    def test_tied_relative_volumes_maintain_order(self):
        """Test that tied relative volumes maintain stable sort order"""
        # Arrange
        candidates = [
            {'symbol': 'AAPL', 'volume': 2000000},
            {'symbol': 'TSLA', 'volume': 2000000},
            {'symbol': 'MSFT', 'volume': 2000000},
        ]

        def mock_calculate_rv(symbol, volume):
            return 2.0  # All same

        self.service.calculate_relative_volume = Mock(side_effect=mock_calculate_rv)

        # Act
        result = self.service.rank_by_relative_volume(candidates)

        # Assert
        assert len(result) == 3
        # All should have same relative volume
        assert all(c['relative_volume'] == 2.0 for c in result)
        # All should have ranks 1, 2, 3
        assert [c['rank'] for c in result] == [1, 2, 3]

    def test_very_high_relative_volume(self):
        """Test handling of very high relative volume (100x)"""
        # Arrange
        symbol = "AAPL"
        current_volume = 100000000
        historical_volumes = [1000000] * 14

        mock_session = Mock()
        mock_ranges = []
        for vol in historical_volumes:
            mock_range = Mock()
            mock_range.volume = vol
            mock_ranges.append(mock_range)

        mock_session.query.return_value.filter.return_value.all.return_value = mock_ranges
        self.mock_database_manager.get_session.return_value = mock_session

        # Act
        rv = self.service.calculate_relative_volume(symbol, current_volume)

        # Assert
        assert rv == pytest.approx(100.0, rel=1e-6)

    def test_very_low_relative_volume(self):
        """Test handling of very low relative volume (0.1x)"""
        # Arrange
        symbol = "AAPL"
        current_volume = 100000
        historical_volumes = [1000000] * 14

        mock_session = Mock()
        mock_ranges = []
        for vol in historical_volumes:
            mock_range = Mock()
            mock_range.volume = vol
            mock_ranges.append(mock_range)

        mock_session.query.return_value.filter.return_value.all.return_value = mock_ranges
        self.mock_database_manager.get_session.return_value = mock_session

        # Act
        rv = self.service.calculate_relative_volume(symbol, current_volume)

        # Assert
        assert rv == pytest.approx(0.1, rel=1e-6)

    def test_partial_historical_data(self):
        """Test calculation with less than full lookback period"""
        # Arrange
        symbol = "AAPL"
        current_volume = 2000000
        # Only 7 days of data instead of 14
        historical_volumes = [1000000] * 7

        mock_session = Mock()
        mock_ranges = []
        for vol in historical_volumes:
            mock_range = Mock()
            mock_range.volume = vol
            mock_ranges.append(mock_range)

        mock_session.query.return_value.filter.return_value.all.return_value = mock_ranges
        self.mock_database_manager.get_session.return_value = mock_session

        # Act
        rv = self.service.calculate_relative_volume(symbol, current_volume)

        # Assert
        # Should calculate with available data
        assert rv == pytest.approx(2.0, rel=1e-6)

    def test_candidates_missing_volume_field(self):
        """Test handling of candidates with missing volume field"""
        # Arrange
        candidates = [
            {'symbol': 'AAPL', 'volume': 3000000},
            {'symbol': 'MISSING'},  # No volume field
            {'symbol': 'TSLA', 'volume': 2500000},
        ]

        def mock_calculate_rv(symbol, volume):
            return 2.0

        self.service.calculate_relative_volume = Mock(side_effect=mock_calculate_rv)

        # Act
        result = self.service.rank_by_relative_volume(candidates)

        # Assert
        assert len(result) == 2
        assert 'MISSING' not in [c['symbol'] for c in result]
