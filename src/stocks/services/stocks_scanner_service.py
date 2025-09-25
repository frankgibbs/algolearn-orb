"""
Stock Scanner Service - Business logic for Interactive Brokers stock scanner operations
"""

from src import logger
import xml.etree.ElementTree as ET


class StocksScannerService:
    """Service for handling stock scanner operations through Interactive Brokers"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.application_context = application_context
        self.client = application_context.client

    def get_available_scanner_types(self):
        """
        Get list of available scanner types from Interactive Brokers

        Returns:
            list: List of available scanner codes
        """
        try:
            xml_data = self.client.get_scanner_parameters()

            if not xml_data:
                logger.error("No scanner parameters received from IB")
                return []

            return self._parse_scanner_xml(xml_data)

        except Exception as e:
            logger.error(f"Error getting scanner types: {e}")
            return []

    def _parse_scanner_xml(self, xml_data):
        """
        Parse XML scanner parameters response from IB

        Args:
            xml_data (str): Raw XML response from IB

        Returns:
            list: List of scanner codes
        """
        try:
            root = ET.fromstring(xml_data)
            scanner_codes = []

            # Look for ScanType elements under ScanTypeList
            for scan_type in root.findall(".//ScanType"):
                scan_code_elem = scan_type.find("scanCode")
                if scan_code_elem is not None and scan_code_elem.text:
                    scanner_codes.append(scan_code_elem.text)

            logger.info(f"Found {len(scanner_codes)} available scanner types")
            return sorted(scanner_codes)

        except ET.ParseError as e:
            logger.error(f"XML parsing error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing scanner XML: {e}")
            return []

    def scan_pre_market_movers(self, criteria):
        """
        Scan for pre-market moving stocks using multiple IB scanners

        Args:
            criteria (dict): Scanner criteria containing:
                - min_price: Minimum stock price
                - max_price: Maximum stock price
                - min_volume: Minimum volume
                - max_results: Maximum results to return

        Returns:
            list: List of stock scanner results

        Raises:
            ValueError: If criteria is None
            RuntimeError: If no data received from any scanner
        """
        if criteria is None:
            raise ValueError("criteria is REQUIRED")

        logger.info(f"Scanning for pre-market movers with criteria: {criteria}")

        all_results = []
        scanner_codes = ["TOP_PERC_GAIN", "MOST_ACTIVE", "HOT_BY_VOLUME"]

        for scan_code in scanner_codes:
            try:
                logger.info(f"Running {scan_code} scanner")

                # Build scanner parameters
                scanner_params = {
                    "scanCode": scan_code,
                    "numberOfRows": 50,  # Get 50 from each scanner
                    "instrument": "STK",
                    "locationCode": "STK.US.MAJOR"
                }

                # Add price filters
                min_price = criteria.get("min_price")
                if min_price is not None and min_price > 0:
                    scanner_params["abovePrice"] = min_price

                max_price = criteria.get("max_price")
                if max_price is not None and max_price > 0:
                    scanner_params["belowPrice"] = max_price

                # Add volume filter
                min_volume = criteria.get("min_volume")
                if min_volume is not None and min_volume > 0:
                    scanner_params["aboveVolume"] = min_volume

                # Execute scanner
                scanner_results = self.client.scan_market(scanner_params, timeout=30)

                if scanner_results:
                    # Tag results with scanner type
                    for result in scanner_results:
                        result['scanner_type'] = scan_code
                    all_results.extend(scanner_results)
                    logger.info(f"{scan_code} scanner returned {len(scanner_results)} candidates")
                else:
                    logger.warning(f"{scan_code} scanner returned no results")

            except Exception as e:
                logger.error(f"Error running {scan_code} scanner: {e}")
                continue

        # Remove duplicates based on symbol
        unique_results = self._remove_duplicate_symbols(all_results)

        # Apply post-scan filtering
        filtered_results = self._apply_post_scan_filters(unique_results, criteria)

        if not filtered_results:
            raise RuntimeError("No candidates found after filtering from pre-market scanners")

        logger.info(f"Final results: {len(filtered_results)} unique candidates from {len(scanner_codes)} scanners")
        return filtered_results

    def scan_most_active_stocks(self, criteria):
        """
        Scan for most active stocks using IB scanner

        Args:
            criteria (dict): Scanner criteria

        Returns:
            list: List of most active stocks

        Raises:
            ValueError: If criteria is None
        """
        if criteria is None:
            raise ValueError("criteria is REQUIRED")

        logger.info(f"Scanning for most active stocks with criteria: {criteria}")

        # Get required parameters
        max_results = criteria.get("max_results")
        if max_results is None:
            raise ValueError("max_results is REQUIRED in criteria")

        scanner_params = {
            "scanCode": "MOST_ACTIVE",
            "numberOfRows": max_results,
            "instrument": "STK",
            "locationCode": "STK.US.MAJOR"
        }

        # Add filters similar to pre-market scan
        min_price = criteria.get("min_price")
        if min_price is not None and min_price > 0:
            scanner_params["abovePrice"] = min_price

        max_price = criteria.get("max_price")
        if max_price is not None and max_price > 0:
            scanner_params["belowPrice"] = max_price

        min_volume = criteria.get("min_volume")
        if min_volume is not None and min_volume > 0:
            scanner_params["aboveVolume"] = min_volume

        scanner_results = self.client.scan_market(scanner_params, timeout=30)

        if not scanner_results:
            logger.warning("No data received from most active scanner")
            return []

        logger.info(f"Scanner returned {len(scanner_results)} most active stocks")
        return scanner_results

    def format_scanner_results(self, scanner_results, scan_criteria, scan_time=None):
        """
        Format scanner results for stock candidate storage

        Args:
            scanner_results (list): Raw scanner results from IB
            scan_criteria (dict): Original scan criteria
            scan_time (datetime): Time of scan (optional, defaults to now)

        Returns:
            list: Formatted candidate data for database storage

        Raises:
            ValueError: If scanner_results is None
        """
        if scanner_results is None:
            raise ValueError("scanner_results is REQUIRED")

        if scan_time is None:
            from datetime import datetime
            scan_time = datetime.now()

        formatted_candidates = []

        for i, result in enumerate(scanner_results):
            try:
                # Extract basic info
                symbol = result.get('symbol', f'UNKNOWN_{i}')
                rank = i + 1  # Re-rank based on filtered order

                # Parse distance field for percentage change
                distance = result.get('distance', '0.0')
                try:
                    pre_market_change = float(distance.replace('%', ''))
                except (ValueError, AttributeError):
                    pre_market_change = 0.0

                # Build criteria description including scanner type
                scanner_type = result.get('scanner_type', 'UNKNOWN')
                criteria_parts = [f"Scanner: {scanner_type}"]

                if scan_criteria.get("min_price"):
                    criteria_parts.append(f"Price >= ${scan_criteria['min_price']}")
                if scan_criteria.get("max_price"):
                    criteria_parts.append(f"Price <= ${scan_criteria['max_price']}")
                if scan_criteria.get("min_volume"):
                    criteria_parts.append(f"Volume >= {scan_criteria['min_volume']:,}")

                criteria_parts.append(f"Change: {pre_market_change:+.1f}%")

                # Create candidate data
                candidate_data = {
                    'symbol': symbol,
                    'scan_time': scan_time.time(),
                    'rank': rank,
                    'pre_market_change': pre_market_change,
                    'volume': 0,  # Would need additional API call to get current volume
                    'relative_volume': 1.0,  # Would need historical data for calculation
                    'criteria_met': "; ".join(criteria_parts),
                    'raw_scanner_data': {
                        'original_rank': result.get('rank', i + 1),
                        'distance': result.get('distance', ''),
                        'benchmark': result.get('benchmark', ''),
                        'projection': result.get('projection', ''),
                        'scanner_type': scanner_type
                    }
                }

                formatted_candidates.append(candidate_data)

            except Exception as e:
                logger.error(f"Error formatting scanner result {i}: {e}")
                continue

        # Limit to top 25 candidates for ORB strategy
        if len(formatted_candidates) > 25:
            logger.info(f"Limiting candidates to top 25 from {len(formatted_candidates)} total")
            formatted_candidates = formatted_candidates[:25]

        logger.info(f"Formatted {len(formatted_candidates)} candidates from scanner results")
        return formatted_candidates

    def _build_criteria_description(self, criteria):
        """
        Build a description of the criteria that were met

        Args:
            criteria (dict): Scanner criteria

        Returns:
            str: Description of criteria
        """
        parts = []

        if criteria.get("min_price"):
            parts.append(f"Price >= ${criteria['min_price']}")

        if criteria.get("max_price"):
            parts.append(f"Price <= ${criteria['max_price']}")

        if criteria.get("min_volume"):
            parts.append(f"Volume >= {criteria['min_volume']:,}")

        parts.append("Pre-market mover")

        return "; ".join(parts)

    def _remove_duplicate_symbols(self, results):
        """
        Remove duplicate symbols, keeping the best ranked result

        Args:
            results (list): List of scanner results

        Returns:
            list: Deduplicated results
        """
        if not results:
            return []

        # Group by symbol
        symbol_groups = {}
        for result in results:
            symbol = result.get('symbol')
            if symbol:
                if symbol not in symbol_groups:
                    symbol_groups[symbol] = []
                symbol_groups[symbol].append(result)

        # Keep best ranked result for each symbol
        unique_results = []
        for symbol, group in symbol_groups.items():
            # Sort by rank (lower is better)
            best_result = min(group, key=lambda x: x.get('rank', 999))
            unique_results.append(best_result)

        logger.info(f"Removed duplicates: {len(results)} -> {len(unique_results)} unique symbols")
        return unique_results

    def _apply_post_scan_filters(self, results, criteria):
        """
        Apply additional filtering after scanner results

        Note: Distance-based filtering removed because IB scanner distance field
        is empty during market hours. Scanner results (TOP_PERC_GAIN, MOST_ACTIVE,
        HOT_BY_VOLUME) are already pre-filtered by IB.

        Args:
            results (list): Scanner results
            criteria (dict): Filter criteria

        Returns:
            list: Filtered results
        """
        if not results:
            logger.error("No results to filter")
            return []

        # Get required max_results parameter
        max_results = criteria.get("max_results")
        if max_results is None:
            raise ValueError("max_results is REQUIRED in criteria")

        # Just limit to max_results - trust the scanner results from IB
        filtered = results[:max_results] if len(results) > max_results else results

        logger.info(f"Post-scan filtering: {len(results)} -> {len(filtered)} candidates (removed distance filtering - field empty during market hours)")
        return filtered