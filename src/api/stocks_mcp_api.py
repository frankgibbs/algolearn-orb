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
                elif name == "get_opening_ranges":
                    return await self._get_opening_ranges(arguments or {})
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
                    "get_opening_ranges"
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
                    elif tool_name == "get_opening_ranges":
                        result = await self._get_opening_ranges(arguments)
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