"""
API-klient for innhenting av postlister og innsyn fra Tønsberg kommune.
"""

import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TonsbergInnsynClient:
    """Klient mot Tønsberg kommunes offisielle innsyn- og postliste-API."""

    BASE_URL = "https://www.tonsberg.kommune.no/api/presentation/v2/nye-innsyn"
    
    # Filterkonstanter identifisert fra Tønsberg kommunes løsning
    SAKSTYPE_BYGGESAK = "at-e8411f20__3835__4913__bf04__3c27a9f93c86-BS!RnA5d9"
    SAKSTYPE_TILSYN_ULOVLIGHET = "at-e8411f20__3835__4913__bf04__3c27a9f93c86-TSBS!ovzivr"
    SAKSTYPE_PLANSAKER = "at-e8411f20__3835__4913__bf04__3c27a9f93c86-PS!eHYVsG"
    SAKSTYPE_DELINGSSAK = "at-e8411f20__3835__4913__bf04__3c27a9f93c86-DS!xcDquM"

    DEFAULT_HEADERS = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Byggeval/1.0",
        "PortalID": "1",
        "MenypunktID": "1594",
        "SprakID": "1",
        "WebObjektID": "4000",
        "X-ANTI-CSRF": "1"
    }

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)

    def fetch_overview(
        self,
        sakstype: Optional[str] = SAKSTYPE_BYGGESAK,
        search_term: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_order: str = "DatoNyest"
    ) -> Dict[str, Any]:
        """
        Henter overordnet søkeresultat/postliste fra Tønsberg kommune.
        """
        url = f"{self.BASE_URL}/overview"
        
        key_values = [
            {"key": "page", "value": str(page)},
            {"key": "pageSize", "value": str(page_size)},
            {"key": "SortDirection", "value": sort_order}
        ]

        if sakstype:
            key_values.append({"key": "Sakstype", "value": sakstype})
            
        if search_term:
            key_values.append({"key": "titleSearch", "value": search_term})

        payload = {
            "type": 0,  # 0 = Sak
            "keyValues": key_values
        }

        try:
            response = self.session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("content", {})
        except requests.RequestException as e:
            logger.error(f"Feil ved henting av oversikt fra Tønsberg API: {e}")
            raise

    def fetch_case_details(self, case_identifier: str) -> Optional[Dict[str, Any]]:
        """
        Henter fullstendige detaljer og journalposter/dokumenter for en sak.
        """
        url = f"{self.BASE_URL}/details/{case_identifier}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            content = data.get("content", {})
            return content.get("sak") if content else None
        except requests.RequestException as e:
            logger.error(f"Feil ved henting av saksdetaljer for {case_identifier}: {e}")
            return None

    def fetch_cases_batch(
        self,
        max_pages: int = 2,
        page_size: int = 20,
        sakstype: Optional[str] = SAKSTYPE_BYGGESAK,
        search_term: Optional[str] = None,
        fetch_details: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Henter en batch med saker, inkludert fullstendige detaljer om ønskelig.
        """
        cases: List[Dict[str, Any]] = []
        seen_case_ids = set()

        for page in range(1, max_pages + 1):
            try:
                overview = self.fetch_overview(
                    sakstype=sakstype,
                    search_term=search_term,
                    page=page,
                    page_size=page_size
                )
                search_items = overview.get("searchItems", {})
                items = search_items.get("items", [])
                
                if not items:
                    break

                for item in items:
                    # Finn saks-identifikator (enten parentIdentifier hvis dokument, eller identifier hvis sak)
                    parent_id = item.get("parentIdentifier")
                    item_id = item.get("identifier")
                    case_id = parent_id if (parent_id and parent_id.startswith("a-")) else item_id
                    
                    if not case_id or case_id in seen_case_ids:
                        continue
                    seen_case_ids.add(case_id)

                    if fetch_details:
                        details = self.fetch_case_details(case_id)
                        if details:
                            cases.append(details)
                        else:
                            # Fallback med data fra overview
                            cases.append({
                                "identifikator": case_id,
                                "saksnummer": item.get("properties", {}).get("saksnummer", "Ukjent"),
                                "tittel": item.get("title", ""),
                                "dato": item.get("properties", {}).get("dato", ""),
                                "sakstype": item.get("type", "Byggesak"),
                                "dokumenter": []
                            })
                    else:
                        cases.append(item)

                if search_items.get("isLastPage", False):
                    break

            except Exception as e:
                logger.error(f"Feil på side {page}: {e}")
                break

        return cases
