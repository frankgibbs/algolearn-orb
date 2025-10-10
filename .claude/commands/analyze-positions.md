---
description: Comprehensive analysis of all open option positions with management recommendations
---

Analyze all open option positions and provide detailed management guidance:

## Step 1: Fetch All Open Positions

Use `list_option_positions` MCP tool (no arguments needed)

## Step 2: Position-by-Position Analysis

For EACH open position, provide detailed analysis:

### Position Header
```
Position #[N]: [SYMBOL] [STRATEGY_TYPE]
Order ID: [ID] | Entry: [DATE] | DTE: [X] days
Status: 🟢 HEALTHY / 🟡 WATCH / 🔴 URGENT
```

### Current Status Analysis

**Entry vs Current**:
- Entry Credit: $X.XX ($XXX)
- Current Spread Value: $X.XX
- Unrealized P&L: $X.XX ([+/-]X.X% ROI)
- % of Max Profit Captured: X.X%

**Price Position** (CRITICAL):
- Current Underlying: $X.XX
- Short Strike: $X.XX
- Breakeven: $X.XX
- Distance to Breakeven: $X.XX (X.X%)
- Distance to Short Strike: $X.XX (X.X%)

**For Bull Put Spreads**:
- ✅ Safe: Price > Breakeven + 3%
- 🟡 Watch: Price within 3% of breakeven
- 🔴 Danger: Price < Breakeven

**For Bear Call Spreads**:
- ✅ Safe: Price < Breakeven - 3%
- 🟡 Watch: Price within 3% of breakeven
- 🔴 Danger: Price > Breakeven

### Time Decay Analysis

**Days to Expiration**: [X] days
- ✅ Sweet spot (15-30 DTE): Optimal theta decay
- 🟡 Getting close (7-14 DTE): Accelerating gamma risk
- 🔴 Expiration week (< 7 DTE): High gamma risk, consider closing

**Theta Decay**:
- Daily theta: Estimate based on current value and DTE
- Expected P&L from time decay if price unchanged

### Greeks & Risk Metrics

**Delta Exposure**:
- Position delta (indicates directional exposure)
- Probability ITM for short strike

**Current Metrics**:
- Current IV vs Entry IV (volatility environment change?)
- Profit target status (50% = $X, 75% = $X)

### Management Decision Matrix

**HOLD** if:
✅ Price has comfortable cushion (>3% from breakeven)
✅ DTE > 14 days
✅ Less than 50% of max profit captured
✅ No adverse trend changes

**CLOSE EARLY** if:
✅ 50-75% of max profit captured (Tastytrade rule)
✅ Price still safe from assignment
✅ Can lock in profits and redeploy capital

**URGENT ACTION** if:
🔴 Price breached breakeven
🔴 < 7 DTE with unfavorable price action
🔴 Major adverse trend change
🔴 Approaching max loss

**ROLL** (extend duration) if:
🟡 DTE < 14 days
🟡 Position still valid but needs more time
🟡 Can collect additional credit by rolling out

### Price Action Check (Get Recent Bars)

Use `get_stock_bars` with symbol=[SYMBOL], duration="30 D", bar_size="1 day" to check recent trend:

**Trend Analysis**:
- Last 5-10 days: [Uptrend/Downtrend/Sideways]
- Support/Resistance relative to strikes
- Any momentum shifts that threaten position?

**For Bull Put Spreads** - Check for:
- ❌ Breaking below support levels
- ❌ Consecutive down days approaching short strike
- ✅ Holding above support
- ✅ Bouncing or consolidating

**For Bear Call Spreads** - Check for:
- ❌ Breaking above resistance levels
- ❌ Consecutive up days approaching short strike
- ✅ Holding below resistance
- ✅ Pulling back or consolidating

### Specific Management Recommendation

Provide ONE clear recommendation:

**Example 1 - HOLD**:
```
🟢 RECOMMENDATION: HOLD
- Position healthy with $X.XX cushion (X.X%)
- X days remain for theta decay
- Target: Close at 50-75% profit ($X-$X)
- Alert: Monitor if price drops below $X.XX
```

**Example 2 - CLOSE EARLY**:
```
🟢 RECOMMENDATION: CLOSE NOW for 68% profit
- Captured $XX of $XXX max profit
- Lock in gains before gamma risk increases
- Redeploy capital to new opportunity
- Action: Buy to close for $X.XX debit
```

**Example 3 - URGENT**:
```
🔴 RECOMMENDATION: CLOSE IMMEDIATELY
- Price breached breakeven at $X.XX
- Current loss: $XX (X% of max risk)
- Trend shows continued [downward/upward] pressure
- Action: Close to prevent further losses
```

**Example 4 - ROLL**:
```
🟡 RECOMMENDATION: ROLL OUT
- Only X DTE remaining
- Position still valid but needs time
- Roll to [DATE] expiration for $X.XX credit
- New breakeven: $X.XX
```

## Step 3: Portfolio-Level Analysis

After analyzing all positions, provide portfolio summary:

### Portfolio Summary
```
Total Open Positions: X
Total Unrealized P&L: $X.XX
Total Capital at Risk: $X.XX
Average DTE: X days
```

### Risk Distribution
- Position #1: $XXX risk (XX%)
- Position #2: $XXX risk (XX%)
- [etc.]

### Diversification Assessment
- Symbols: [List unique symbols]
- Strategies: [Bull put, bear call, etc.]
- Sectors represented: [Tech, Retail, etc.]
- ✅ Good diversification / 🟡 Concentrated risk

### Portfolio Greeks (if calculable)
- Net Delta: [Directional bias]
- Net Theta: [Daily decay benefit]
- Net Vega: [IV sensitivity]

### Action Items Summary

**Immediate Actions** (🔴):
- [List any positions requiring urgent action]

**Close for Profit** (🟢):
- [List positions at profit targets]

**Monitor Closely** (🟡):
- [List positions needing attention]

**Hold** (✅):
- [List healthy positions to hold]

### Calendar & Risk Events

**Upcoming Expirations**:
- [DATE]: X positions expiring
- [DATE]: X positions expiring

**Earnings/Events** (if any symbols have earnings before expiration):
- [SYMBOL]: Earnings on [DATE] - consider closing before

## Step 4: Final Portfolio Recommendations

Provide strategic guidance:

**Capital Efficiency**:
- Total premium collected: $XXX
- Total capital deployed: $X,XXX
- Current return: X.X% unrealized

**Suggested Actions**:
1. [Close X position(s) for profit and redeploy]
2. [Roll Y position(s) for more time]
3. [Monitor Z position(s) closely]
4. [Consider new positions in different sectors for diversification]

**Risk Management**:
- Max portfolio drawdown acceptable: X%
- Current drawdown: X%
- Position sizing: Keep each position < 15% of total risk

**Next Review**: Recommend reviewing again in [X] days or immediately if:
- Any position price moves within 2% of breakeven
- < 7 DTE on any position
- Major market volatility event

Present analysis in clear, actionable format with traffic lights (🟢🟡🔴) for easy scanning.
