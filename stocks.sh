#!/bin/sh
# Stock Trading Service Launch Script - ORB Strategy
# NO DEFAULTS - all parameters required

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
  --stagnation-minutes $STAGNATION_MINUTES \
  --initial-stop-loss-ratio $INITIAL_STOP_LOSS_RATIO \
  --trailing-stop-ratio $TRAILING_STOP_RATIO \
  --take-profit-ratio $TAKE_PROFIT_RATIO \
  --min-range-pct $MIN_RANGE_PCT \
  --max-range-pct $MAX_RANGE_PCT \
  --volume-lookback-days $VOLUME_LOOKBACK_DAYS \
  --volume-zscore-threshold $VOLUME_ZSCORE_THRESHOLD