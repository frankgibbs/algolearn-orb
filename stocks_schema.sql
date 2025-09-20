-- Stock Trading Database Schema
-- Tables for Opening Range Breakout (ORB) strategy

-- Opening ranges table - stores daily opening ranges for stocks
CREATE TABLE IF NOT EXISTS opening_ranges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    range_high DECIMAL(10,4) NOT NULL,
    range_low DECIMAL(10,4) NOT NULL,
    range_size DECIMAL(10,4) NOT NULL,
    range_size_pct DECIMAL(5,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Stock candidates table - stores pre-market scan results
CREATE TABLE IF NOT EXISTS stock_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    scan_time TIME NOT NULL,
    pre_market_change DECIMAL(5,2) NOT NULL,
    volume INTEGER NOT NULL,
    relative_volume DECIMAL(5,2) NOT NULL,
    rank INTEGER NOT NULL,
    criteria_met TEXT NOT NULL,
    selected BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Trade decisions table - audit trail of all trading decisions
CREATE TABLE IF NOT EXISTS trade_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    time TIME NOT NULL,
    action VARCHAR(10) NOT NULL,
    reason TEXT NOT NULL,
    confidence DECIMAL(3,0) NOT NULL,
    executed BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Stock trades table - extends existing trades table for stock-specific data
-- Note: Stock trades will use the existing 'trades' table with strategy_name = 'ORB'
-- Additional stock-specific columns may be added via migrations:
-- ALTER TABLE trades ADD COLUMN opening_range_id INTEGER;
-- ALTER TABLE trades ADD COLUMN breakout_direction VARCHAR(10);
-- ALTER TABLE trades ADD COLUMN range_size_pct DECIMAL(5,2);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_opening_ranges_symbol_date ON opening_ranges(symbol, date);
CREATE INDEX IF NOT EXISTS idx_stock_candidates_date_rank ON stock_candidates(date, rank);
CREATE INDEX IF NOT EXISTS idx_trade_decisions_symbol_date ON trade_decisions(symbol, date);

-- Sample queries for reference:

-- Get today's opening ranges
-- SELECT * FROM opening_ranges WHERE date = DATE('now');

-- Get top 10 candidates for today
-- SELECT * FROM stock_candidates WHERE date = DATE('now') AND selected = TRUE ORDER BY rank LIMIT 10;

-- Get all trade decisions for a symbol today
-- SELECT * FROM trade_decisions WHERE symbol = 'AAPL' AND date = DATE('now') ORDER BY time;

-- Get stock trades (from existing trades table)
-- SELECT * FROM trades WHERE strategy_name = 'ORB' AND date = DATE('now');