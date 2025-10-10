---
description: Discover and analyze ITM covered call opportunities by scanning fundamentally sound stocks to maximize extrinsic value
---

Analyze the market to find optimal ITM covered call opportunities by following this systematic workflow:

1. **Multi-Scanner Strategy for Comprehensive Coverage** (targeting 75+ candidates):

   **Primary Scans** (execute all three to capture diverse opportunities):
   - **Income Focus**: `mcp__forex-bot__scan_stocks` with scan_code="HIGH_DIVIDEND_YIELD_IB", max_symbols=25, price_above=99
   - **Liquidity Focus**: `mcp__forex-bot__scan_stocks` with scan_code="MOST_ACTIVE", max_symbols=25, price_above=99
   - **Options Volume Focus**: `mcp__forex-bot__scan_stocks` with scan_code="TOP_OPT_VOLUME_MOST_ACTIVE", max_symbols=25, price_above=99

   **Rationale**:
   - High dividend stocks provide income stability for covered calls
   - Most active stocks ensure good liquidity and tight spreads
   - High option volume stocks have better bid-ask spreads and execution
   - Combined approach captures 75 diverse candidates ensuring 50+ viable options

2. **Consolidate and Screen Candidates** from all three scans:

   **Deduplication Process**:
   - Combine all symbols from the three scans (may have overlaps)
   - Remove duplicates to create master candidate list
   - Target: 50-75 unique symbols for evaluation

   **Pre-Screening for Option Availability**:
   - Prioritize symbols that appear in multiple scans (indicates strong fundamentals + liquidity)
   - Use scanner ranking data to identify best opportunities from each category

3. **Get fundamental data** for each unique stock to verify quality and exclude ETFs:
   Use `mcp__forex-bot__get_fundamental_data` for each symbol
   - **Exclude ETFs**: Skip symbols that are ETFs (ETFs lack traditional earnings metrics)
   - **Enhanced Quality Metrics**: P/E ratio <30 (relaxed for growth), debt-to-equity <0.7, positive earnings growth
   - **Dividend considerations**: Bonus scoring for dividend-paying stocks for additional income
   - **Market Cap Filter**: Prefer large-cap (>$10B) and mega-cap (>$100B) for stability
   - Include both growth and value stocks with strong fundamentals

4. **Get 120-day technical analysis** for each fundamentally sound stock:
   **IMPORTANT**: Request stock candles ONE AT A TIME (sequential, not parallel) to avoid IB disconnections
   Use `mcp__forex-bot__get_stock_candles` with duration="120 D", bar_size="1 week", include_indicators=true
   - Identify current trend direction (uptrend preferred for covered calls)
   - Analyze support levels for stock protection
   - Check volatility patterns (moderate IV preferred)
   - Assess momentum indicators for timing
   - Assign technical score (1-10) for covered call suitability

5. **Apply Enhanced ITM Covered Call Classification Matrix** (CRITICAL for maximizing extrinsic value):

   **Trend Analysis (Ideal for Covered Calls)**:
   - **Mild Uptrend**: IDEAL - Stock appreciation + premium collection
   - **Sideways/Consolidation**: ACCEPTABLE - Premium collection focus
   - **Strong Uptrend**: CAUTION - High assignment risk, less extrinsic value
   - **Downtrend**: AVOID - Stock depreciation risk outweighs premium

   **Enhanced Volatility Analysis for Premium Maximization**:
   - **IV 25-40%**: IDEAL - Good premium without excessive assignment risk
   - **IV 40-60%**: ACCEPTABLE - Higher premium but watch for volatility crush
   - **IV >60%**: CAUTION - High premium but extreme assignment risk
   - **IV <25%**: AVOID - Insufficient premium for covered call strategy

   **IV Rank Integration** (use `mcp__forex-bot__get_iv_analysis` for qualified candidates):
   - **IV Rank 20-60%**: IDEAL - Moderate to elevated volatility
   - **IV Rank >80%**: CAUTION - Extremely high volatility, potential mean reversion
   - **IV Rank <20%**: AVOID - Low volatility, insufficient premium generation

   **Strike Selection for Extrinsic Value**:
   - **ITM 2-5%**: MAXIMUM extrinsic value, moderate assignment risk
   - **ITM 5-8%**: HIGH extrinsic value, higher assignment protection
   - **ITM 8-12%**: MODERATE extrinsic value, strong downside protection
   - **ITM >12%**: LOW extrinsic value, mainly intrinsic value

   **Enhanced Final Classification Matrix**:
   - **Mild uptrend + IV 25-40% + IV Rank 20-60% + ITM 2-5%**: PREMIUM covered call candidate
   - **Sideways + IV 30-50% + IV Rank 30-70% + ITM 3-8%**: STRONG income generation candidate
   - **Quality dividend stock + IV 25-45% + ITM 5-10%**: CONSERVATIVE income candidate
   - **Multi-scan appearance + Mega-cap + Moderate IV**: PRIORITY candidate
   - **Strong uptrend + High IV + IV Rank >80%**: SKIP (assignment risk too high)
   - **Downtrend + Any ITM**: SKIP (stock risk outweighs premium)
   - **IV Rank <20%**: SKIP (insufficient premium potential)

   **⚠️ CRITICAL COVERED CALL WARNINGS**:
   - Never sell calls on stocks in strong downtrends (premium won't offset losses)
   - Avoid during earnings week (volatility crush + assignment risk)
   - Skip if stock has gapped >8% up in last 30 days (momentum risk)
   - Ensure comfortable owning the stock if assigned
   - Check dividend ex-dates (early assignment risk)

6. **Smart Option Chain Analysis** for top-ranked candidates only:

   **Pre-Selection Criteria** (select top 10-15 candidates before option analysis):
   - Combine fundamental score (40%) + technical score (40%) + liquidity ranking (20%)
   - Prioritize stocks appearing in multiple scans
   - Require minimum market cap of $5B for option liquidity

7. **Fetch call option chains** for qualified ITM covered call candidates:
   **Strike Selection Criteria**:
   - Focus on ITM strikes 2-8% below current price for maximum extrinsic value
   - Ensure adequate volume and open interest (>50 contracts)
   - Target 30-45 DTE for optimal time decay
   - Verify no earnings between now and expiration

   **Enhanced Option Chain Requests**:
   - **Primary target (30 DTE)**: Use `mcp__forex-bot__get_options_data` with symbols=["SYMBOL"], target_dte=30, option_type="C", strike_selection="ITM", max_strikes=3
   - **Secondary target (45 DTE)**: Use `mcp__forex-bot__get_options_data` with symbols=["SYMBOL"], target_dte=45, option_type="C", strike_selection="ITM", max_strikes=3
   - **Backup scan (21 DTE)**: For weekly options if monthly chains lack liquidity

8. **Enhanced Scoring System** for each ITM covered call opportunity:

   **Core Metrics**:
   - **Extrinsic Value Ratio**: Extrinsic premium ÷ (Stock price - Strike price)
   - **Annualized Return**: (Total premium ÷ Stock price) × (365 ÷ DTE)
   - **Downside Protection**: (Strike price + Premium - Stock price) ÷ Stock price
   - **Liquidity Score**: Based on option volume, bid-ask spread, and stock ranking from scans

   **Enhanced Covered Call Score Calculation**:
   - **Extrinsic Value Weight**: 40% (maximize time premium)
   - **Annualized Return Weight**: 30% (income generation focus)
   - **Technical Score Weight**: 20% (trend and support analysis)
   - **Liquidity Score Weight**: 10% (execution quality)

   **Bonus Factors**:
   - +0.5 points for dividend-paying stocks
   - +0.3 points for stocks appearing in multiple scans
   - +0.2 points for mega-cap stocks (>$100B market cap)

9. **Rank opportunities** by Enhanced Covered Call Score (higher is better - maximizes extrinsic value with acceptable risk)

10. **Present top 5 ITM covered call opportunities** in comprehensive analysis:

**For each opportunity, include**:
   - **Symbol and current price** with fundamental quality metrics
   - **Strike price** and moneyness (% ITM)
   - **Fundamental Analysis**: P/E ratio, debt levels, earnings growth, dividend yield
   - **Technical Analysis**: Trend direction, support levels, volatility assessment
   - **Option Details**:
     - Expiry date and DTE
     - Premium (total and per share)
     - Intrinsic value and extrinsic value breakdown
     - Delta, Theta, and implied volatility
   - **Strategy Metrics**:
     - Total premium collected
     - Annualized return if unchanged
     - Annualized return if assigned
     - Downside protection percentage
     - Maximum profit potential
     - Breakeven price
     - Covered Call Score
   - **Trade Setup**: "Own 100 shares of [Symbol] at $[Price], Sell [Expiry] $[Strike] Call for $[Premium]"
   - **Risk Factors**: Assignment probability, support levels, upcoming events

**Focus on opportunities with enhanced ideal covered call conditions**:
- Strong fundamental metrics (profitable, reasonable valuation, market cap >$5B)
- ITM strikes with high extrinsic value (2-8% ITM preferred)
- Moderate implied volatility (25-40% ideal) with IV Rank 20-60%
- High liquidity (appears in multiple scans, good option volume)
- Mild uptrend or sideways price action with strong support levels
- No earnings or major events before expiration
- Comfortable stock ownership at current levels (quality companies)
- Bonus preference for dividend-paying mega-cap stocks

**Enhanced Income Enhancement Strategy**:
- Target 1-3% monthly returns from premium collection with stocks >$99
- Focus on repeatable setups with quality underlying stocks from multiple scans
- Balance assignment risk with premium income using IV rank analysis
- Prioritize dividend capture opportunities (bonus scoring)
- Maintain portfolio diversification across sectors and market caps
- Leverage high-volume option markets for better execution
- Build watchlist of mega-cap dividend stocks for consistent covered call cycles