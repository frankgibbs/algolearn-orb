"""
Dividend Data Service - Get dividend metrics and schedule for stocks
Uses IB's fundamental data and contract details to retrieve dividend information
"""

from src import logger
import xml.etree.ElementTree as ET
from typing import Dict, Optional
from datetime import datetime


class DividendDataService:
    """Service for retrieving dividend data from Interactive Brokers"""

    def __init__(self, application_context):
        """
        Initialize dividend data service

        Args:
            application_context: Application context with client

        Raises:
            ValueError: If application_context is None
        """
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.client = application_context.client
        self.application_context = application_context

    def get_dividend_data(self, symbol: str) -> Dict[str, any]:
        """
        Get dividend metrics and schedule for a stock

        Args:
            symbol: Stock symbol (required)

        Returns:
            Dict containing:
            - current_yield: Current dividend yield (%)
            - annual_amount: Annual dividend amount ($)
            - frequency: Dividend frequency (monthly/quarterly/annual)
            - ex_dividend_date: Next or most recent ex-dividend date
            - payment_date: Next or most recent payment date
            - dividend_growth_rate: Year-over-year dividend growth (if available)

        Raises:
            ValueError: If symbol is None
            RuntimeError: If no dividend data available
            TimeoutError: If request times out
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        logger.info(f"Fetching dividend data for {symbol}")

        try:
            # Get fundamental data from IB (contains dividend info)
            xml_data = self.client.get_fundamental_data(
                symbol=symbol,
                report_type="ReportSnapshot",  # Contains dividend data
                timeout=10
            )

            if not xml_data:
                raise TimeoutError(f"Timeout getting dividend data for {symbol}")

            # DEBUG: Log raw XML to understand structure (increased to 20000 chars to see Ratio section)
            logger.info(f"RAW DIVIDEND XML for {symbol} (first 20000 chars):\n{xml_data[:20000]}")

            # Parse XML for dividend information
            dividend_data = self._parse_dividend_xml(xml_data, symbol)

            logger.info(f"Retrieved dividend data for {symbol}")
            return dividend_data

        except TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Error getting dividend data for {symbol}: {e}")
            raise RuntimeError(f"Error getting dividend data for {symbol}: {str(e)}")

    def _parse_dividend_xml(self, xml_data: str, symbol: str) -> Dict[str, any]:
        """
        Parse IB fundamental data XML for dividend information

        Args:
            xml_data: XML string from IB
            symbol: Stock symbol

        Returns:
            Dict with dividend metrics
        """
        try:
            root = ET.fromstring(xml_data)

            result = {
                "symbol": symbol,
                "current_yield": None,
                "annual_amount": None,
                "quarterly_amount": None,
                "frequency": None,
                "ex_dividend_date": None,
                "payment_date": None,
                "dividend_growth_rate": None,
                "pays_dividend": False,
                "data_available": True
            }

            # Look for dividend-related ratio fields
            for ratio_elem in root.iter('Ratio'):
                field_name = ratio_elem.get('FieldName', '')
                value_text = ratio_elem.text

                try:
                    value = float(value_text) if value_text and value_text.strip() else None
                except (ValueError, AttributeError):
                    value = None

                # Parse dividend fields - Enhanced pattern matching
                # Dividend Yield
                if any(pattern in field_name.upper() for pattern in ['DIVYIELD', 'YIELD', 'DIV_YIELD', 'YIELD_PCT', 'ANNUAL_YIELD', 'TTMDIVYIELD', 'DIVIDENDYIELD']):
                    if result['current_yield'] is None:
                        result['current_yield'] = value
                        if value and value > 0:
                            result['pays_dividend'] = True

                # Annual Dividend Amount
                elif any(pattern in field_name.upper() for pattern in ['TTMDIVPERSHR', 'TTMDIV', 'DIVANNUAL', 'ADIVSHR', 'ANNUAL_DIV', 'DIV_PER_SHARE']):
                    if result['annual_amount'] is None:
                        result['annual_amount'] = value
                        if value and value > 0:
                            result['pays_dividend'] = True

                # Quarterly Dividend Amount
                elif any(pattern in field_name.upper() for pattern in ['QTTMDIVPERSHR', 'DIVQUARTER', 'QDIVSHR', 'QUARTERLY_DIV', 'QUARTERLYDIVIDEND', 'LAST_DIV']):
                    if result['quarterly_amount'] is None:
                        result['quarterly_amount'] = value

                elif 'DIVGRPCT' in field_name or 'DIVGROWTH' in field_name:
                    result['dividend_growth_rate'] = value

            # Try to find dividend dates in XML - Enhanced pattern matching
            for elem in root.iter():
                tag_lower = elem.tag.lower()

                # Ex-Dividend Date
                if any(pattern in tag_lower for pattern in ['exdate', 'exdividend', 'ex_date', 'exdiv_date', 'dividendexdate', 'exdivdate']):
                    if elem.text and elem.text.strip():
                        result['ex_dividend_date'] = elem.text.strip()
                    # Also check attributes
                    if not result['ex_dividend_date']:
                        for attr_name in ['value', 'Value', 'date', 'Date']:
                            if elem.get(attr_name):
                                result['ex_dividend_date'] = elem.get(attr_name)
                                break

                # Payment Date
                elif any(pattern in tag_lower for pattern in ['paydate', 'paymentdate', 'pay_date', 'payment_date', 'dividendpaydate', 'divpaydate']):
                    if elem.text and elem.text.strip():
                        result['payment_date'] = elem.text.strip()
                    # Also check attributes
                    if not result['payment_date']:
                        for attr_name in ['value', 'Value', 'date', 'Date']:
                            if elem.get(attr_name):
                                result['payment_date'] = elem.get(attr_name)
                                break

                # Dividend Frequency
                elif any(pattern in tag_lower for pattern in ['divfrequency', 'frequency', 'div_frequency', 'dividendfrequency']):
                    if elem.text and elem.text.strip():
                        result['frequency'] = elem.text.strip()
                    # Also check attributes
                    if not result['frequency']:
                        for attr_name in ['value', 'Value']:
                            if elem.get(attr_name):
                                result['frequency'] = elem.get(attr_name)
                                break

            # Infer frequency if not explicitly stated
            if not result['frequency'] and result['quarterly_amount'] and result['annual_amount']:
                if abs(result['quarterly_amount'] * 4 - result['annual_amount']) < 0.01:
                    result['frequency'] = 'Quarterly'
                elif abs(result['quarterly_amount'] * 12 - result['annual_amount']) < 0.01:
                    result['frequency'] = 'Monthly'

            # Calculate annual from quarterly if missing
            if not result['annual_amount'] and result['quarterly_amount']:
                if result['frequency'] == 'Quarterly':
                    result['annual_amount'] = result['quarterly_amount'] * 4
                elif result['frequency'] == 'Monthly':
                    result['annual_amount'] = result['quarterly_amount'] * 12

            return result

        except ET.ParseError as e:
            logger.error(f"XML parse error for dividend data on {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": "XML parse error",
                "data_available": False,
                "message": str(e)
            }
        except Exception as e:
            logger.error(f"Error parsing dividend data for {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": "Parse error",
                "data_available": False,
                "message": str(e)
            }
