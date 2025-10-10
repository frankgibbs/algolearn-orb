---
description: Complete options strategy analysis for a symbol including volatility, trend, and strategy recommendations
---

Analyze {0} for options trading opportunities following this comprehensive workflow:

## Step 1: Volatility Analysis (REQUIRED)

Use `mcp__stocks__analyze_volatility` with symbol={0}

Review and report:
- Current ATM IV level
- Historical volatility (10, 20, 30, 60 day)
- **IV/HV ratio** (key metric)
- Volatility term structure
- Trading signal (SELL_VOLATILITY, BUY_VOLATILITY, NEUTRAL)

## Step 2: Price Trend Analysis (REQUIRED - CRITICAL)

Use `get_stock_bars` with symbol={0}, duration="90 D", bar_size="1 day"

**Analyze last 20-30 days and report**:

**Trend Direction**:
- Uptrend, downtrend, or sideways?
- Recent high/low levels
- Any failed breakouts or reversals?

**Key Levels**:
- Support levels (identify and note how many times tested)
- Resistance levels (identify and note how many times rejected)
- Recent gaps or significant moves

**Volume Analysis**:
- Volume pattern during recent moves
- Distribution or accumulation?
- Volume exhaustion signals?

**Reversal Signal Analysis** (CRITICAL for counter-trend trades):
- **Oversold conditions**: Multiple down days, volume declining on down moves
- **Overbought conditions**: Extended rally, volume declining on up moves
- **Support/Resistance strength**: Has level held multiple times (3+)?
- **Price action patterns**: Hammers, shooting stars, engulfing patterns

**Trend Assessment**:
- Primary trend direction
- Any reversal signals present?
- Support/resistance levels for strike placement

**Red Flags** (report if present):
- ❌ Failed breakout followed by reversal
- ❌ Multiple consecutive down days on high volume (avoid bullish strategies UNLESS oversold)
- ❌ Multiple consecutive up days on high volume (avoid bearish strategies UNLESS overbought)
- ❌ Breaking below key support (avoid bullish strategies)
- ❌ Breaking above key resistance (avoid bearish strategies)

**Green Flags for Counter-Trend** (note if present):
- ✅ Support tested 3+ times without breaking (potential bounce)
- ✅ Resistance rejected 3+ times (potential reversal)
- ✅ Volume exhaustion on recent moves
- ✅ Reversal candlestick patterns

## Step 3: Strategy Selection (Based on Volatility Signal + Trend + Reversal Signals)

**Match volatility signal with trend-appropriate strategies**:

**If SELL_VOLATILITY (IV/HV > 1.25)**:

**Trend-Following (Preferred)**:
- **Uptrend**: Bull Put Spread (strikes below current price)
- **Downtrend**: Bear Call Spread (strikes above current price)
- **Sideways**: Iron Condor

**Counter-Trend (Only with strong reversal signals)**:
- **Downtrend → Potential Bounce**: Bull Put Spread IF:
  - Support tested 3+ times and holding
  - Volume exhaustion on down moves
  - Oversold conditions present
  - **Place strikes AT or BELOW tested support level**

- **Uptrend → Potential Pullback**: Bear Call Spread IF:
  - Resistance rejected 3+ times
  - Volume exhaustion on up moves
  - Overbought conditions present
  - **Place strikes AT or ABOVE resistance level**

**If BUY_VOLATILITY (IV/HV < 0.85)**:
- Long Straddle/Strangle (neutral on direction)
- Calendar spreads (if term structure supports)
- Vertical spreads (MUST confirm trend supports direction)

**If NEUTRAL (0.85 < IV/HV < 1.25)**:
- Iron Condor (requires sideways trend)
- Vertical spreads with directional view (MUST confirm trend + reversal signals)

**Select 1-2 strategies that align with volatility, trend, AND technical setup**

## Step 4: Get Real Market Quotes (REQUIRED)

For each selected strategy, use `mcp__stocks__get_option_quote` to get actual bid/ask for all legs.

**CRITICAL**:
- Always use real market prices - NEVER estimate
- Sell at BID price
- Buy at ASK price
- Target 28-45 DTE (Nov or Dec expiration)
- Look for strikes with good liquidity

## Step 5: Calculate Strategy Metrics

For each strategy analyzed, calculate and report:

**Premium & Risk**:
- Net credit/debit
- Max risk
- Max profit
- **ROI**: (Premium / Max Risk) × 100

**Positioning**:
- Breakeven points
- Profit zone (distance between breakevens as % of underlying)
- Current price vs breakeven (cushion)
- **Strike placement relative to support/resistance**

**Greeks & Time**:
- Days to expiration
- Delta exposure
- Theta decay rate

## Step 6: Recommendation

Provide clear recommendation with rationale:

**Summary Table** for each strategy:
```
Strategy: [Bull Put Spread / Bear Call Spread / Iron Condor]
Strikes: [e.g., 390/395]
Net Credit: $X.XX ($XXX)
Max Risk: $XXX
ROI: XX.X%
Breakeven: $XXX.XX
Cushion: $XX.XX (X.X%)
DTE: XX
Strike Placement: [At/Below support] or [At/Above resistance]
```

**Trade Rationale**:
✅ High/Low IV (X.XX ratio) - favorable for [selling/buying] premium
✅ [Uptrend/Downtrend/Sideways] - [aligns with/counter to] trend
✅ [If counter-trend]: Support/Resistance at $XXX tested X times
✅ [If counter-trend]: Volume exhaustion / reversal signals present
✅ Strikes placed [at/below support] or [at/above resistance]
✅ X% cushion provides safety margin

**Risk Assessment**:
- Primary risk: [Continued downtrend / Failed reversal / etc.]
- Assignment probability
- Key price levels to monitor
- Management plan (when to close early)

**Final Recommendation**:
- **PLACE**: If all criteria met (volatility + trend/reversal + ROI > 25% + proper strike placement)
- **PASS**: If trend doesn't support strategy AND no reversal signals
- **WAIT**: If need more price action to confirm reversal

**IMPORTANT RULES**:
1. **Default to trend-following** - counter-trend trades require strong technical evidence
2. **Bull put spreads in downtrends**: ONLY if support tested 3+ times + volume exhaustion + strikes at/below support
3. **Bear call spreads in uptrends**: ONLY if resistance rejected 3+ times + volume exhaustion + strikes at/above resistance
4. **NEVER estimate option prices** - always use real quotes
5. **Require minimum 25% ROI** for defined-risk spreads
6. **Require minimum 2% cushion** to breakeven
7. **Strike placement is critical**: Counter-trend trades MUST place strikes at key support/resistance

Focus on presenting ONE best opportunity based on highest probability of success given current market conditions and technical setup.
