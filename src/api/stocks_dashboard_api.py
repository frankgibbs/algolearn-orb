from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.core.constants import *
import os
import uvicorn
import numpy as np
import pandas as pd
from datetime import datetime, date
from src import logger

class StocksDashboardApi:
    def __init__(self, application_context):
        self.application_context = application_context
        self.state_manager = application_context.state_manager
        self.app = FastAPI()
        self.setup_cors()
        self.setup_routes()
        self.mount_dashboard()

    def setup_cors(self):
        origins = ["*"]  # Allow all origins

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def setup_routes(self):
        @self.app.get("/api")
        async def root():
            return {"message": "Stock trading bot is running"}

        @self.app.get("/api/config")
        async def get_config():
            account_balance = self.application_context.client.get_pair_balance("USD")

            config = self.state_manager.config.copy()
            config[FIELD_ACCOUNT_BALANCE] = account_balance
            return config

        @self.app.get("/api/positions")
        async def get_positions():
            # Get all positions (raw data, no aggregation)
            positions = self.application_context.database_manager.get_all_positions()

            if positions is None or len(positions) == 0:
                return {"positions": []}

            # Helper to calculate return percentage
            def calculate_return(position):
                """Calculate return % from position data"""
                if position.realized_pnl is not None and position.entry_price and position.shares:
                    cost_basis = position.shares * position.entry_price
                    return (position.realized_pnl / cost_basis) if cost_basis > 0 else 0
                return 0

            # Convert to JSON-safe format
            def convert_to_json_safe(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                if isinstance(obj, date):
                    return obj.isoformat()
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                return obj

            # Convert positions to list of dicts - map Position model fields to frontend names
            positions_list = []
            for pos in positions:
                pos_dict = {
                    'id': pos.id,
                    'symbol': pos.symbol,
                    'direction': pos.direction,
                    'quantity': pos.shares,  # Map shares → quantity
                    'entry_price': pos.entry_price,
                    'stop_price': pos.stop_loss_price,  # Map stop_loss_price → stop_price
                    'target_price': pos.take_profit_price,  # Map take_profit_price → target_price
                    'status': pos.status,
                    'entry_date': pos.entry_time,  # Map entry_time → entry_date
                    'exit_date': pos.exit_time,  # Map exit_time → exit_date
                    'exit_price': pos.exit_price,
                    'net_profit': pos.realized_pnl or 0,  # Map realized_pnl → net_profit
                    'net_return': calculate_return(pos),  # Calculate return %
                    'opening_range_id': pos.opening_range_id,
                    'entry_order_id': pos.id,  # Parent order ID
                    'stop_order_id': pos.stop_order_id
                }
                positions_list.append({k: convert_to_json_safe(v) for k, v in pos_dict.items()})

            return {"positions": positions_list}

        @self.app.get("/api/opening-ranges")
        async def get_opening_ranges():
            # Get opening ranges for today (or last 5 days)
            today = datetime.now().date()
            ranges = []

            for i in range(5):  # Last 5 days
                query_date = today - pd.Timedelta(days=i)
                day_ranges = self.application_context.database_manager.get_opening_ranges_by_date(query_date)
                if day_ranges:
                    ranges.extend(day_ranges)

            # Convert to JSON-safe format
            def convert_to_json_safe(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                if isinstance(obj, date):
                    return obj.isoformat()
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                return obj

            ranges_list = []
            for r in ranges:
                range_dict = {
                    'id': r.id,
                    'symbol': r.symbol,
                    'date': r.date,
                    'timeframe_minutes': r.timeframe_minutes,
                    'range_high': r.range_high,
                    'range_low': r.range_low,
                    'range_size': r.range_size,
                    'range_size_pct': r.range_size_pct,
                    'created_at': r.created_at
                }
                ranges_list.append({k: convert_to_json_safe(v) for k, v in range_dict.items()})

            return {"opening_ranges": ranges_list}

        @self.app.get("/api/candidates")
        async def get_candidates():
            # Get candidates for today
            today = datetime.now().date()
            candidates = self.application_context.database_manager.get_candidates(today, selected_only=False)

            if candidates is None or len(candidates) == 0:
                return {"candidates": []}

            # Convert to JSON-safe format
            def convert_to_json_safe(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                if isinstance(obj, date):
                    return obj.isoformat()
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                return obj

            candidates_list = []
            for c in candidates:
                cand_dict = {
                    'id': c.id,
                    'symbol': c.symbol,
                    'date': c.date,
                    'scan_time': c.scan_time,
                    'pre_market_change': c.pre_market_change,
                    'volume': c.volume,
                    'relative_volume': c.relative_volume,
                    'rank': c.rank,
                    'criteria_met': c.criteria_met,
                    'selected': c.selected,
                    'created_at': c.created_at
                }
                candidates_list.append({k: convert_to_json_safe(v) for k, v in cand_dict.items()})

            return {"candidates": candidates_list}

        @self.app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found")

            file_path = os.path.join(self.dashboard_dir, full_path)

            # Check if the path is a directory and serve index.html
            if os.path.isdir(file_path):
                file_path = os.path.join(file_path, 'index.html')

            if os.path.exists(file_path):
                return FileResponse(file_path)

            # Default to serving the main index.html if the file doesn't exist
            return FileResponse(os.path.join(self.dashboard_dir, 'index.html'))

    def mount_dashboard(self):
        # Dashboard build directory
        self.dashboard_dir = '/app/dashboard/build'
        if os.path.exists(self.dashboard_dir):
            self.app.mount("/", StaticFiles(directory=self.dashboard_dir, html=True), name="dashboard")
        else:
            logger.warning(f"Dashboard directory not found: {self.dashboard_dir}")

    def run(self, host="0.0.0.0", port=8080):
        uvicorn.run(self.app, host=host, port=port)
