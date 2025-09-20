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
  --min-volume $MIN_VOLUME