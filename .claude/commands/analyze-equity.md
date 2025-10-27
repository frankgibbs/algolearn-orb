---
description: Comprehensive PowerOptions equity analysis with real-time cost basis and option premium
---

Analyze PowerOptions equity holdings with complete cost basis calculation including option premium.

## Step 1: Fetch All Equity Holdings

Use the `get_equity_holdings` MCP tool to get PowerOptions equity holdings from the database:

```bash
mcp__stocks__get_equity_holdings(status="OPEN")
```

This returns all OPEN equity holdings (long-term stock positions for covered calls).

## Step 2: For Each Equity Holding

For each equity holding, perform detailed analysis:

### A. Stock Position Details

Display:
- **Symbol**: [SYMBOL]
- **Shares**: [X] shares
- **Purchase Date**: [DATE]
- **Original Cost Basis**: $X.XX per share
- **Total Original Cost**: $X,XXX.XX
- **Status**: [OPEN/CLOSED]

### B. Get Current Stock Price

Use `get_stock_bars` to get latest close price:

```bash
mcp__stocks__get_stock_bars(
  symbol=[SYMBOL],
  duration="1 D",
  bar_size="1 day"
)
```

Calculate:
- **Current Market Price**: $X.XX
- **Current Market Value**: $X,XXX.XX (shares × current_price)
- **Stock Gain/Loss**: $XXX (market_value - original_cost)

### C. Fetch All Linked Option Positions

Use `list_option_positions` to get all options for this symbol:

```bash
mcp__stocks__list_option_positions(symbol=[SYMBOL])
```

Then query database to filter only options with matching `equity_holding_id`.

Separate into two categories:
1. **CLOSED** positions (status = CLOSED or EXPIRED_WORTHLESS)
2. **OPEN** positions (status = OPEN or PENDING)

### D. Calculate Realized Premium (Closed Options)

For each CLOSED option position:

Display table:
```
Closed Options:
Order ID | Strategy      | Entry Date | Close Date | Net Credit | Realized P&L
---------|---------------|------------|------------|------------|-------------
[ID]     | [SHORT_CALL]  | [DATE]     | [DATE]     | $X.XX      | $XXX.XX
[ID]     | [SHORT_CALL]  | [DATE]     | [DATE]     | $X.XX      | $XXX.XX
```

**Total Realized Premium**: $XXX.XX (sum of all realized_pnl)

### E. Calculate Unrealized Premium (Open Options)

**CRITICAL**: For each OPEN option position, get REAL-TIME bid/ask for ALL legs:

#### For Each Open Position:

1. **Display position details**:
   ```
   Open Position: [STRATEGY_TYPE]
   Order ID: [ID]
   Entry Date: [DATE]
   Entry Credit: $X.XX ($XXX per contract)
   DTE: [X] days
   ```

2. **Fetch real-time quotes for ALL legs**:

   For EACH leg in the position, use `get_option_quote`:
   ```bash
   mcp__stocks__get_option_quote(
     symbol=[SYMBOL],
     expiry=[EXPIRY from leg],
     strike=[STRIKE from leg],
     right=[C or P from leg]
   )
   ```

3. **Calculate current cost to close**:

   **Rules**:
   - **SELL legs** (short positions): Buy back at **ASK** price
   - **BUY legs** (long positions): Sell at **BID** price

   **Example for SHORT_CALL**:
   ```
   Leg: SELL 1x 270C
   Current quote: Bid $4.80, Ask $4.85
   Cost to close: $4.85 (buy back at ASK) × 100 = $485

   Entry credit: $5.05 × 100 = $505
   Unrealized P&L: $505 - $485 = $20 profit
   ```

   **Example for Bear Call Spread**:
   ```
   Leg 1: SELL 1x 270C
   - Current: Bid $4.80, Ask $4.85
   - Close cost: $485 (ASK)

   Leg 2: BUY 1x 280C
   - Current: Bid $2.25, Ask $2.30
   - Close value: $225 (BID)

   Net close cost: $485 - $225 = $260
   Entry credit: $272
   Unrealized P&L: $272 - $260 = $12 profit
   ```

4. **Display for each open position**:
   ```
   Legs Detail:
   - SELL 270C: Ask $4.85 → Close cost $485
   - [Additional legs if any]

   Cost to Close: $XXX
   Unrealized P&L: $XXX (XX% of max profit)
   ```

**Total Unrealized Premium**: $XXX.XX (sum of all open position P&L)

### F. Calculate Effective Cost Basis

Now calculate the complete picture:

```
Cost Basis Analysis:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Original Stock Purchase:
  Shares: [X]
  Price per share: $XXX.XX
  Total cost: $X,XXX.XX

Option Premium Impact:
  Realized premium (closed): +$XXX.XX
  Unrealized premium (open): +$XXX.XX
  ────────────────────────────────────
  Total net premium: +$XXX.XX

Effective Cost Basis:
  Adjusted total cost: $X,XXX.XX - $XXX.XX = $X,XXX.XX
  Effective cost per share: $XXX.XX

  Original: $XXX.XX/share
  Effective: $XXX.XX/share
  Reduction: $XX.XX/share (X.X%)
```

### G. Current Position Summary

```
Position Summary for [SYMBOL]:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Stock:
  Current price: $XXX.XX
  Shares: [X]
  Market value: $X,XXX.XX

Cost Basis:
  Effective cost: $XXX.XX/share
  Breakeven: $XXX.XX
  Cushion: $XX.XX (X.X%)

Options Summary:
  Closed positions: [X] ($XXX realized)
  Open positions: [X] ($XXX unrealized)
  Total premium: $XXX.XX

Total P&L:
  Stock gain/loss: $XXX
  Option premium: $XXX
  ────────────────────────────────────
  Combined P&L: $XXX (XX.X% ROI)
```

### H. Risk Assessment

**Assignment Risk** (for open calls):
- If SHORT_CALL positions exist, check distance to strike:
  ```
  Open SHORT_CALL 270C:
  Current price: $XXX.XX
  Strike: $270.00
  Distance: $XX.XX (X.X%)

  Status: ✅ Safe (>5%) / 🟡 Watch (2-5%) / 🔴 Risk (<2%)
  ```

**Recommendation**:
- ✅ **HOLD**: Price well below call strikes, collect theta
- 🟡 **MONITOR**: Price approaching strike, consider rolling
- 🔴 **ACTION**: Price above strike, close or accept assignment

## Step 3: Portfolio Summary

After analyzing all equity holdings:

```
PowerOptions Portfolio Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total Equity Holdings: [X]
Total Shares Value: $X,XXX
Total Original Cost: $X,XXX

Option Activity:
  Closed trades: [X] positions, $XXX realized
  Open trades: [X] positions, $XXX unrealized
  Total premium collected: $XXX

Effective Returns:
  Stock appreciation: $XXX (X.X%)
  Option premium: $XXX (X.X%)
  ────────────────────────────────────
  Combined return: $XXX (X.X% total ROI)

Average cost basis reduction: X.X%
```

## Important Notes

**Always use real-time bid/ask**:
- Never trust cached "current_value" fields
- Always fetch fresh quotes for open positions
- Use ASK when buying back shorts, BID when selling longs

**Cost basis is dynamic**:
- Changes as new options are opened/closed
- Unrealized premium fluctuates with market
- Track both realized (locked in) and unrealized (current)

**PowerOptions Strategy**:
- Goal: Reduce stock cost basis through premium
- Multiple cycles of covered calls over time
- Assignment is acceptable at profitable strikes
