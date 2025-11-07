"""
Fundamental Data Service - Real-time fundamental data for stock screening
Uses IB's reqFundamentalData API to retrieve company fundamentals
"""

from src import logger
import xml.etree.ElementTree as ET
from typing import Dict, Optional


class FundamentalDataService:
    """Service for retrieving and parsing fundamental stock data from Interactive Brokers"""

    def __init__(self, application_context):
        """
        Initialize fundamental data service

        Args:
            application_context: Application context with client

        Raises:
            ValueError: If application_context is None
        """
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.client = application_context.client
        self.application_context = application_context

    def get_fundamental_data(self, symbol: str) -> Dict[str, any]:
        """
        Get comprehensive fundamental data for a stock

        Args:
            symbol: Stock symbol (required)

        Returns:
            Dict containing fundamental metrics:
            - valuation: P/E ratios, Price-to-Book, Price-to-Sales
            - financial_health: Debt-to-Equity, Current Ratio, Quick Ratio
            - profitability: ROE, ROA, Profit Margin, Operating Margin
            - growth: Earnings Growth, Revenue Growth, EPS Growth
            - market_data: Market Cap, Shares Outstanding

        Raises:
            ValueError: If symbol is None
            RuntimeError: If no fundamental data available
            TimeoutError: If request times out
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        logger.info(f"Fetching fundamental data for {symbol}")

        try:
            # Get fundamental data from IB (returns XML string)
            xml_data = self.client.get_fundamental_data(
                symbol=symbol,
                report_type="ReportSnapshot",  # Company overview with key metrics
                timeout=10
            )

            if not xml_data:
                raise TimeoutError(f"Timeout getting fundamental data for {symbol}")

            # DEBUG: Log raw XML to understand structure (increased to 20000 chars to see Ratio section)
            logger.info(f"RAW FUNDAMENTAL XML for {symbol} (first 20000 chars):\n{xml_data[:20000]}")

            # Parse XML and extract metrics
            fundamentals = self._parse_fundamental_xml(xml_data, symbol)

            logger.info(f"Retrieved fundamental data for {symbol}")
            return fundamentals

        except TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Error getting fundamental data for {symbol}: {e}")
            raise RuntimeError(f"Error getting fundamental data for {symbol}: {str(e)}")

    def _parse_fundamental_xml(self, xml_data: str, symbol: str) -> Dict[str, any]:
        """
        Parse IB fundamental data XML response

        Args:
            xml_data: XML string from IB
            symbol: Stock symbol (for logging)

        Returns:
            Dict with categorized fundamental metrics
        """
        try:
            root = ET.fromstring(xml_data)

            # Initialize result structure
            result = {
                "symbol": symbol,
                "valuation": {},
                "financial_health": {},
                "profitability": {},
                "growth": {},
                "market_data": {},
                "raw_data_available": True
            }

            # Navigate XML structure - IB returns nested XML
            # Format: <ReportSnapshot><CoIDs><CoID>...</CoID></CoIDs><FinancialStatements>...

            # Try to find financial ratios section
            for ratio_elem in root.iter('Ratio'):
                field_name = ratio_elem.get('FieldName', '')
                value_text = ratio_elem.text

                # Parse numeric values safely
                try:
                    value = float(value_text) if value_text and value_text.strip() else None
                except (ValueError, AttributeError):
                    value = None

                # Categorize metrics
                # Valuation metrics - Enhanced pattern matching for P/E
                if any(pattern in field_name.upper() for pattern in ['TTMPE', 'PE_RATIO', 'PEEXCLXOR', 'PEINCLXOR', 'PERATIO', 'PRICEEARNINGS', 'P/E', 'TRAILING_PE', 'TRAILINGPE']):
                    if 'pe_ratio' not in result['valuation'] or result['valuation']['pe_ratio'] is None:
                        result['valuation']['pe_ratio'] = value
                elif 'PRICE2BK' in field_name or 'PriceToBook' in field_name:
                    result['valuation']['price_to_book'] = value
                elif 'PRICE2SALES' in field_name or 'PriceToSales' in field_name:
                    result['valuation']['price_to_sales'] = value
                elif 'PRICE2TANG' in field_name:
                    result['valuation']['price_to_tangible_book'] = value

                # Financial health metrics
                elif 'QTOTD2EQ' in field_name or 'DebtToEquity' in field_name:
                    result['financial_health']['debt_to_equity'] = value
                elif 'QCURRENT' in field_name or 'CurrentRatio' in field_name:
                    result['financial_health']['current_ratio'] = value
                elif 'QQUICK' in field_name or 'QuickRatio' in field_name:
                    result['financial_health']['quick_ratio'] = value
                elif 'QLTD2EQ' in field_name:
                    result['financial_health']['long_term_debt_to_equity'] = value

                # Profitability metrics
                elif 'TTMROEPCT' in field_name or 'ROE' in field_name:
                    result['profitability']['roe'] = value
                elif 'TTMROAPCT' in field_name or 'ROA' in field_name:
                    result['profitability']['roa'] = value
                elif 'TTMPR2REV' in field_name or 'ProfitMargin' in field_name:
                    result['profitability']['profit_margin'] = value
                elif 'TTMGROSMGN' in field_name or 'GrossMargin' in field_name:
                    result['profitability']['gross_margin'] = value
                elif 'TTMOPMGN' in field_name or 'OperatingMargin' in field_name:
                    result['profitability']['operating_margin'] = value

                # Growth metrics (EPS, Revenue) - Enhanced pattern matching for EPS
                elif any(pattern in field_name.upper() for pattern in ['TTMEPSXCLX', 'TTMEPSINCLXOR', 'QEPSDIL', 'AEPSDIL', 'EARNINGSPERSHARE', 'TTM_EPS', 'DILUTED_EPS', 'BASIC_EPS', 'EPS_TTM', 'TRAILING_EPS']):
                    if 'eps' not in result['growth'] or result['growth']['eps'] is None:
                        result['growth']['eps'] = value
                elif field_name.upper() == 'EPS' or field_name == 'eps':
                    if 'eps' not in result['growth'] or result['growth']['eps'] is None:
                        result['growth']['eps'] = value
                elif 'TTMREVPS' in field_name or 'RevenuePerShare' in field_name:
                    result['growth']['revenue_per_share'] = value
                elif 'REVCHNGYR' in field_name or 'RevenueGrowth' in field_name:
                    result['growth']['revenue_growth_yoy'] = value
                elif 'EPSCHNGYR' in field_name or 'EPSGrowth' in field_name:
                    result['growth']['eps_growth_yoy'] = value

            # Extract market data (market cap, shares outstanding)
            for issue_elem in root.iter('IssueID'):
                for coid_elem in issue_elem.iter('CoID'):
                    for shares_elem in coid_elem.iter('SharesOut'):
                        try:
                            result['market_data']['shares_outstanding'] = float(shares_elem.text)
                        except (ValueError, AttributeError, TypeError):
                            pass

                    for mktcap_elem in coid_elem.iter('MktCap'):
                        try:
                            result['market_data']['market_cap'] = float(mktcap_elem.text)
                        except (ValueError, AttributeError, TypeError):
                            pass

            # Alternative parsing: check for different XML structure
            # IB can return data in multiple formats depending on report type
            if not result['valuation'] and not result['financial_health']:
                logger.warning(f"No ratio data found for {symbol} - trying alternative XML structure")
                # Try to find any numeric elements
                for elem in root.iter():
                    if elem.text and elem.tag:
                        try:
                            value = float(elem.text)
                            # Store in raw data for inspection
                            if 'raw_fields' not in result:
                                result['raw_fields'] = {}
                            result['raw_fields'][elem.tag] = value
                        except (ValueError, TypeError):
                            pass

            return result

        except ET.ParseError as e:
            logger.error(f"XML parse error for {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": "XML parse error",
                "raw_data_available": False,
                "message": str(e)
            }
        except Exception as e:
            logger.error(f"Error parsing fundamental data for {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": "Parse error",
                "raw_data_available": False,
                "message": str(e)
            }
