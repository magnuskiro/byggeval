"""
API-klient for innhenting av postlister og innsyn fra Tønsberg kommune.
"""

import time
import logging
import requests
from typing import Dict, Any, List, Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)


class TonsbergInnsynClient:
    """
    Klient mot Tønsberg kommunes offisielle innsyn- og postliste-API.
    Inkluderer innebygd rate-limiting og skånsom pacing for å beskytte kommunens servere.
    """

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

    DEFAULT_DELAY = 10.0  # 10 sekunders høflig ventetid per sak for å unngå abuse

    def __init__(self, timeout: int = 20, delay_between_requests: float = 10.0, max_retries: int = 3):
        self.timeout = timeout
        self.delay_between_requests = delay_between_requests
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self._last_request_time = 0.0

    def _wait_for_rate_limit(self):
        """Sørger for en høflig forsinkelse mellom hvert kall til kommunen."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.delay_between_requests:
            sleep_needed = self.delay_between_requests - elapsed
            time.sleep(sleep_needed)
        self._last_request_time = time.time()

    def fetch_overview(
        self,
        sakstype: Optional[str] = SAKSTYPE_BYGGESAK,
        search_term: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_order: str = "DatoNyest"
    ) -> Dict[str, Any]:
        """
        Henter overordnet søkeresultat/postliste fra Tønsberg kommune med rate limiting.
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

        for attempt in range(1, self.max_retries + 1):
            self._wait_for_rate_limit()
            try:
                response = self.session.post(url, json=payload, timeout=self.timeout)
                if response.status_code == 429:
                    wait_time = attempt * 2.0
                    logger.warning(f"Rate limit (429) fra Tønsberg API. Venter {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                response.raise_for_status()
                data = response.json()
                return data.get("content", {})
            except requests.RequestException as e:
                logger.warning(f"Feil ved henting av oversikt (forsøk {attempt}/{self.max_retries}): {e}")
                if attempt == self.max_retries:
                    raise
                time.sleep(attempt * 1.5)

        return {}

    def fetch_case_details(self, case_identifier: str) -> Optional[Dict[str, Any]]:
        """
        Henter fullstendige detaljer og journalposter/dokumenter for en sak med rate limiting.
        """
        url = f"{self.BASE_URL}/details/{case_identifier}"
        for attempt in range(1, self.max_retries + 1):
            self._wait_for_rate_limit()
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 429:
                    wait_time = attempt * 2.0
                    logger.warning(f"Rate limit (429) fra Tønsberg API for {case_identifier}. Venter {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                response.raise_for_status()
                data = response.json()
                content = data.get("content", {})
                return content.get("sak") if content else None
            except requests.RequestException as e:
                logger.warning(f"Feil ved henting av saksdetaljer for {case_identifier} (forsøk {attempt}/{self.max_retries}): {e}")
                if attempt == self.max_retries:
                    return None
                time.sleep(attempt * 1.0)
        return None

    def fetch_cases_batch(
        self,
        max_pages: int = 2,
        page_size: int = 20,
        sakstype: Optional[str] = SAKSTYPE_BYGGESAK,
        search_term: Optional[str] = None,
        fetch_details: bool = True,
        skip_existing_ids: Optional[Set[str]] = None,
        progress_callback: Optional[callable] = None,
        limit_cases: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Henter en skånsom batch med saker, med støtte for å hoppe over allerede kjente saker.
        """
        cases: List[Dict[str, Any]] = []
        seen_case_ids = set()
        existing_ids = skip_existing_ids or set()

        for page in range(1, max_pages + 1):
            if limit_cases and len(cases) >= limit_cases:
                logger.info(f"Nådde ønsket antall nye saker ({len(cases)} av {limit_cases}). Avslutter innhenting.")
                break

            try:
                if progress_callback:
                    progress_callback(f"Henter side {page} av {max_pages} (Nye saker hittil: {len(cases)})...")

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

                for i, item in enumerate(items):
                    if limit_cases and len(cases) >= limit_cases:
                        break

                    # Finn saks-identifikator (enten parentIdentifier hvis dokument, eller identifier hvis sak)
                    parent_id = item.get("parentIdentifier")
                    item_id = item.get("identifier")
                    case_id = parent_id if (parent_id and parent_id.startswith("a-")) else item_id
                    
                    if not case_id or case_id in seen_case_ids:
                        continue
                    seen_case_ids.add(case_id)

                    # Hvis saken allerede finnes i lokal database, trenger vi ikke hente detaljer på nytt
                    if case_id in existing_ids:
                        continue

                    if fetch_details:
                        if progress_callback:
                            progress_callback(f"Henter detaljer for sak {len(cases) + 1}...")

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
