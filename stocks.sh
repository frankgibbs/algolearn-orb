#!/bin/sh
# Stock Trading Service Launch Script - ORB Strategy
# NO DEFAULTS - all parameters required

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

python stocks.py \
  --host $HOST \
  --port $PORT \
  --client $IB_CLIENT_ID \
  --account $ACCOUNT \
  --token $TELEGRAM_TOKEN \
  --chat-id $TELEGRAM_CHAT_ID \
  --orb-period $ORB_PERIOD_MINUTES \
  --risk-pct $RISK_PERCENTAGE \
  --max-positions $MAX_POSITIONS \
  --min-price $MIN_PRICE \
  --max-price $MAX_PRICE \
  --min-volume $MIN_VOLUME \
  --min-pre-market-change $MIN_PRE_MARKET_CHANGE \
  --min-range-pct $MIN_RANGE_PCT \
  --max-range-pct $MAX_RANGE_PCT \
  --volume-lookback-days $VOLUME_LOOKBACK_DAYS \
  --top-n-stocks $TOP_N_STOCKS \
  --min-relative-volume $MIN_RELATIVE_VOLUME \
  --relative-volume-lookback $RELATIVE_VOLUME_LOOKBACK \
  --atr-period $ATR_PERIOD \
  --atr-stop-multiplier $ATR_STOP_MULTIPLIER \
  --min-atr $MIN_ATR