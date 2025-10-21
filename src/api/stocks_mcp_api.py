#!/usr/bin/env python3
"""
MCP Server for Stocks Trading Real-Time Data
Provides real-time ORB strategy tools for Claude CLI analysis
"""

import asyncio
import json
import os
import sys
from typing import Any, Sequence
from datetime import datetime, timedelta
import pandas as pd

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
from pydantic import AnyUrl

from src.core.constants import *
from src.stocks.services.stocks_scanner_service import StocksScannerService
from src.stocks.services.stocks_strategy_service import StocksStrategyService
from src.stocks.services.volatility_service import VolatilityService
from src import logger

class StocksMcpApi:
    """MCP Server for Stocks ORB trading data"""

    def __init__(self, application_context):
        self.server = Server("stocks-orb")
        self.application_context = application_context
        self.database_manager = application_context.database_manager
        self._setup_tools()
        self._setup_resources()

    def _setup_tools(self):
        """Setup MCP tools"""

        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available tools"""
            return [
                Tool(
                    name="run_pre_market_scan",
                    description="Execute pre-market scan for ORB candidates with configurable criteria",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "min_price": {
                                "type": "number",
                                "description": "Minimum stock price filter",
                                "default": 5.0,
                                "minimum": 1.0,
                                "maximum": 500.0
                            },
                            "max_price": {
                                "type": "number",
                                "description": "Maximum stock price filter",
                                "default": 100.0,
                                "minimum": 5.0,
                                "maximum": 1000.0
                            },
                            "min_volume": {
                                "type": "integer",
                                "description": "Minimum daily volume",
                                "default": 100000,
                                "minimum": 10000,
                                "maximum": 10000000
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of candidates to return",
                                "default": 50,
                                "minimum": 10,
                                "maximum": 100
                            },
                            "min_pre_market_change": {
                                "type": "number",
                                "description": "Minimum pre-market percentage change",
                                "default": 2.0,
                                "minimum": 0.5,
                                "maximum": 20.0
                            }
                        },
                        "required": []
                    },
                ),
                Tool(
                    name="get_current_candidates",
                    description="Get current stock candidates from the most recent scan",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of candidates to return",
                                "default": 25,
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        "required": []
                    },
                ),
                Tool(
                    name="get_scanner_types",
                    description="Get list of available IB scanner types for stock scanning",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                Tool(
                    name="get_stock_bars",
                    description="Get historical OHLC bars for a stock symbol using IB native format",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Stock symbol (e.g., AAPL)"
                            },
                            "duration": {
                                "type": "string",
                                "description": "IB duration format: '252 D' (days), '390 S' (seconds), '1 M' (months)",
                                "default": "390 S"
                            },
                            "bar_size": {
                                "type": "string",
                                "description": "IB bar size: '1 day', '30 mins', '1 hour', etc.",
                                "default": "30 mins"
                            }
                        },
                        "required": ["symbol"]
                    }
                ),
                Tool(
                    name="get_opening_ranges",
                    description="Monitor and retrieve opening ranges from database for ORB strategy",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date to query (YYYY-MM-DD format, defaults to today PST)",
                                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
                            },
                            "include_all": {
                                "type": "boolean",
                                "description": "Include all ranges in database for debugging",
                                "default": False
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "Number of days back to include",
                                "default": 1,
                                "minimum": 1,
                                "maximum": 30
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="get_all_positions",
                    description="Retrieve all positions regardless of status",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "date_from": {
                                "type": "string",
                                "description": "Start date filter (YYYY-MM-DD format)",
                                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
                            },
                            "date_to": {
                                "type": "string",
                                "description": "End date filter (YYYY-MM-DD format)",
                                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
                            },
                            "symbol": {
                                "type": "string",
                                "description": "Filter by specific symbol (e.g., AAPL)"
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "Number of days back from today (alternative to date_from/date_to)",
                                "default": 1,
                                "minimum": 1,
                                "maximum": 365
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="get_current_implied_volatility",
                    description="Get current at-the-money (ATM) implied volatility for options strategy analysis",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Stock symbol (e.g., AAPL)"
                            }
                        },
                        "required": ["symbol"]
                    }
                ),
                Tool(
                    name="get_volatility_term_structure",
                    description="Get implied volatility term structure across multiple expirations",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Stock symbol (e.g., AAPL)"
                            },
                            "target_days": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Target days to expiration (e.g., [30, 60, 90])",
                                "default": [30, 60, 90]
                            }
                        },
                        "required": ["symbol"]
                    }
                ),
                Tool(
                    name="analyze_volatility",
                    description="Perform complete real-time volatility analysis including IV, HV, IV/HV ratio, and term structure",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Stock symbol (e.g., AAPL)"
                            }
                        },
                        "required": ["symbol"]
                    }
                ),
                Tool(
                    name="get_option_quote",
                    description="Get real-time option quote with bid/ask prices and Greeks",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Stock symbol (e.g., AAPL)"
                            },
                            "expiry": {
                                "type": "string",
                                "description": "Expiration date in YYYYMMDD format (e.g., 20251107)"
                            },
                            "strike": {
                                "type": "number",
                                "description": "Strike price (e.g., 240)"
                            },
                            "right": {
                                "type": "string",
                                "description": "Option type: 'C' for call, 'P' for put",
                                "enum": ["C", "P"]
                            }
                        },
                        "required": ["symbol", "expiry", "strike", "right"]
                    }
                ),
                Tool(
                    name="place_options_spread",
                    description="Place a multi-leg option spread order (vertical spreads, iron condors, etc.)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Stock symbol (e.g., AAPL)"
                            },
                            "strategy_type": {
                                "type": "string",
                                "description": "Strategy name (e.g., BULL_PUT_SPREAD, BEAR_CALL_SPREAD, IRON_CONDOR)",
                                "enum": ["BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "IRON_CONDOR", "IRON_BUTTERFLY"]
                            },
                            "legs": {
                                "type": "array",
                                "description": "List of leg dictionaries with keys: action (BUY/SELL), strike, right (C/P), expiry (YYYYMMDD), quantity",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "action": {"type": "string", "enum": ["BUY", "SELL"]},
                                        "strike": {"type": "number"},
                                        "right": {"type": "string", "enum": ["C", "P"]},
                                        "expiry": {"type": "string"},
                                        "quantity": {"type": "integer", "default": 1}
                                    },
                                    "required": ["action", "strike", "right", "expiry"]
                                }
                            },
                            "limit_price": {
                                "type": "number",
                                "description": "Net credit (positive) or debit (negative) for the spread"
                            },
                            "expiration_date": {
                                "type": "string",
                                "description": "Expiration datetime in ISO format (YYYY-MM-DDTHH:MM:SS)"
                            },
                            "entry_iv": {
                                "type": "number",
                                "description": "Current implied volatility at entry (decimal, e.g., 0.30 for 30%)"
                            },
                            "time_in_force": {
                                "type": "string",
                                "description": "Order time in force",
                                "enum": ["DAY", "GTC"],
                                "default": "DAY"
                            }
                        },
                        "required": ["symbol", "strategy_type", "legs", "limit_price", "expiration_date", "entry_iv"]
                    }
                ),
                Tool(
                    name="cancel_option_order",
                    description="Cancel a pending option order",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "order_id": {
                                "type": "integer",
                                "description": "Order ID to cancel"
                            }
                        },
                        "required": ["order_id"]
                    }
                ),
                Tool(
                    name="list_working_orders",
                    description="List all pending/working option orders",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Optional symbol filter (e.g., AAPL)"
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="list_option_positions",
                    description="List all open option positions with current P&L",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Optional symbol filter (e.g., AAPL)"
                            }
                        },
                        "required": []
                    }
                ),
                Tool(
                    name="analyze_option_position",
                    description="Analyze an option position and get exit/management recommendation",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "order_id": {
                                "type": "integer",
                                "description": "Position order ID to analyze"
                            }
                        },
                        "required": ["order_id"]
                    }
                ),
                Tool(
                    name="close_option_position",
                    description="Close an open option position by placing offsetting order",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "opening_order_id": {
                                "type": "integer",
                                "description": "Original position order ID to close"
                            },
                            "exit_reason": {
                                "type": "string",
                                "description": "Reason for closing (e.g., PROFIT_TARGET, MANUAL_CLOSE)",
                                "default": "MANUAL_CLOSE"
                            },
                            "limit_price": {
                                "type": "number",
                                "description": "Optional limit price for closing order (if not provided, calculated from market)"
                            }
                        },
                        "required": ["opening_order_id"]
                    }
                ),
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
            """Handle tool calls"""

            try:
                if name == "run_pre_market_scan":
                    return await self._run_pre_market_scan(arguments or {})
                elif name == "get_current_candidates":
                    return await self._get_current_candidates(arguments or {})
                elif name == "get_scanner_types":
                    return await self._get_scanner_types(arguments or {})
                elif name == "get_stock_bars":
                    return await self._get_stock_bars(arguments or {})
                elif name == "get_opening_ranges":
                    return await self._get_opening_ranges(arguments or {})
                elif name == "get_all_positions":
                    return await self._get_all_positions(arguments or {})
                elif name == "get_current_implied_volatility":
                    return await self._get_current_implied_volatility(arguments or {})
                elif name == "get_volatility_term_structure":
                    return await self._get_volatility_term_structure(arguments or {})
                elif name == "analyze_volatility":
                    return await self._analyze_volatility(arguments or {})
                elif name == "get_option_quote":
                    return await self._get_option_quote(arguments or {})
                elif name == "place_options_spread":
                    return await self._place_options_spread(arguments or {})
                elif name == "cancel_option_order":
                    return await self._cancel_option_order(arguments or {})
                elif name == "list_working_orders":
                    return await self._list_working_orders(arguments or {})
                elif name == "list_option_positions":
                    return await self._list_option_positions(arguments or {})
                elif name == "analyze_option_position":
                    return await self._analyze_option_position(arguments or {})
                elif name == "close_option_position":
                    return await self._close_option_position(arguments or {})
                else:
                    raise ValueError(f"Unknown tool: {name}")
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {str(e)}", meta={})]

    def _setup_resources(self):
        """Setup MCP resources"""

        @self.server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            """List available resources"""
            return [
                Resource(
                    uri=AnyUrl("stocks://candidates/current"),
                    name="Current Stock Candidates",
                    description="Most recent pre-market scan candidates",
                    mimeType="application/json",
                ),
                Resource(
                    uri=AnyUrl("stocks://config"),
                    name="ORB Strategy Configuration",
                    description="Current ORB strategy configuration and parameters",
                    mimeType="application/json",
                ),
            ]

        @self.server.read_resource()
        async def handle_read_resource(uri: AnyUrl) -> str:
            """Read resource content"""
            if str(uri) == "stocks://candidates/current":
                # Get current candidates from database
                candidates = self.database_manager.get_current_stock_candidates()
                return json.dumps([{
                    "symbol": candidate.symbol,
                    "scan_time": candidate.scan_time.isoformat() if candidate.scan_time else None,
                    "rank": candidate.rank,
                    "pre_market_change": candidate.pre_market_change,
                    "volume": candidate.volume,
                    "relative_volume": candidate.relative_volume,
                    "criteria_met": candidate.criteria_met
                } for candidate in candidates], indent=2)
            elif str(uri) == "stocks://config":
                return json.dumps({
                    "server_info": {
                        "name": "Stocks ORB Trading MCP Server",
                        "version": "1.0.0",
                        "capabilities": [
                            "pre_market_scanning",
                            "candidate_analysis",
                            "orb_strategy_monitoring"
                        ]
                    }
                }, indent=2)
            else:
                raise ValueError(f"Unknown resource: {uri}")

    async def _run_pre_market_scan(self, args: dict) -> list[TextContent]:
        """Execute pre-market scan with provided criteria"""
        try:
            # Extract parameters with defaults
            min_price = args.get("min_price", 5.0)
            max_price = args.get("max_price", 100.0)
            min_volume = args.get("min_volume", 100000)
            max_results = args.get("max_results", 50)
            min_pre_market_change = args.get("min_pre_market_change", 2.0)

            # Create scanner criteria (all parameters provided with defaults)
            scan_criteria = {
                "min_price": min_price,
                "max_price": max_price,
                "min_volume": min_volume,
                "max_results": max_results,
                "min_pre_market_change": min_pre_market_change
            }

            # Initialize services
            scanner_service = StocksScannerService(self.application_context)
            strategy_service = StocksStrategyService(self.application_context)

            # Execute scanner
            logger.info(f"MCP: Running pre-market scan with criteria: {scan_criteria}")
            scanner_results = scanner_service.scan_pre_market_movers(scan_criteria)

            # Format results
            candidates = scanner_service.format_scanner_results(
                scanner_results,
                scan_criteria,
                datetime.now()
            )

            # Save to database
            strategy_service.save_candidates(candidates, datetime.now())

            # Format response
            result = {
                "scan_timestamp": datetime.now().isoformat(),
                "criteria_used": scan_criteria,
                "total_candidates_found": len(candidates),
                "candidates": candidates[:25],  # Limit display to top 25
                "summary": {
                    "avg_pre_market_change": round(sum(c.get("pre_market_change", 0) for c in candidates) / len(candidates), 2) if candidates else 0,
                    "price_range": {
                        "min": min(float(r.get('benchmark', '0') or 0) for r in scanner_results) if scanner_results else 0,
                        "max": max(float(r.get('benchmark', '0') or 0) for r in scanner_results) if scanner_results else 0
                    }
                },
                "debug_info": {
                    "scanner_codes_used": ["TOP_PERC_GAIN", "MOST_ACTIVE", "HOT_BY_VOLUME"],
                    "total_raw_results": len(scanner_results) if scanner_results else 0,
                    "filtering_applied": True,
                    "saved_to_database": True
                }
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _run_pre_market_scan: {e}")
            return [TextContent(type="text", text=f"Error running pre-market scan: {str(e)}", meta={})]

    async def _get_current_candidates(self, args: dict) -> list[TextContent]:
        """Get current stock candidates from database"""
        try:
            limit = args.get("limit", 25)

            # Get candidates from database
            candidates = self.database_manager.get_current_stock_candidates(limit)

            # Convert to JSON-serializable format
            candidates_data = []
            for candidate in candidates:
                candidate_data = {
                    "symbol": candidate.symbol,
                    "scan_time": candidate.scan_time.isoformat() if candidate.scan_time else None,
                    "rank": candidate.rank,
                    "pre_market_change": candidate.pre_market_change,
                    "volume": candidate.volume,
                    "relative_volume": candidate.relative_volume,
                    "criteria_met": candidate.criteria_met
                }
                candidates_data.append(candidate_data)

            result = {
                "timestamp": datetime.now().isoformat(),
                "total_candidates": len(candidates_data),
                "candidates": candidates_data,
                "summary": {
                    "most_recent_scan": candidates_data[0]["scan_time"] if candidates_data else None,
                    "avg_change": round(sum(c["pre_market_change"] for c in candidates_data) / len(candidates_data), 2) if candidates_data else 0,
                    "top_mover": max(candidates_data, key=lambda x: abs(x["pre_market_change"]))["symbol"] if candidates_data else None
                }
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _get_current_candidates: {e}")
            return [TextContent(type="text", text=f"Error getting current candidates: {str(e)}", meta={})]

    async def _get_scanner_types(self, args: dict) -> list[TextContent]:
        """Get available scanner types from IB"""
        try:
            scanner_service = StocksScannerService(self.application_context)
            scanner_codes = scanner_service.get_available_scanner_types()

            result = {
                "timestamp": datetime.now().isoformat(),
                "total_scanner_types": len(scanner_codes),
                "available_scanners": scanner_codes,
                "recommended_for_orb": [
                    "TOP_PERC_GAIN",
                    "MOST_ACTIVE",
                    "HOT_BY_VOLUME",
                    "HIGH_OPT_IMP_VOLAT"
                ]
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error getting scanner types: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}", meta={})]

    async def _get_stock_bars(self, args: dict) -> list[TextContent]:
        """Get historical OHLC bars for analysis using IB native format"""
        symbol = args.get("symbol")
        duration = args.get("duration", "390 S")  # Default: 390 seconds (6.5 hours)
        bar_size = args.get("bar_size", "30 mins")  # Default: 30 min bars

        if not symbol:
            return [TextContent(type="text", text="Error: symbol is required")]

        try:
            # Use volatility service for consistent handling
            volatility_service = VolatilityService(self.application_context)
            bars = volatility_service.get_historical_prices(
                symbol=symbol,
                duration=duration,
                bar_size=bar_size
            )

            if bars is None or bars.empty:
                return [TextContent(type="text", text=f"No data available for {symbol}")]

            # Format bars for output
            result = {
                "symbol": symbol,
                "duration": duration,
                "bar_size": bar_size,
                "bar_count": len(bars),
                "bars": []
            }

            for i, row in bars.iterrows():
                result["bars"].append({
                    "index": i,
                    "datetime": str(row['date']),
                    "open": row['open'],
                    "high": row['high'],
                    "low": row['low'],
                    "close": row['close'],
                    "volume": row.get('volume', 0)
                })

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str)
            )]

        except Exception as e:
            logger.error(f"Error in _get_stock_bars: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _get_opening_ranges(self, args: dict) -> list[TextContent]:
        """Monitor and retrieve opening ranges from database"""
        try:
            import pytz
            from datetime import datetime, timedelta

            # Get parameters
            date_str = args.get("date")
            include_all = args.get("include_all", False)
            days_back = args.get("days_back", 1)

            # Get current PST time
            pst_tz = pytz.timezone('US/Pacific')
            now_pst = datetime.now(pst_tz)
            today_pst = now_pst.date()

            # Parse target date or use today
            if date_str:
                from datetime import datetime as dt
                target_date = dt.strptime(date_str, '%Y-%m-%d').date()
            else:
                target_date = today_pst

            # Query ranges for target date
            ranges_for_date = self.database_manager.get_opening_ranges_by_date(target_date)

            # Get all ranges if requested
            all_ranges = []
            if include_all:
                # Query all ranges in database
                session = self.database_manager.get_session()
                try:
                    from src.stocks.models.opening_range import OpeningRange
                    all_ranges = session.query(OpeningRange).order_by(OpeningRange.date.desc()).limit(100).all()
                finally:
                    session.close()

            # Get recent ranges (last N days)
            recent_ranges = []
            for i in range(days_back):
                check_date = today_pst - timedelta(days=i)
                ranges_on_date = self.database_manager.get_opening_ranges_by_date(check_date)
                for r in ranges_on_date:
                    recent_ranges.append({
                        'symbol': r.symbol,
                        'date': r.date.isoformat(),
                        'timeframe_minutes': r.timeframe_minutes,
                        'range_high': r.range_high,
                        'range_low': r.range_low,
                        'range_size': r.range_size,
                        'range_size_pct': r.range_size_pct,
                        'created_at': r.created_at.isoformat() if r.created_at else None
                    })

            # Format target date ranges
            target_ranges = []
            for r in ranges_for_date:
                target_ranges.append({
                    'symbol': r.symbol,
                    'date': r.date.isoformat(),
                    'timeframe_minutes': r.timeframe_minutes,
                    'range_high': r.range_high,
                    'range_low': r.range_low,
                    'range_size': r.range_size,
                    'range_size_pct': r.range_size_pct,
                    'created_at': r.created_at.isoformat() if r.created_at else None
                })

            # Build result
            result = {
                "timestamp": now_pst.isoformat(),
                "current_pst_time": now_pst.strftime('%Y-%m-%d %H:%M:%S %Z'),
                "today_pst_date": today_pst.isoformat(),
                "query_info": {
                    "target_date": target_date.isoformat(),
                    "days_back_requested": days_back,
                    "include_all_requested": include_all
                },
                "ranges_for_target_date": {
                    "count": len(target_ranges),
                    "ranges": target_ranges
                },
                "recent_ranges": {
                    "count": len(recent_ranges),
                    "ranges": recent_ranges
                }
            }

            # Add all ranges if requested
            if include_all:
                all_ranges_data = []
                for r in all_ranges:
                    all_ranges_data.append({
                        'symbol': r.symbol,
                        'date': r.date.isoformat(),
                        'timeframe_minutes': r.timeframe_minutes,
                        'range_high': r.range_high,
                        'range_low': r.range_low,
                        'range_size': r.range_size,
                        'range_size_pct': r.range_size_pct,
                        'created_at': r.created_at.isoformat() if r.created_at else None
                    })

                result["all_ranges"] = {
                    "count": len(all_ranges_data),
                    "ranges": all_ranges_data[:50]  # Limit to first 50 for display
                }

            # Add summary
            result["summary"] = {
                "ranges_today": len([r for r in recent_ranges if r['date'] == today_pst.isoformat()]),
                "total_recent_ranges": len(recent_ranges),
                "unique_symbols_recent": len(set(r['symbol'] for r in recent_ranges)),
                "date_match": target_date == today_pst,
                "database_has_data": len(recent_ranges) > 0 or (include_all and len(all_ranges) > 0)
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _get_opening_ranges: {e}")
            return [TextContent(type="text", text=f"Error getting opening ranges: {str(e)}", meta={})]


    async def _get_all_positions(self, args: dict) -> list[TextContent]:
        """Get all positions regardless of status"""
        try:
            import pytz
            from datetime import datetime, timedelta

            # Get parameters
            date_from_str = args.get("date_from")
            date_to_str = args.get("date_to")
            symbol = args.get("symbol")
            days_back = args.get("days_back")

            # Parse dates or use days_back - only filter if explicitly provided
            now = datetime.now()

            if date_from_str and date_to_str:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            elif days_back:
                date_from = (now - timedelta(days=days_back)).date()
                date_to = now.date()
            else:
                # No date filtering - get all positions
                date_from = None
                date_to = None

            # Get all positions from database
            positions = self.database_manager.get_all_positions(
                date_from=date_from,
                date_to=date_to,
                symbol=symbol
            )

            # Format positions
            positions_data = []
            for position in positions:
                position_data = {
                    "id": position.id,
                    "symbol": position.symbol,
                    "direction": position.direction,
                    "shares": position.shares,
                    "status": position.status,
                    "entry_time": position.entry_time.isoformat() if position.entry_time else None,
                    "entry_price": position.entry_price,
                    "exit_time": position.exit_time.isoformat() if position.exit_time else None,
                    "exit_price": position.exit_price,
                    "exit_reason": position.exit_reason,
                    "realized_pnl": position.realized_pnl,
                    "stop_loss_price": position.stop_loss_price,
                    "take_profit_price": position.take_profit_price,
                    "range_size": position.range_size,
                    "created_at": position.created_at.isoformat() if position.created_at else None,
                    "updated_at": position.updated_at.isoformat() if position.updated_at else None
                }
                positions_data.append(position_data)

            # Build result
            result = {
                "timestamp": now.isoformat(),
                "query_info": {
                    "date_from": date_from.isoformat() if date_from else None,
                    "date_to": date_to.isoformat() if date_to else None,
                    "symbol_filter": symbol,
                    "days_back": days_back
                },
                "total_positions": len(positions_data),
                "positions": positions_data
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _get_all_positions: {e}")
            return [TextContent(type="text", text=f"Error getting all positions: {str(e)}", meta={})]

    async def _get_current_implied_volatility(self, args: dict) -> list[TextContent]:
        """Get current at-the-money implied volatility"""
        symbol = args.get("symbol")

        if not symbol:
            return [TextContent(type="text", text="Error: symbol is required", meta={})]

        try:
            # Initialize volatility service
            volatility_service = VolatilityService(self.application_context)

            # Get ATM IV
            iv_data = volatility_service.get_current_atm_iv(symbol)

            result = {
                "timestamp": datetime.now().isoformat(),
                "symbol": symbol,
                "data": iv_data
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _get_current_implied_volatility: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}", meta={})]

    async def _get_volatility_term_structure(self, args: dict) -> list[TextContent]:
        """Get volatility term structure across multiple expirations"""
        symbol = args.get("symbol")
        target_days = args.get("target_days", [30, 60, 90])

        if not symbol:
            return [TextContent(type="text", text="Error: symbol is required", meta={})]

        try:
            # Initialize volatility service
            volatility_service = VolatilityService(self.application_context)

            # Get term structure
            term_structure_data = volatility_service.get_volatility_term_structure(
                symbol=symbol,
                target_days=target_days
            )

            result = {
                "timestamp": datetime.now().isoformat(),
                "data": term_structure_data
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _get_volatility_term_structure: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}", meta={})]

    async def _analyze_volatility(self, args: dict) -> list[TextContent]:
        """Perform complete volatility analysis"""
        symbol = args.get("symbol")

        if not symbol:
            return [TextContent(type="text", text="Error: symbol is required", meta={})]

        try:
            # Initialize volatility service
            volatility_service = VolatilityService(self.application_context)

            # Perform complete analysis
            analysis = volatility_service.analyze_complete_volatility(symbol)

            return [TextContent(type="text", text=json.dumps(analysis, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _analyze_volatility: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}", meta={})]

    async def _get_option_quote(self, args: dict) -> list[TextContent]:
        """Get real-time option quote with bid/ask and Greeks"""
        symbol = args.get("symbol")
        expiry = args.get("expiry")
        strike = args.get("strike")
        right = args.get("right")

        # Validate required parameters
        if not symbol:
            return [TextContent(type="text", text="Error: symbol is required", meta={})]
        if not expiry:
            return [TextContent(type="text", text="Error: expiry is required", meta={})]
        if strike is None:
            return [TextContent(type="text", text="Error: strike is required", meta={})]
        if not right:
            return [TextContent(type="text", text="Error: right is required (C or P)", meta={})]
        if right not in ["C", "P"]:
            return [TextContent(type="text", text="Error: right must be 'C' (call) or 'P' (put)", meta={})]

        try:
            # Get option Greeks and pricing from IB
            greeks_data = self.application_context.client.get_option_greeks(
                symbol=symbol,
                expiry=expiry,
                strike=strike,
                right=right
            )

            if not greeks_data:
                return [TextContent(type="text", text=f"No data available for {symbol} {strike}{right} exp:{expiry}", meta={})]

            # Format result
            result = {
                "timestamp": datetime.now().isoformat(),
                "symbol": symbol,
                "strike": strike,
                "expiry": expiry,
                "right": right,
                "bid": greeks_data.get('bid'),
                "ask": greeks_data.get('ask'),
                "last": greeks_data.get('last'),
                "mid": (greeks_data.get('bid', 0) + greeks_data.get('ask', 0)) / 2 if greeks_data.get('bid') and greeks_data.get('ask') else None,
                "volume": greeks_data.get('volume'),
                "open_interest": greeks_data.get('open_interest'),
                "greeks": {
                    "iv": greeks_data.get('iv'),
                    "delta": greeks_data.get('delta'),
                    "gamma": greeks_data.get('gamma'),
                    "theta": greeks_data.get('theta'),
                    "vega": greeks_data.get('vega')
                },
                "underlying_price": greeks_data.get('underlying_price')
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _get_option_quote: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}", meta={})]

    async def _place_options_spread(self, args: dict) -> list[TextContent]:
        """Place a multi-leg option spread order"""
        from src.options.services.option_order_service import OptionOrderService

        symbol = args.get("symbol")
        strategy_type = args.get("strategy_type")
        legs = args.get("legs")
        limit_price = args.get("limit_price")
        expiration_date_str = args.get("expiration_date")
        entry_iv = args.get("entry_iv")
        time_in_force = args.get("time_in_force", "DAY")

        # Validate required parameters
        if not symbol:
            return [TextContent(type="text", text="Error: symbol is required", meta={})]
        if not strategy_type:
            return [TextContent(type="text", text="Error: strategy_type is required", meta={})]
        if not legs or len(legs) < 2:
            return [TextContent(type="text", text="Error: legs is required and must have at least 2 legs", meta={})]
        if limit_price is None:
            return [TextContent(type="text", text="Error: limit_price is required", meta={})]
        if not expiration_date_str:
            return [TextContent(type="text", text="Error: expiration_date is required", meta={})]
        if entry_iv is None or entry_iv <= 0:
            return [TextContent(type="text", text="Error: entry_iv is required and must be > 0", meta={})]

        try:
            # Parse expiration date
            expiration_date = datetime.fromisoformat(expiration_date_str)

            # Initialize service
            order_service = OptionOrderService(self.application_context)

            # Place the spread order
            order_result = order_service.place_spread(
                symbol=symbol,
                strategy_type=strategy_type,
                legs=legs,
                limit_price=limit_price,
                expiration_date=expiration_date,
                entry_iv=entry_iv,
                time_in_force=time_in_force
            )

            # Format result
            result = {
                "timestamp": datetime.now().isoformat(),
                "order_id": order_result['order_id'],
                "symbol": symbol,
                "strategy_type": strategy_type,
                "status": order_result['status'],
                "message": order_result['message'],
                "max_risk": order_result['max_risk'],
                "max_profit": order_result['max_profit'],
                "roi_target": order_result['roi_target'],
                "legs": legs,
                "limit_price": limit_price,
                "time_in_force": time_in_force
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _place_options_spread: {e}")
            return [TextContent(type="text", text=f"Error placing option spread: {str(e)}", meta={})]

    async def _cancel_option_order(self, args: dict) -> list[TextContent]:
        """Cancel a pending option order"""
        from src.options.services.option_order_service import OptionOrderService

        order_id = args.get("order_id")

        if not order_id:
            return [TextContent(type="text", text="Error: order_id is required", meta={})]

        try:
            # Initialize service
            order_service = OptionOrderService(self.application_context)

            # Cancel the order
            cancel_result = order_service.cancel_order(order_id)

            # Format result
            result = {
                "timestamp": datetime.now().isoformat(),
                "order_id": cancel_result['order_id'],
                "status": cancel_result['status'],
                "message": cancel_result['message']
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _cancel_option_order: {e}")
            return [TextContent(type="text", text=f"Error canceling option order: {str(e)}", meta={})]

    async def _close_option_position(self, args: dict) -> list[TextContent]:
        """Close an open option position by placing offsetting order"""
        from src.options.services.option_order_service import OptionOrderService

        opening_order_id = args.get("opening_order_id")
        exit_reason = args.get("exit_reason", "MANUAL_CLOSE")
        limit_price = args.get("limit_price")

        if not opening_order_id:
            return [TextContent(type="text", text="Error: opening_order_id is required", meta={})]

        try:
            # Initialize service
            order_service = OptionOrderService(self.application_context)

            # Close the position
            close_result = order_service.close_position(
                opening_order_id=opening_order_id,
                exit_reason=exit_reason,
                limit_price=limit_price
            )

            # Format result
            result = {
                "timestamp": datetime.now().isoformat(),
                "opening_order_id": close_result['opening_order_id'],
                "closing_order_id": close_result['closing_order_id'],
                "status": close_result['status'],
                "message": close_result['message'],
                "limit_price": close_result['limit_price'],
                "expected_pnl": close_result['expected_pnl'],
                "exit_reason": close_result['exit_reason']
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _close_option_position: {e}")
            return [TextContent(type="text", text=f"Error closing option position: {str(e)}", meta={})]

    async def _list_working_orders(self, args: dict) -> list[TextContent]:
        """List all pending/working option orders"""
        from src.options.services.option_order_service import OptionOrderService

        symbol = args.get("symbol")

        try:
            # Initialize service
            order_service = OptionOrderService(self.application_context)

            # Get working orders
            working_orders = order_service.list_working_orders(symbol=symbol)

            # Format result
            result = {
                "timestamp": datetime.now().isoformat(),
                "total_working_orders": len(working_orders),
                "working_orders": working_orders,
                "summary": {
                    "unique_symbols": len(set(order['symbol'] for order in working_orders)),
                    "total_credit_at_risk": sum(order.get('max_risk', 0) for order in working_orders)
                }
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _list_working_orders: {e}")
            return [TextContent(type="text", text=f"Error listing working orders: {str(e)}", meta={})]

    async def _list_option_positions(self, args: dict) -> list[TextContent]:
        """List all open option positions with current P&L"""
        from src.options.services.option_position_service import OptionPositionService

        symbol = args.get("symbol")

        try:
            # Initialize service
            position_service = OptionPositionService(self.application_context)

            # Get open positions with updated P&L
            positions = position_service.list_open_positions(symbol=symbol)

            # Calculate summary stats
            total_unrealized_pnl = sum(pos.get('unrealized_pnl', 0) for pos in positions)
            total_max_risk = sum(pos.get('max_risk', 0) for pos in positions)
            avg_dte = sum(pos.get('dte', 0) for pos in positions) / len(positions) if positions else 0

            # Format result
            result = {
                "timestamp": datetime.now().isoformat(),
                "total_open_positions": len(positions),
                "positions": positions,
                "summary": {
                    "total_unrealized_pnl": total_unrealized_pnl,
                    "total_max_risk": total_max_risk,
                    "average_dte": round(avg_dte, 1),
                    "positions_at_profit_target": len([p for p in positions if p.get('profit_target_hit')]),
                    "positions_needing_management": len([p for p in positions if p.get('needs_management')]),
                    "unique_symbols": len(set(p['symbol'] for p in positions))
                }
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _list_option_positions: {e}")
            return [TextContent(type="text", text=f"Error listing option positions: {str(e)}", meta={})]

    async def _analyze_option_position(self, args: dict) -> list[TextContent]:
        """Analyze an option position and provide exit/management recommendation"""
        from src.options.services.option_analyzer_service import OptionAnalyzerService

        order_id = args.get("order_id")

        if not order_id:
            return [TextContent(type="text", text="Error: order_id is required", meta={})]

        try:
            # Initialize service
            analyzer_service = OptionAnalyzerService(self.application_context)

            # Analyze the position
            analysis = analyzer_service.analyze_position(order_id)

            # Format result
            result = {
                "timestamp": datetime.now().isoformat(),
                "analysis": analysis,
                "action_summary": {
                    "recommendation": analysis['recommendation'],
                    "reason": analysis['reason'],
                    "suggested_action": analysis['suggested_action']
                },
                "position_metrics": analysis['metrics']
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2), meta={})]

        except Exception as e:
            logger.error(f"Error in _analyze_option_position: {e}")
            return [TextContent(type="text", text=f"Error analyzing option position: {str(e)}", meta={})]

    def run(self, host="0.0.0.0", port=8003):
        """Run the MCP server with both HTTP endpoints and MCP protocol support"""
        import logging
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        import uvicorn
        from src import logger

        # Create FastAPI app
        app = FastAPI(title="Stocks ORB Trading MCP Server", version="1.0.0")

        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/")
        async def root():
            return {
                "name": "Stocks ORB Trading MCP Server",
                "version": "1.0.0",
                "status": "running",
                "available_tools": [
                    "run_pre_market_scan",
                    "get_current_candidates",
                    "get_scanner_types",
                    "get_stock_bars",
                    "get_opening_ranges",
                    "get_all_positions",
                    "get_current_implied_volatility",
                    "get_volatility_term_structure",
                    "analyze_volatility",
                    "get_option_quote",
                    "place_options_spread",
                    "cancel_option_order",
                    "close_option_position",
                    "list_working_orders",
                    "list_option_positions",
                    "analyze_option_position"
                ]
            }

        @app.post("/mcp")
        async def mcp_endpoint(request: Request):
            """MCP protocol endpoint for Claude Code integration"""
            try:
                # Get the request body
                body = await request.json()

                # Handle MCP protocol messages
                if body.get("method") == "initialize":
                    return {
                        "jsonrpc": "2.0",
                        "id": body.get("id"),
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "tools": {},
                                "resources": {}
                            },
                            "serverInfo": {
                                "name": "stocks-orb",
                                "version": "1.0.0"
                            }
                        }
                    }
                elif body.get("method") == "tools/list":
                    # Return the complete tool list
                    return {
                        "jsonrpc": "2.0",
                        "id": body.get("id"),
                        "result": {
                            "tools": [
                                {
                                    "name": "run_pre_market_scan",
                                    "description": "Execute pre-market scan for ORB candidates with configurable criteria",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "min_price": {
                                                "type": "number",
                                                "description": "Minimum stock price filter",
                                                "default": 5.0
                                            },
                                            "max_price": {
                                                "type": "number",
                                                "description": "Maximum stock price filter",
                                                "default": 100.0
                                            },
                                            "min_volume": {
                                                "type": "integer",
                                                "description": "Minimum daily volume",
                                                "default": 100000
                                            },
                                            "max_results": {
                                                "type": "integer",
                                                "description": "Maximum number of candidates to return",
                                                "default": 50
                                            },
                                            "min_pre_market_change": {
                                                "type": "number",
                                                "description": "Minimum pre-market percentage change",
                                                "default": 2.0
                                            }
                                        }
                                    }
                                },
                                {
                                    "name": "get_current_candidates",
                                    "description": "Get current stock candidates from the most recent scan",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "limit": {
                                                "type": "integer",
                                                "description": "Maximum number of candidates to return",
                                                "default": 25
                                            }
                                        }
                                    }
                                },
                                {
                                    "name": "get_scanner_types",
                                    "description": "Get list of available IB scanner types for stock scanning",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {}
                                    }
                                },
                                {
                                    "name": "get_opening_ranges",
                                    "description": "Monitor and retrieve opening ranges from database for ORB strategy",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "date": {
                                                "type": "string",
                                                "description": "Date to query (YYYY-MM-DD format, defaults to today PST)"
                                            },
                                            "include_all": {
                                                "type": "boolean",
                                                "description": "Include all ranges in database for debugging",
                                                "default": False
                                            },
                                            "days_back": {
                                                "type": "integer",
                                                "description": "Number of days back to include",
                                                "default": 1
                                            }
                                        }
                                    }
                                },
                                {
                                    "name": "get_all_positions",
                                    "description": "Retrieve all positions regardless of status",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "date_from": {
                                                "type": "string",
                                                "description": "Start date filter (YYYY-MM-DD format)"
                                            },
                                            "date_to": {
                                                "type": "string",
                                                "description": "End date filter (YYYY-MM-DD format)"
                                            },
                                            "symbol": {
                                                "type": "string",
                                                "description": "Filter by specific symbol (e.g., AAPL)"
                                            },
                                            "days_back": {
                                                "type": "integer",
                                                "description": "Number of days back from today",
                                                "default": 1
                                            }
                                        }
                                    }
                                },
                                {
                                    "name": "get_current_implied_volatility",
                                    "description": "Get current at-the-money implied volatility",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "symbol": {
                                                "type": "string",
                                                "description": "Stock symbol (e.g., AAPL)"
                                            }
                                        }
                                    }
                                },
                                {
                                    "name": "get_volatility_term_structure",
                                    "description": "Get volatility term structure",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "symbol": {
                                                "type": "string",
                                                "description": "Stock symbol"
                                            },
                                            "target_days": {
                                                "type": "array",
                                                "items": {"type": "integer"},
                                                "description": "Target days to expiration",
                                                "default": [30, 60, 90]
                                            }
                                        }
                                    }
                                },
                                {
                                    "name": "analyze_volatility",
                                    "description": "Complete volatility analysis",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "symbol": {
                                                "type": "string",
                                                "description": "Stock symbol"
                                            }
                                        }
                                    }
                                },
                                {
                                    "name": "get_option_quote",
                                    "description": "Get real-time option quote with bid/ask and Greeks",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "symbol": {
                                                "type": "string",
                                                "description": "Stock symbol (e.g., AAPL)"
                                            },
                                            "expiry": {
                                                "type": "string",
                                                "description": "Expiration date in YYYYMMDD format (e.g., 20251107)"
                                            },
                                            "strike": {
                                                "type": "number",
                                                "description": "Strike price (e.g., 240)"
                                            },
                                            "right": {
                                                "type": "string",
                                                "description": "Option type: C for call, P for put"
                                            }
                                        }
                                    }
                                },
                                {
                                    "name": "get_stock_bars",
                                    "description": "Get historical OHLC bars for stock price analysis",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "symbol": {
                                                "type": "string",
                                                "description": "Stock symbol (e.g., AAPL)"
                                            },
                                            "duration": {
                                                "type": "string",
                                                "description": "IB duration string (e.g., '90 D', '252 D', '1 Y')",
                                                "default": "90 D"
                                            },
                                            "bar_size": {
                                                "type": "string",
                                                "description": "IB bar size (e.g., '1 day', '1 hour', '30 mins')",
                                                "default": "1 day"
                                            }
                                        },
                                        "required": ["symbol"]
                                    }
                                },
                                {
                                    "name": "place_options_spread",
                                    "description": "Place a multi-leg option spread order",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "symbol": {"type": "string"},
                                            "strategy_type": {"type": "string"},
                                            "legs": {"type": "array"},
                                            "limit_price": {"type": "number"},
                                            "expiration_date": {"type": "string"},
                                            "entry_iv": {"type": "number"},
                                            "time_in_force": {"type": "string", "default": "DAY"}
                                        },
                                        "required": ["symbol", "strategy_type", "legs", "limit_price", "expiration_date", "entry_iv"]
                                    }
                                },
                                {
                                    "name": "cancel_option_order",
                                    "description": "Cancel a pending option order",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "order_id": {"type": "integer"}
                                        },
                                        "required": ["order_id"]
                                    }
                                },
                                {
                                    "name": "list_working_orders",
                                    "description": "List all pending/working option orders",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "symbol": {"type": "string"}
                                        }
                                    }
                                },
                                {
                                    "name": "list_option_positions",
                                    "description": "List all open option positions",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "symbol": {"type": "string"}
                                        }
                                    }
                                },
                                {
                                    "name": "analyze_option_position",
                                    "description": "Analyze an option position",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "order_id": {"type": "integer"}
                                        },
                                        "required": ["order_id"]
                                    }
                                },
                                {
                                    "name": "close_option_position",
                                    "description": "Close an open option position by placing offsetting order",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "opening_order_id": {"type": "integer"},
                                            "exit_reason": {"type": "string", "default": "MANUAL_CLOSE"},
                                            "limit_price": {"type": "number"}
                                        },
                                        "required": ["opening_order_id"]
                                    }
                                },
                            ]
                        }
                    }
                elif body.get("method") == "tools/call":
                    params = body.get("params", {})
                    tool_name = params.get("name")
                    arguments = params.get("arguments", {})

                    # Call the appropriate method
                    result = None
                    if tool_name == "run_pre_market_scan":
                        result = await self._run_pre_market_scan(arguments)
                    elif tool_name == "get_current_candidates":
                        result = await self._get_current_candidates(arguments)
                    elif tool_name == "get_scanner_types":
                        result = await self._get_scanner_types(arguments)
                    elif tool_name == "get_stock_bars":
                        result = await self._get_stock_bars(arguments)
                    elif tool_name == "get_opening_ranges":
                        result = await self._get_opening_ranges(arguments)
                    elif tool_name == "get_all_positions":
                        result = await self._get_all_positions(arguments)
                    elif tool_name == "get_current_implied_volatility":
                        result = await self._get_current_implied_volatility(arguments)
                    elif tool_name == "get_volatility_term_structure":
                        result = await self._get_volatility_term_structure(arguments)
                    elif tool_name == "analyze_volatility":
                        result = await self._analyze_volatility(arguments)
                    elif tool_name == "get_option_quote":
                        result = await self._get_option_quote(arguments)
                    elif tool_name == "place_options_spread":
                        result = await self._place_options_spread(arguments)
                    elif tool_name == "cancel_option_order":
                        result = await self._cancel_option_order(arguments)
                    elif tool_name == "list_working_orders":
                        result = await self._list_working_orders(arguments)
                    elif tool_name == "list_option_positions":
                        result = await self._list_option_positions(arguments)
                    elif tool_name == "analyze_option_position":
                        result = await self._analyze_option_position(arguments)
                    elif tool_name == "close_option_position":
                        result = await self._close_option_position(arguments)
                    else:
                        return {
                            "jsonrpc": "2.0",
                            "id": body.get("id"),
                            "error": {
                                "code": -32601,
                                "message": f"Tool not found: {tool_name}"
                            }
                        }

                    # Convert TextContent objects to proper dictionaries for MCP protocol
                    content_list = []
                    for tc in result:
                        content_dict = tc.model_dump()
                        # Ensure _meta is {} instead of null for MCP protocol compatibility
                        if content_dict.get('meta') is not None:
                            content_dict['_meta'] = content_dict['meta']
                        else:
                            content_dict['_meta'] = {}
                        # Remove the non-aliased meta field
                        content_dict.pop('meta', None)
                        content_list.append(content_dict)

                    return {
                        "jsonrpc": "2.0",
                        "id": body.get("id"),
                        "result": {
                            "content": content_list
                        }
                    }
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": body.get("id"),
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {body.get('method')}"
                        }
                    }

            except Exception as e:
                logger.error(f"MCP endpoint error: {e}")
                return {
                    "jsonrpc": "2.0",
                    "id": body.get("id") if isinstance(body, dict) else None,
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                }

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info"
        )