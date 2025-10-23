---
description: Build a diversified stock portfolio optimized for covered calls and ratio spreads
---

Build a diversified equity portfolio for selling covered calls and ratio spreads.

**Portfolio Target**: {0} (default: 5-8 positions)

## Step 1: Define Portfolio Criteria & Methodology

**Portfolio Construction Framework**: **Risk Parity with Factor Tilts**

This approach combines:
1. **Risk Parity**: Equal risk contribution per position (not equal dollars)
2. **Factor Exposure**: Intentional tilts toward Value, Quality, and Volatility factors
3. **Multi-Factor Diversification**: Decorrelate across sectors, factors, and risk regimes

**Why Not Traditional CAPM?**
- CAPM assumes markets are efficient and beta is the only risk factor
- Modern research shows multiple factors drive returns (Fama-French, Carhart)
- Options selling strategies benefit from volatility and quality factors
- Risk parity prevents over-concentration in low-vol stocks

**Investment Thesis**:
- Hold 100+ shares per position (enables covered calls)
- Target liquid, optionable stocks with healthy premium
- **Equal risk contribution** across positions (adjust position size by volatility)
- Focus on quality companies with strong fundamentals
- Tilt toward high IV (volatility premium capture)

**Target Allocation** (Risk-Based, not Dollar-Based):
- **Large Cap (60% risk)**: 3-4 positions - stable, liquid, high option volume
- **Mid Cap (30% risk)**: 2-3 positions - growth potential, decent liquidity
- **Small Cap (10% risk)**: 0-1 positions - higher volatility = higher premium

**Position Sizing Formula** (Risk Parity Approach):
```
Position Size = (Target Risk per Position) / (Stock Annual Volatility)

Example:
- Target: 5% portfolio risk per position
- Stock A: 30% annual vol → Position size = 5% / 30% = 16.7% of portfolio
- Stock B: 60% annual vol → Position size = 5% / 60% = 8.3% of portfolio

Result: Equal risk contribution despite different volatilities
```

**Sector Diversification** (no more than 25% per sector):
1. Technology (semiconductors, software, hardware)
2. Financials (banks, insurance, brokerages)
3. Healthcare (pharma, biotech, medical devices)
4. Energy (oil, renewable, utilities)
5. Consumer (discretionary & staples)
6. Industrials (aerospace, machinery, defense)
7. Communications (telecom, media)

**Stock Selection Criteria** (Multi-Factor Approach):

**Liquidity Factors** (Required):
- ✅ Price: $50-$300 (affordable 100-share lots: $5k-$30k)
- ✅ Average daily volume > 1M shares (liquidity)
- ✅ Option volume: Bid-ask spreads < 5% (good option liquidity)
- ✅ Avoid earnings within next 30 days (reduces blowup risk)

**Risk Factors** (For Position Sizing):
- 📊 Annual Volatility: 20-80% (measured via HV or IV)
- 📊 Beta: 0.7-1.5 (relative market sensitivity)
- 📊 Maximum Drawdown: Historical 20% drawdown periods
- 📊 Correlation: Target low correlation (<0.7) between positions

**Quality Factors** (Fama-French inspired):
- 💪 Profitability: Positive earnings, ROE > 10%
- 💪 Investment: Reasonable debt levels, sustainable business
- 💪 Market Leadership: Top 3 in industry or strong moat

**Value Factors** (Not strict requirement but considered):
- 💰 P/E ratio relative to sector average
- 💰 Earnings growth vs price growth
- 💰 Dividend yield (bonus for income)

**Volatility Factor** (Option Premium Driver - PRIMARY TILT):
- 🎯 **Implied Volatility: 25-60%** (sweet spot for premium collection)
- 🎯 **IV Rank**: Prefer stocks in 50%+ IV percentile
- 🎯 **IV/HV Ratio**: >1.2 ideal (overpriced options)
- 🎯 **Vol of Vol**: Stable high vol > spiking/crashing vol

**Factor Scoring System**:
```
Total Score = Quality (40%) + Volatility (40%) + Liquidity (20%)

Quality Score:
- Profitability: 20 points
- Low debt: 10 points
- Market leader: 10 points

Volatility Score:
- IV 40-60%: 20 points
- IV 25-40%: 15 points
- IV/HV > 1.2: 10 points
- IV Rank > 50%: 10 points

Liquidity Score:
- Volume > 5M: 10 points
- Volume 1-5M: 7 points
- Tight bid-ask (<3%): 10 points

Target: 65+ points for portfolio inclusion
```

## Step 2: Candidate Universe

**Suggest candidates across sectors**:

### Large Cap Candidates ($100B+ market cap)
**Technology**:
- AAPL, MSFT, GOOGL, META, NVDA, AMD, INTC, QCOM, AVGO
- Target: High IV (30-50%), liquid options

**Financials**:
- JPM, BAC, GS, MS, WFC, C
- Target: Stable dividend, moderate IV (25-40%)

**Healthcare**:
- UNH, JNJ, PFE, ABBV, MRK, LLY
- Target: Defensive, steady IV (20-35%)

**Energy**:
- XOM, CVX, COP, SLB, OXY
- Target: Cyclical exposure, moderate IV (30-45%)

**Consumer**:
- AMZN, TSLA, HD, NKE, SBUX, DIS
- Target: Growth + volatility, IV (35-60%)

### Mid Cap Candidates ($10B-$100B)
**Technology**: SNAP, PLTR, RIVN, COIN, SQ
**Financials**: SOFI, ALLY, KEY
**Healthcare**: TDOC, CRSP, BEAM
**Energy**: FSLR, ENPH, RIG
**Industrials**: BA, UAL, LUV, AAL

### Small Cap Candidates ($2B-$10B)
**High Volatility Premium**: AMC, BB, WKHS, RIDE, NKLA
- Use sparingly - higher risk but excellent premium

## Step 3: Volatility & Trend Analysis

For each candidate, use `mcp__stocks__analyze_volatility` and `mcp__stocks__get_stock_bars`:

**Analyze and report**:
1. **Current IV Level**: ATM implied volatility
2. **IV Percentile**: Where is current IV relative to 52-week range?
3. **Historical Volatility**: 30-day realized vol
4. **IV/HV Ratio**: >1.2 = excellent for selling premium
5. **Trend**: Uptrend/Downtrend/Sideways (last 30 days)
6. **Support Levels**: Key price levels for strike selection
7. **Earnings Date**: Confirm no earnings in next 30 days

**Priority Matrix**:
```
High IV (>40%) + Uptrend = TIER 1 (best for covered calls)
High IV (>40%) + Sideways = TIER 2 (good for ratio spreads)
Moderate IV (25-40%) + Uptrend = TIER 3 (dividend + premium)
Low IV (<25%) = AVOID (insufficient premium)
```

## Step 4: Portfolio Construction (Risk Parity + Factor Optimization)

**Build portfolio with modern diversification constraints**:

### Position Sizing Formula (Risk Parity)

**Step 1: Calculate Target Risk per Position**
```
If N positions, each should contribute 1/N of portfolio risk
For 6 positions: Each contributes 16.7% of total risk
```

**Step 2: Adjust Position Size by Volatility**
```
Position Weight (%) = Target Risk Contribution / (Stock Annual Vol × Portfolio Vol)

Simplified:
- Low Vol Stock (25% annual): Larger position size (15-20% of capital)
- Medium Vol Stock (40% annual): Medium position size (10-15% of capital)
- High Vol Stock (60% annual): Smaller position size (5-10% of capital)

Constraint: Minimum 100 shares (for covered calls)
```

**Step 3: Apply Practical Constraints**
```
After risk-parity calculation, apply these rules:
- Minimum position: $5,000 (100 shares minimum requirement)
- Maximum position: 20% of total capital (concentration limit)
- Round to nearest 100 shares (option contract = 100 shares)
```

### Diversification Rules (Multi-Dimensional)

**Sector Diversification** (Herfindahl Index < 0.25):
- ✅ No more than 2 positions per sector
- ✅ No more than 25% capital in any single sector
- ✅ Target 5-7 different sectors for 6+ positions

**Factor Diversification**:
- ✅ Mix of beta: 33% low (<0.9), 33% medium (0.9-1.1), 33% high (>1.1)
- ✅ Mix of IV: 33% medium (25-35%), 67% high (35-60%)
- ✅ Quality spread: 50% high quality (score 75+), 50% medium (score 65-75)

**Correlation Constraints**:
- ✅ Average pairwise correlation < 0.6
- ✅ No two positions with correlation > 0.8
- ✅ Use 30-day return correlation from historical data

**Market Cap Diversification** (Risk-weighted):
- ✅ At least 60% risk in large cap (stability)
- ✅ Up to 30% risk in mid cap (growth)
- ✅ Up to 10% risk in small cap (premium)

### Portfolio Risk Metrics to Calculate

**1. Total Portfolio Volatility**:
```
σ_portfolio = sqrt(Σ Σ w_i × w_j × σ_i × σ_j × ρ_ij)

Where:
w_i = weight of position i
σ_i = volatility of position i
ρ_ij = correlation between positions i and j
```

**2. Risk Contribution per Position**:
```
Risk Contribution_i = (w_i × σ_i × β_i,portfolio) / σ_portfolio

Target: Equal risk contributions (±3% deviation)
```

**3. Factor Exposures**:
```
Market Beta (weighted avg): Target 0.9-1.1
Volatility Factor: Target 1.2-1.5 (tilt toward high vol)
Quality Factor: Target positive exposure
```

**4. Portfolio Sharpe Ratio Enhancement**:
```
Expected Enhancement from Option Income:
- Covered calls: +3-8% annual yield (depending on IV)
- Portfolio Sharpe improvement: +0.3 to +0.6

Target Total Portfolio Sharpe: >0.8 (stock + options)
```

### Sample Portfolio Output

Present final portfolio as:

```
DIVERSIFIED EQUITY PORTFOLIO FOR COVERED CALL INCOME
Total Positions: {N}
Total Capital: ${XXX,XXX}
Target Annual Income: X-XX% (from covered calls)

POSITION 1: [SYMBOL] - [Sector] - [Large/Mid/Small Cap]
├─ Price: $XXX.XX
├─ Shares: XXX (cost: $XX,XXX)
├─ IV: XX.X% (Rank: High/Medium)
├─ Beta: X.XX
├─ Trend: [Uptrend/Sideways/Downtrend]
├─ Support: $XXX (for strike selection)
├─ Next Earnings: MM/DD (XX days away)
└─ Strategy:
   • Covered Call: Sell [X]C @ $X.XX (30-45 DTE)
   • Monthly Income: $XXX (X.X% monthly yield)
   • Or: Ratio Spread: Sell 2x [X]C, Buy 1x [Y]C

POSITION 2: [SYMBOL] - [Sector] - [Large/Mid/Small Cap]
[... repeat for each position ...]

PORTFOLIO SUMMARY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sector Allocation:
├─ Technology: XX% (X positions)
├─ Financials: XX% (X positions)
├─ Healthcare: XX% (X positions)
├─ Energy: XX% (X positions)
├─ Consumer: XX% (X positions)
└─ Industrials: XX% (X positions)

Market Cap Distribution:
├─ Large Cap: XX% ($XXX,XXX)
├─ Mid Cap: XX% ($XXX,XXX)
└─ Small Cap: XX% ($XXX,XXX)

Risk Metrics (Risk Parity Analysis):
├─ Portfolio Volatility: XX.X% (annualized)
├─ Portfolio Beta: X.XX (weighted avg)
├─ Avg Correlation: X.XX (target <0.6)
├─ Risk Contribution Balance: XX% deviation (target <3%)
├─ Avg IV: XX.X%
├─ High IV positions: X (>40%)
└─ Medium IV positions: X (25-40%)

Factor Exposures:
├─ Market Factor (Beta): X.XX (target 0.9-1.1)
├─ Volatility Factor: X.XX (target >1.2 for premium)
├─ Quality Factor: X.XX (target positive)
└─ Sector Concentration (HHI): X.XX (target <0.25)

Position Sizing Verification:
├─ Largest position: XX% (target <20%)
├─ Smallest position: XX% (target >5%)
├─ Risk contribution range: XX%-XX% (target equal)
└─ All positions ≥100 shares: ✅/❌

Income Potential:
├─ Monthly covered call premium: $X,XXX - $X,XXX
├─ Annual yield estimate: X-XX%
├─ Assumes 30-45 DTE calls at ~0.30 delta
├─ Roll uncalled positions monthly
└─ Expected Sharpe Enhancement: +0.X
```

## Step 5: First Month Strategy Recommendations

For each position, recommend initial covered call trade:

**POSITION: [SYMBOL] (XXX shares @ $XXX.XX)**

Use `mcp__stocks__get_option_quote` to get real quotes for suggested strikes.

**Covered Call Setup**:
```
Strategy: Covered Call
Sell: [X] x [STRIKE]C @ $X.XX (bid)
Expiration: [DATE] (XX DTE)
Premium Collected: $XXX (X.X% yield)
Breakeven: $XXX.XX (current + premium)
Max Profit: $XXX (if called away at strike)
Delta: ~0.25-0.35 (75-65% prob OTM)
```

**Or Ratio Spread Setup** (if high IV + sideways):
```
Strategy: 1x2 Call Ratio Spread
Buy: 1 x [STRIKE_1]C @ $X.XX (ask)
Sell: 2 x [STRIKE_2]C @ $X.XX (bid)
Net Credit: $XXX (or small debit)
Max Profit: $XXX at [STRIKE_2]
Risk: Uncapped above [STRIKE_2 + credit]
Best for: High IV + expect small move
```

**Management Rules**:
- 🟢 Roll at 50% profit or 7 DTE
- 🟡 Adjust if stock threatens breakout
- 🔴 Close if stock drops >10% (protect shares)

## Step 6: Portfolio Monitoring & Management

**Weekly Review Checklist**:
- [ ] Check each position's distance to short strike
- [ ] Monitor any approaching earnings dates
- [ ] Review IV changes (roll up if IV drops significantly)
- [ ] Assess any positions for early roll opportunities
- [ ] Rebalance if any sector exceeds 30%

**Monthly Tasks**:
- [ ] Roll all covered calls (or let assign if ITM)
- [ ] Review portfolio performance vs SPY
- [ ] Calculate realized income vs target
- [ ] Consider adding/removing positions based on IV changes
- [ ] Tax loss harvest if applicable

**Quarterly Review**:
- [ ] Full portfolio rebalance
- [ ] Sector rotation based on market conditions
- [ ] Replace low-IV stocks with higher-IV alternatives
- [ ] Review capital deployment efficiency

## Step 7: Risk Management

**Position-Level Risk**:
- Max 15% per position (prevents concentration risk)
- Stop loss: -20% on any equity position
- Don't sell calls through earnings (IV crush risk)
- Keep some cash (10-15%) for opportunities

**Portfolio-Level Risk**:
- Target portfolio beta: 0.9-1.1 (balanced risk)
- Correlation check: Avoid all positions moving together
- Hedge consideration: Consider QQQ/SPY put spreads if >80% long tech
- Cash reserve: 10-15% for buying dips or volatility spikes

**Income Risk**:
- Diversify expirations (don't expire all same week)
- Mix of deltas: Some 0.25 (safer), some 0.35 (more income)
- Have alternative strategies (ratio spreads) if IV drops
- Don't chase yield - quality positions first

## Output Format

Present analysis in this order:
1. **Candidate Analysis** (3-5 symbols per sector with IV/trend data)
2. **Recommended Portfolio** (5-8 positions with full details)
3. **Initial Trade Setups** (specific strikes and premiums for each position)
4. **Income Projections** (monthly/annual based on current IV)
5. **Risk Assessment** (sector concentration, beta, correlation)
6. **Next Steps** (what to execute first, in what order)

**Key Principles**:
- Quality over quantity - better to have 5 great positions than 10 mediocre
- Premium follows volatility - prioritize high IV stocks
- Diversification protects capital - avoid sector concentration
- Trend is your friend - covered calls work best in uptrends or sideways
- Roll don't fold - manage positions actively for maximum income
