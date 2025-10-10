"""
Option Strategy Selection Based on Volatility Analysis
Based on concepts from Natenberg's Option Volatility and Pricing Chapter 6

This module implements volatility-based option strategy selection using:
1. Historical vs Implied Volatility comparison
2. Volatility forecasting
3. Strategy recommendation engine
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import warnings
warnings.filterwarnings('ignore')


class VolatilityRegime(Enum):
    """Volatility market regimes"""
    LOW = "Low Volatility"
    NORMAL = "Normal Volatility"
    HIGH = "High Volatility"
    EXTREMELY_HIGH = "Extremely High Volatility"


class StrategyType(Enum):
    """Option strategy types based on volatility outlook"""
    # Long Volatility Strategies (benefit from increasing volatility)
    LONG_STRADDLE = "Long Straddle"
    LONG_STRANGLE = "Long Strangle"
    CALENDAR_SPREAD = "Calendar Spread"
    DIAGONAL_SPREAD = "Diagonal Spread"

    # Short Volatility Strategies (benefit from decreasing volatility)
    SHORT_STRADDLE = "Short Straddle"
    SHORT_STRANGLE = "Short Strangle"
    IRON_CONDOR = "Iron Condor"
    IRON_BUTTERFLY = "Iron Butterfly"
    COVERED_CALL = "Covered Call"
    CASH_SECURED_PUT = "Cash Secured Put"

    # Directional Strategies with Volatility Edge
    LONG_CALL = "Long Call"
    LONG_PUT = "Long Put"
    BULL_CALL_SPREAD = "Bull Call Spread"
    BEAR_PUT_SPREAD = "Bear Put Spread"

    # Neutral Strategies
    RATIO_SPREAD = "Ratio Spread"
    BUTTERFLY_SPREAD = "Butterfly Spread"


@dataclass
class VolatilityMetrics:
    """Container for volatility analysis metrics"""
    historical_volatility: float
    implied_volatility: float
    iv_percentile: float  # Where current IV ranks historically
    hv_percentile: float  # Where current HV ranks historically
    iv_hv_ratio: float  # IV / HV ratio
    term_structure_slope: float  # Front month vs back month IV
    volatility_forecast: float
    regime: VolatilityRegime


@dataclass
class StrategyRecommendation:
    """Option strategy recommendation with rationale"""
    strategy: StrategyType
    confidence: float  # 0-1 confidence score
    rationale: str
    entry_criteria: Dict[str, float]
    risk_metrics: Dict[str, float]


class VolatilityAnalyzer:
    """
    Analyzes historical and implied volatility to determine optimal option strategies
    Core concepts from Natenberg Chapter 6
    """

    def __init__(self, lookback_days: int = 252):
        self.lookback_days = lookback_days

    def calculate_historical_volatility(self,
                                       prices: pd.Series,
                                       periods: List[int] = [10, 20, 30, 60]) -> pd.DataFrame:
        """
        Calculate historical volatility over multiple periods

        Args:
            prices: Series of stock prices
            periods: List of lookback periods in days

        Returns:
            DataFrame with HV for each period
        """
        returns = np.log(prices / prices.shift(1))
        hv_data = {}

        for period in periods:
            # Annualized historical volatility
            hv = returns.rolling(window=period).std() * np.sqrt(252)
            hv_data[f'HV_{period}'] = hv

        return pd.DataFrame(hv_data)

    def calculate_iv_metrics(self,
                             current_iv: float,
                             iv_history: pd.Series,
                             term_structure: Optional[Dict[int, float]] = None) -> Dict:
        """
        Calculate implied volatility metrics

        Args:
            current_iv: Current implied volatility
            iv_history: Historical IV series
            term_structure: IV by expiration (days to expiry: IV)

        Returns:
            Dictionary of IV metrics
        """
        iv_percentile = stats.percentileofscore(iv_history.dropna(), current_iv)
        iv_mean = iv_history.mean()
        iv_std = iv_history.std()
        iv_zscore = (current_iv - iv_mean) / iv_std

        metrics = {
            'current_iv': current_iv,
            'iv_percentile': iv_percentile,
            'iv_mean': iv_mean,
            'iv_zscore': iv_zscore,
            'iv_1std_range': (iv_mean - iv_std, iv_mean + iv_std),
            'iv_2std_range': (iv_mean - 2*iv_std, iv_mean + 2*iv_std)
        }

        # Calculate term structure slope if provided
        if term_structure and len(term_structure) >= 2:
            days = sorted(term_structure.keys())
            front_iv = term_structure[days[0]]
            back_iv = term_structure[days[-1]]
            metrics['term_structure_slope'] = (back_iv - front_iv) / front_iv
        else:
            metrics['term_structure_slope'] = 0

        return metrics

    def forecast_volatility(self,
                           historical_vol: pd.Series,
                           method: str = 'ewma') -> float:
        """
        Forecast future volatility using various methods

        Args:
            historical_vol: Series of historical volatility
            method: 'ewma', 'garch', or 'mean_reversion'

        Returns:
            Forecasted volatility
        """
        if method == 'ewma':
            # Exponentially weighted moving average
            alpha = 0.94  # RiskMetrics standard
            forecast = historical_vol.ewm(alpha=alpha, adjust=False).mean().iloc[-1]

        elif method == 'mean_reversion':
            # Mean reversion forecast
            long_term_mean = historical_vol.mean()
            current = historical_vol.iloc[-1]
            reversion_speed = 0.1  # Mean reversion parameter
            forecast = current + reversion_speed * (long_term_mean - current)

        else:  # Simple average
            forecast = historical_vol.rolling(window=20).mean().iloc[-1]

        return forecast

    def determine_volatility_regime(self, metrics: VolatilityMetrics) -> VolatilityRegime:
        """
        Classify current volatility regime based on metrics
        """
        if metrics.iv_percentile < 25:
            return VolatilityRegime.LOW
        elif metrics.iv_percentile < 75:
            return VolatilityRegime.NORMAL
        elif metrics.iv_percentile < 90:
            return VolatilityRegime.HIGH
        else:
            return VolatilityRegime.EXTREMELY_HIGH

    def analyze_volatility(self,
                          prices: pd.Series,
                          current_iv: float,
                          iv_history: pd.Series,
                          term_structure: Optional[Dict[int, float]] = None) -> VolatilityMetrics:
        """
        Comprehensive volatility analysis

        Args:
            prices: Historical stock prices
            current_iv: Current implied volatility
            iv_history: Historical implied volatility series
            term_structure: Optional IV term structure

        Returns:
            VolatilityMetrics object with complete analysis
        """
        # Calculate historical volatility
        hv_df = self.calculate_historical_volatility(prices)
        current_hv = hv_df['HV_20'].iloc[-1]  # 20-day HV as baseline

        # Calculate HV percentile
        hv_percentile = stats.percentileofscore(hv_df['HV_20'].dropna(), current_hv)

        # Calculate IV metrics
        iv_metrics = self.calculate_iv_metrics(current_iv, iv_history, term_structure)

        # Forecast volatility
        vol_forecast = self.forecast_volatility(hv_df['HV_20'].dropna())

        # Create metrics object
        metrics = VolatilityMetrics(
            historical_volatility=current_hv,
            implied_volatility=current_iv,
            iv_percentile=iv_metrics['iv_percentile'],
            hv_percentile=hv_percentile,
            iv_hv_ratio=current_iv / current_hv if current_hv > 0 else 1,
            term_structure_slope=iv_metrics['term_structure_slope'],
            volatility_forecast=vol_forecast,
            regime=VolatilityRegime.NORMAL  # Will be updated
        )

        # Determine regime
        metrics.regime = self.determine_volatility_regime(metrics)

        return metrics


class OptionStrategySelector:
    """
    Selects optimal option strategies based on volatility analysis
    Implements strategy selection logic from Natenberg's framework
    """

    def __init__(self):
        self.strategy_rules = self._initialize_strategy_rules()

    def _initialize_strategy_rules(self) -> Dict:
        """
        Define strategy selection rules based on volatility conditions
        These rules implement Natenberg's strategy selection framework
        """
        return {
            # Buy volatility when IV < HV (options underpriced)
            'long_volatility': {
                'condition': lambda m: m.iv_hv_ratio < 0.9 and m.iv_percentile < 30,
                'strategies': [StrategyType.LONG_STRADDLE, StrategyType.LONG_STRANGLE],
                'rationale': "IV trading below HV - options appear underpriced"
            },

            # Sell volatility when IV > HV (options overpriced)
            'short_volatility': {
                'condition': lambda m: m.iv_hv_ratio > 1.2 and m.iv_percentile > 70,
                'strategies': [StrategyType.IRON_CONDOR, StrategyType.SHORT_STRANGLE],
                'rationale': "IV trading above HV - options appear overpriced"
            },

            # Calendar spreads when term structure is steep
            'calendar_spread': {
                'condition': lambda m: abs(m.term_structure_slope) > 0.1,
                'strategies': [StrategyType.CALENDAR_SPREAD, StrategyType.DIAGONAL_SPREAD],
                'rationale': "Steep volatility term structure - exploit time decay differential"
            },

            # Directional with low IV
            'directional_long': {
                'condition': lambda m: m.iv_percentile < 25,
                'strategies': [StrategyType.LONG_CALL, StrategyType.LONG_PUT],
                'rationale': "Low IV environment - cheap option premium for directional plays"
            },

            # Income strategies in high IV
            'income_generation': {
                'condition': lambda m: m.iv_percentile > 80 and m.regime != VolatilityRegime.EXTREMELY_HIGH,
                'strategies': [StrategyType.COVERED_CALL, StrategyType.CASH_SECURED_PUT],
                'rationale': "High IV with controlled risk - premium collection strategies"
            },

            # Spreads in normal volatility
            'vertical_spreads': {
                'condition': lambda m: 30 <= m.iv_percentile <= 70,
                'strategies': [StrategyType.BULL_CALL_SPREAD, StrategyType.BEAR_PUT_SPREAD],
                'rationale': "Normal volatility - use spreads to reduce cost and define risk"
            }
        }

    def select_strategies(self,
                         metrics: VolatilityMetrics,
                         directional_bias: str = 'neutral') -> List[StrategyRecommendation]:
        """
        Select appropriate option strategies based on volatility metrics

        Args:
            metrics: Volatility analysis metrics
            directional_bias: 'bullish', 'bearish', or 'neutral'

        Returns:
            List of strategy recommendations
        """
        recommendations = []

        # Check each strategy rule
        for rule_name, rule in self.strategy_rules.items():
            if rule['condition'](metrics):
                for strategy in rule['strategies']:
                    # Filter based on directional bias
                    if self._is_strategy_compatible(strategy, directional_bias):
                        confidence = self._calculate_confidence(metrics, strategy)

                        recommendation = StrategyRecommendation(
                            strategy=strategy,
                            confidence=confidence,
                            rationale=rule['rationale'],
                            entry_criteria=self._get_entry_criteria(strategy, metrics),
                            risk_metrics=self._calculate_risk_metrics(strategy, metrics)
                        )
                        recommendations.append(recommendation)

        # Sort by confidence
        recommendations.sort(key=lambda x: x.confidence, reverse=True)

        return recommendations[:3]  # Return top 3 recommendations

    def _is_strategy_compatible(self, strategy: StrategyType, bias: str) -> bool:
        """Check if strategy is compatible with directional bias"""
        bullish_strategies = [StrategyType.LONG_CALL, StrategyType.BULL_CALL_SPREAD,
                             StrategyType.CASH_SECURED_PUT, StrategyType.COVERED_CALL]
        bearish_strategies = [StrategyType.LONG_PUT, StrategyType.BEAR_PUT_SPREAD]
        neutral_strategies = [StrategyType.LONG_STRADDLE, StrategyType.LONG_STRANGLE,
                             StrategyType.SHORT_STRADDLE, StrategyType.SHORT_STRANGLE,
                             StrategyType.IRON_CONDOR, StrategyType.IRON_BUTTERFLY,
                             StrategyType.CALENDAR_SPREAD, StrategyType.DIAGONAL_SPREAD,
                             StrategyType.BUTTERFLY_SPREAD, StrategyType.RATIO_SPREAD]

        if bias == 'bullish':
            return strategy in bullish_strategies or strategy in neutral_strategies
        elif bias == 'bearish':
            return strategy in bearish_strategies or strategy in neutral_strategies
        else:  # neutral
            return True

    def _calculate_confidence(self, metrics: VolatilityMetrics, strategy: StrategyType) -> float:
        """
        Calculate confidence score for a strategy recommendation
        Based on how well current conditions match ideal conditions for the strategy
        """
        confidence = 0.5  # Base confidence

        # Long volatility strategies
        if strategy in [StrategyType.LONG_STRADDLE, StrategyType.LONG_STRANGLE]:
            # Higher confidence when IV is very low compared to HV
            if metrics.iv_hv_ratio < 0.8:
                confidence += 0.3
            if metrics.iv_percentile < 20:
                confidence += 0.2

        # Short volatility strategies
        elif strategy in [StrategyType.SHORT_STRADDLE, StrategyType.SHORT_STRANGLE,
                         StrategyType.IRON_CONDOR, StrategyType.IRON_BUTTERFLY]:
            # Higher confidence when IV is high compared to HV
            if metrics.iv_hv_ratio > 1.3:
                confidence += 0.3
            if metrics.iv_percentile > 80:
                confidence += 0.2

        # Calendar spreads
        elif strategy in [StrategyType.CALENDAR_SPREAD, StrategyType.DIAGONAL_SPREAD]:
            # Higher confidence with steep term structure
            if abs(metrics.term_structure_slope) > 0.15:
                confidence += 0.3

        # Directional strategies
        elif strategy in [StrategyType.LONG_CALL, StrategyType.LONG_PUT]:
            # Higher confidence when IV is very low
            if metrics.iv_percentile < 15:
                confidence += 0.4

        return min(confidence, 1.0)

    def _get_entry_criteria(self, strategy: StrategyType, metrics: VolatilityMetrics) -> Dict[str, float]:
        """
        Get specific entry criteria for a strategy
        """
        criteria = {
            'current_iv': metrics.implied_volatility,
            'iv_percentile': metrics.iv_percentile,
            'iv_hv_ratio': metrics.iv_hv_ratio
        }

        # Add strategy-specific criteria
        if strategy in [StrategyType.IRON_CONDOR, StrategyType.SHORT_STRANGLE]:
            # For short vol strategies, define expected IV contraction
            criteria['target_iv'] = metrics.implied_volatility * 0.8
            criteria['days_to_expiry'] = 30  # Optimal DTE for theta decay

        elif strategy in [StrategyType.LONG_STRADDLE, StrategyType.LONG_STRANGLE]:
            # For long vol strategies, define expected IV expansion
            criteria['target_iv'] = metrics.implied_volatility * 1.3
            criteria['breakeven_move'] = metrics.implied_volatility * np.sqrt(30/365)  # 30-day expected move

        return criteria

    def _calculate_risk_metrics(self, strategy: StrategyType, metrics: VolatilityMetrics) -> Dict[str, float]:
        """
        Calculate risk metrics for a strategy
        """
        risk_metrics = {}

        # Estimate 1-standard deviation move
        one_std_move = metrics.implied_volatility * np.sqrt(30/365)

        if strategy in [StrategyType.LONG_STRADDLE, StrategyType.LONG_STRANGLE]:
            risk_metrics['max_loss'] = 1.0  # 100% of premium paid
            risk_metrics['breakeven_move'] = one_std_move
            risk_metrics['profit_potential'] = 'Unlimited'

        elif strategy in [StrategyType.SHORT_STRADDLE, StrategyType.SHORT_STRANGLE]:
            risk_metrics['max_loss'] = 'Unlimited'
            risk_metrics['max_profit'] = 1.0  # Premium received
            risk_metrics['profit_zone'] = f"±{one_std_move:.1%}"

        elif strategy in [StrategyType.IRON_CONDOR, StrategyType.IRON_BUTTERFLY]:
            risk_metrics['max_loss'] = 0.7  # Typical for 10-point wide IC
            risk_metrics['max_profit'] = 0.3  # Premium received
            risk_metrics['profit_zone'] = f"±{one_std_move * 0.8:.1%}"

        elif strategy in [StrategyType.LONG_CALL, StrategyType.LONG_PUT]:
            risk_metrics['max_loss'] = 1.0  # Premium paid
            risk_metrics['breakeven'] = f"Stock ± {one_std_move:.1%}"
            risk_metrics['delta_exposure'] = 0.5  # ATM assumption

        return risk_metrics


class VolatilityTradingSystem:
    """
    Complete volatility-based trading system implementing Natenberg's concepts
    """

    def __init__(self):
        self.analyzer = VolatilityAnalyzer()
        self.selector = OptionStrategySelector()

    def analyze_and_recommend(self,
                             prices: pd.Series,
                             current_iv: float,
                             iv_history: pd.Series,
                             term_structure: Optional[Dict[int, float]] = None,
                             directional_bias: str = 'neutral') -> Dict:
        """
        Complete analysis and strategy recommendation

        Args:
            prices: Historical stock prices
            current_iv: Current implied volatility
            iv_history: Historical IV series
            term_structure: Optional IV term structure
            directional_bias: Trading bias

        Returns:
            Dictionary with analysis and recommendations
        """
        # Perform volatility analysis
        metrics = self.analyzer.analyze_volatility(
            prices, current_iv, iv_history, term_structure
        )

        # Get strategy recommendations
        recommendations = self.selector.select_strategies(metrics, directional_bias)

        # Compile results
        results = {
            'volatility_metrics': {
                'historical_volatility': f"{metrics.historical_volatility:.1%}",
                'implied_volatility': f"{metrics.implied_volatility:.1%}",
                'iv_percentile': f"{metrics.iv_percentile:.0f}%",
                'hv_percentile': f"{metrics.hv_percentile:.0f}%",
                'iv_hv_ratio': f"{metrics.iv_hv_ratio:.2f}",
                'volatility_forecast': f"{metrics.volatility_forecast:.1%}",
                'regime': metrics.regime.value
            },
            'trading_signal': self._generate_trading_signal(metrics),
            'recommendations': []
        }

        for rec in recommendations:
            results['recommendations'].append({
                'strategy': rec.strategy.value,
                'confidence': f"{rec.confidence:.1%}",
                'rationale': rec.rationale,
                'entry_criteria': rec.entry_criteria,
                'risk_metrics': rec.risk_metrics
            })

        return results

    def _generate_trading_signal(self, metrics: VolatilityMetrics) -> str:
        """Generate overall trading signal based on volatility analysis"""
        if metrics.iv_hv_ratio < 0.85:
            return "BUY VOLATILITY - Options appear underpriced relative to historical volatility"
        elif metrics.iv_hv_ratio > 1.25:
            return "SELL VOLATILITY - Options appear overpriced relative to historical volatility"
        elif metrics.iv_percentile < 20:
            return "BUY OPTIONS - IV at historical lows, favorable for long premium strategies"
        elif metrics.iv_percentile > 80:
            return "SELL OPTIONS - IV at historical highs, favorable for short premium strategies"
        else:
            return "NEUTRAL - Use spread strategies or wait for better volatility opportunities"


def demonstrate_strategy_selection():
    """
    Demonstrate volatility-based strategy selection with example data
    """
    print("=" * 80)
    print("VOLATILITY-BASED OPTION STRATEGY SELECTION")
    print("Based on Natenberg's Option Volatility and Pricing Concepts")
    print("=" * 80)
    print()

    # Generate sample data
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=252, freq='D')

    # Simulate price data with varying volatility
    returns = np.random.normal(0.0005, 0.02, 252)
    prices = pd.Series(100 * np.exp(np.cumsum(returns)), index=dates)

    # Simulate IV history with mean reversion
    iv_mean = 0.25
    iv_history = pd.Series(
        iv_mean + 0.1 * np.sin(np.linspace(0, 4*np.pi, 252)) +
        np.random.normal(0, 0.02, 252),
        index=dates
    )
    iv_history = iv_history.clip(lower=0.1, upper=0.6)

    # Create trading system
    system = VolatilityTradingSystem()

    # Test different market scenarios
    scenarios = [
        {
            'name': "Low IV vs HV - Buy Volatility Scenario",
            'current_iv': 0.15,
            'term_structure': {30: 0.15, 60: 0.18, 90: 0.20},
            'bias': 'neutral'
        },
        {
            'name': "High IV vs HV - Sell Volatility Scenario",
            'current_iv': 0.45,
            'term_structure': {30: 0.45, 60: 0.40, 90: 0.35},
            'bias': 'neutral'
        },
        {
            'name': "Bullish with Normal Volatility",
            'current_iv': 0.25,
            'term_structure': {30: 0.25, 60: 0.26, 90: 0.27},
            'bias': 'bullish'
        }
    ]

    for scenario in scenarios:
        print(f"\n{'='*60}")
        print(f"SCENARIO: {scenario['name']}")
        print(f"{'='*60}")

        results = system.analyze_and_recommend(
            prices=prices,
            current_iv=scenario['current_iv'],
            iv_history=iv_history,
            term_structure=scenario['term_structure'],
            directional_bias=scenario['bias']
        )

        # Print volatility metrics
        print("\nVolatility Analysis:")
        print("-" * 40)
        for key, value in results['volatility_metrics'].items():
            print(f"  {key.replace('_', ' ').title()}: {value}")

        # Print trading signal
        print(f"\nTrading Signal:")
        print(f"  {results['trading_signal']}")

        # Print strategy recommendations
        print("\nRecommended Strategies:")
        print("-" * 40)
        for i, rec in enumerate(results['recommendations'], 1):
            print(f"\n  {i}. {rec['strategy']} (Confidence: {rec['confidence']})")
            print(f"     Rationale: {rec['rationale']}")
            print(f"     Entry Criteria:")
            for key, value in rec['entry_criteria'].items():
                if isinstance(value, float):
                    print(f"       - {key}: {value:.3f}")
                else:
                    print(f"       - {key}: {value}")

    print("\n" + "=" * 80)
    print("KEY TAKEAWAYS FROM NATENBERG'S VOLATILITY FRAMEWORK:")
    print("=" * 80)
    print("""
1. COMPARE IV TO HV: The relationship between implied and historical volatility
   is the foundation for identifying mispriced options.

2. VOLATILITY REGIMES: Understanding where current IV ranks historically helps
   determine whether to be a net buyer or seller of options.

3. TERM STRUCTURE: The slope of the volatility term structure can identify
   calendar spread opportunities.

4. MEAN REVERSION: Volatility tends to mean-revert, creating opportunities
   when IV is at extremes.

5. STRATEGY SELECTION: Match your strategy to the volatility environment:
   - Low IV: Buy options (long gamma/vega)
   - High IV: Sell options (short gamma/vega)
   - Normal IV: Use spreads to reduce cost and define risk

6. RISK MANAGEMENT: Always consider the worst-case scenario and size positions
   appropriately based on the unlimited risk potential of some strategies.
""")


if __name__ == "__main__":
    demonstrate_strategy_selection()