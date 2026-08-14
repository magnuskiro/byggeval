#!/usr/bin/env python3
"""
Målrettet og skånsom innhenting av saker for spesifikke aktører:
- KB arkitekter
- BYGGMESTER DE LANGE OG SØRENSEN AS
Går 2 år tilbake i tid (2024-2026) med 10 sekunders pause mellom hvert kall.
"""

import sys
import os
import logging
from datetime import datetime

# Legg til src i PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from byggeval.client import TonsbergInnsynClient
from byggeval.evaluator import ByggesakEvaluator
from byggeval.database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("byggeval.targeted_fetcher")


def run_targeted_fetch():
    targets = [
        "KB arkitekter",
        "KB Arkitekter AS",
        "De Lange og Sørensen",
        "Byggmester De Lange og Sørensen",
        "Byggmester De Lange"
    ]
    
    # Inkluder alle saker fra 2022 til 2026 for disse foretakene
    min_year = 2022
    
    client = TonsbergInnsynClient(delay_between_requests=10.0)
    db = Database(db_path="data/byggeval.db")
    existing_ids = db.get_all_case_ids()
    
    logger.info(f"Starter målrettet innhenting for {len(targets)} aktører (Forsinkelse: 10s per forespørsel, Min år: {min_year})...")
    
    total_saved = 0
    total_skipped_unntatt = 0
    seen_ids = set(existing_ids)
    
    for term in targets:
        logger.info(f"\n==================================================")
        logger.info(f"Søker etter: '{term}'")
        logger.info(f"==================================================")
        
        for page in range(1, 15):
            logger.info(f"Henter side {page} for '{term}'...")
            try:
                overview = client.fetch_overview(
                    sakstype=None,  # Søk bredt på arkivsaker/byggesaker
                    search_term=term,
                    page=page,
                    page_size=20
                )
                search_items = overview.get("searchItems", {})
                items = search_items.get("items", [])
                if not items:
                    logger.info(f"Ingen flere resultater for '{term}'.")
                    break
                
                logger.info(f"Fant {len(items)} treff på side {page} for '{term}'.")
                
                for item in items:
                    parent_id = item.get("parentIdentifier")
                    item_id = item.get("identifier")
                    case_id = parent_id if (parent_id and parent_id.startswith("a-")) else item_id
                    
                    if not case_id:
                        continue
                        
                    # Sjekk årstall fra properties hvis mulig
                    item_props = item.get("properties", {})
                    dato_str = item_props.get("dato", "")
                    if dato_str:
                        try:
                            item_year = int(dato_str.strip().split(".")[-1])
                            if item_year < min_year:
                                logger.info(f"Hopper over sak {case_id} ({dato_str}) – eldre enn 2 år ({min_year}).")
                                continue
                        except Exception:
                            pass
                    
                    # Hvis vi allerede har saken i minnet i denne runden:
                    if case_id in seen_ids:
                        continue
                    seen_ids.add(case_id)
                    
                    logger.info(f"Henter detaljer for sak {case_id} ('{item.get('title', '')}')...")
                    details = client.fetch_case_details(case_id)
                    if not details:
                        continue
                        
                    # Sjekk sakens dato etter detaljhenting
                    case_date = details.get("dato", "")
                    if case_date:
                        try:
                            case_year = int(case_date.strip().split(".")[-1])
                            if case_year < min_year:
                                logger.info(f"Sak {details.get('saksnummer')} ({case_date}) er eldre enn {min_year}, hopper over.")
                                continue
                        except Exception:
                            pass
                    
                    # Filtrer bort meldinger unntatt søknadsplikt
                    if not ByggesakEvaluator.is_relevant_building_case(details):
                        logger.info(f"Hopper over sak {details.get('saksnummer')} – unntatt søknadsplikt.")
                        total_skipped_unntatt += 1
                        continue
                        
                    # Evaluer og lagre
                    try:
                        case_model = ByggesakEvaluator.create_byggesak_model(details)
                        db.save_case(case_model)
                        total_saved += 1
                        logger.info(f"✅ Lagret sak {case_model.saksnummer}: {case_model.tittel} (Firma: {case_model.primary_company})")
                    except Exception as e:
                        logger.error(f"Feil ved lagring av sak {case_id}: {e}")
                
                if search_items.get("isLastPage", False):
                    break
                    
            except Exception as e:
                logger.error(f"Feil ved søk etter '{term}' på side {page}: {e}")
                break
                
    db.record_sync(cases_synced=total_saved, error_count=0, status="success")
    logger.info(f"\n🎉 Målrettet innhenting fullført! Lagret {total_saved} nye/oppdaterte saker. ({total_skipped_unntatt} unntatte saker ble ignorert).")


if __name__ == "__main__":
    run_targeted_fetch()
