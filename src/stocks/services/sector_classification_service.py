"""
Sector Classification Service - Get industry classification for stocks
Uses IB's fundamental data XML to retrieve primary SIC industry classification
"""

from src import logger
from typing import Dict
import xml.etree.ElementTree as ET


class SectorClassificationService:
    """Service for retrieving industry classification from Interactive Brokers"""

    def __init__(self, application_context):
        """
        Initialize sector classification service

        Args:
            application_context: Application context with client

        Raises:
            ValueError: If application_context is None
        """
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.client = application_context.client
        self.application_context = application_context

    def get_sector_info(self, symbol: str) -> Dict[str, str]:
        """
        Get industry classification for a stock

        Args:
            symbol: Stock symbol (required)

        Returns:
            Dict containing:
            - industry: Primary SIC industry classification
            - sic_code: SIC code

        Raises:
            ValueError: If symbol is None
            RuntimeError: If no classification data available
            TimeoutError: If request times out
        """
        if not symbol:
            raise ValueError("symbol is REQUIRED")

        logger.info(f"Fetching industry classification for {symbol}")

        try:
            # Get fundamental data XML which contains industry classifications
            xml_data = self.client.get_fundamental_data(
                symbol=symbol,
                report_type="ReportSnapshot",
                timeout=10
            )

            if not xml_data:
                raise TimeoutError(f"Timeout getting fundamental data for {symbol}")

            # Parse XML to extract primary SIC industry classification
            result = self._parse_industry_from_xml(xml_data, symbol)

            logger.info(f"Retrieved industry classification for {symbol}: {result.get('industry')}")
            return result

        except TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Error getting industry classification for {symbol}: {e}")
            raise RuntimeError(f"Error getting industry classification for {symbol}: {str(e)}")

    def _parse_industry_from_xml(self, xml_data: str, symbol: str) -> Dict[str, str]:
        """
        Parse primary SIC industry classification from IB fundamental data XML

        IB provides multiple industry classification systems in their XML:
        - TRBC (Thomson Reuters Business Classification)
        - NAICS (North American Industry Classification System)
        - SIC (Standard Industrial Classification)

        We use the primary SIC classification (order="0", reported="1")

        Args:
            xml_data: XML string from IB
            symbol: Stock symbol

        Returns:
            Dict with industry and sic_code
        """
        result = {
            "symbol": symbol,
            "industry": None,
            "sic_code": None,
            "data_available": True
        }

        try:
            root = ET.fromstring(xml_data)

            # Find primary SIC industry classification
            # Look for: <Industry type="SIC" order="0" reported="1">Industry Name</Industry>
            for industry_elem in root.findall('.//IndustryInfo/Industry'):
                industry_type = industry_elem.get('type')
                order = industry_elem.get('order')

                # Primary SIC classification has order="0"
                if industry_type == 'SIC' and order == '0':
                    result['industry'] = industry_elem.text
                    result['sic_code'] = industry_elem.get('code')
                    break

            # If no primary SIC found, try to get the first SIC classification
            if not result['industry']:
                for industry_elem in root.findall('.//IndustryInfo/Industry'):
                    if industry_elem.get('type') == 'SIC':
                        result['industry'] = industry_elem.text
                        result['sic_code'] = industry_elem.get('code')
                        break

            if not result['industry']:
                logger.warning(f"No SIC industry classification found for {symbol}")
                result['data_available'] = False

            return result

        except ET.ParseError as e:
            logger.error(f"XML parse error for industry classification on {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": "XML parse error",
                "data_available": False,
                "message": str(e)
            }
        except Exception as e:
            logger.error(f"Error parsing industry classification for {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": "Parse error",
                "data_available": False,
                "message": str(e)
            }
