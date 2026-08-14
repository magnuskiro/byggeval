#!/usr/bin/env python3
"""
Systematisk og skånsom bakgrunnsinnhenting av alle byggesaker tilbake til 1. januar 2025.
- 10 sekunders høflig ventetid per forespørsel
- Hopper over saker som allerede er i databasen
- Filtrerer bort meldinger unntatt søknadsplikt
- Stopper automatisk når vi når saker eldre enn 01.01.2025
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
logger = logging.getLogger("byggeval.archive_crawler")


def crawl_to_date(cutoff_str: str = "01.01.2025", delay: float = 10.0):
    cutoff_dt = datetime.strptime(cutoff_str, "%d.%m.%Y").date()
    logger.info(f"Starter systematisk arkivinnhenting tilbake til {cutoff_str} (Forsinkelse: {delay}s per kall)...")
    
    client = TonsbergInnsynClient(delay_between_requests=delay)
    db = Database(db_path="data/byggeval.db")
    existing_ids = db.get_all_case_ids()
    seen_ids = set(existing_ids)
    
    logger.info(f"Fant {len(existing_ids)} saker allerede i lokal database. Disse hoppes over.")
    
    total_saved = 0
    total_skipped_unntatt = 0
    consecutive_old_pages = 0
    
    # Blar gjennom opptil 350 sider
    for page in range(1, 350):
        logger.info(f"Henter side {page} fra byggesaksarkivet...")
        try:
            overview = client.fetch_overview(
                sakstype=TonsbergInnsynClient.SAKSTYPE_BYGGESAK,
                page=page,
                page_size=20
            )
            search_items = overview.get("searchItems", {})
            items = search_items.get("items", [])
            
            if not items:
                logger.info(f"Ingen flere saker i arkivet på side {page}.")
                break
                
            page_has_valid_date = False
            
            for item in items:
                parent_id = item.get("parentIdentifier")
                item_id = item.get("identifier")
                case_id = parent_id if (parent_id and parent_id.startswith("a-")) else item_id
                
                if not case_id:
                    continue
                    
                item_props = item.get("properties", {})
                dato_str = item_props.get("dato", "")
                if dato_str:
                    try:
                        item_dt = datetime.strptime(dato_str.strip(), "%d.%m.%Y").date()
                        if item_dt < cutoff_dt:
                            logger.info(f"Post {dato_str} er eldre enn grensedato {cutoff_str}.")
                            continue
                        else:
                            page_has_valid_date = True
                    except Exception:
                        pass
                
                if case_id in seen_ids:
                    continue
                seen_ids.add(case_id)
                
                # Hent fullverdige saks- og dokumentdetaljer
                logger.info(f"Henter detaljer for sak {case_id} ('{item.get('title', '')}')...")
                details = client.fetch_case_details(case_id)
                if not details:
                    continue
                    
                # Sjekk endelig dato på saken
                case_date_str = details.get("dato", "")
                if case_date_str:
                    try:
                        case_dt = datetime.strptime(case_date_str.strip(), "%d.%m.%Y").date()
                        if case_dt < cutoff_dt:
                            logger.info(f"Sak {details.get('saksnummer')} ({case_date_str}) er eldre enn {cutoff_str}.")
                            continue
                    except Exception:
                        pass
                
                # Filtrer bort meldinger unntatt søknadsplikt
                if not ByggesakEvaluator.is_relevant_building_case(details):
                    logger.info(f"Hopper over sak {details.get('saksnummer')} – unntatt søknadsplikt.")
                    total_skipped_unntatt += 1
                    continue
                    
                # Evaluer og lagre i database
                try:
                    case_model = ByggesakEvaluator.create_byggesak_model(details)
                    db.save_case(case_model)
                    total_saved += 1
                    logger.info(f"✅ Lagret sak {case_model.saksnummer} ({case_model.dato}): {case_model.tittel} [Firma: {case_model.primary_company or 'Ikke oppgitt'}] (Totalt nye: {total_saved})")
                except Exception as e:
                    logger.error(f"Feil ved evaluering/lagring av sak {case_id}: {e}")
            
            # Hvis en hel side kun inneholder poster eldre enn cutoff_dt:
            if not page_has_valid_date and len(items) > 0:
                consecutive_old_pages += 1
                if consecutive_old_pages >= 3:
                    logger.info(f"Nådde slutten av tidsrommet ({cutoff_str}). Avslutter innhenting.")
                    break
            else:
                consecutive_old_pages = 0
                
            if search_items.get("isLastPage", False):
                logger.info("Nådde siste side i innsynsløsningen.")
                break
                
        except Exception as e:
            logger.error(f"Feil ved henting av side {page}: {e}")
            break
            
    db.record_sync(cases_synced=total_saved, error_count=0, status="success")
    stats = db.get_statistics()
    logger.info(f"\n🎉 Arkivinnhenting til {cutoff_str} fullført!")
    logger.info(f"Lagret {total_saved} nye saker. Totalt i databasen: {stats['total_cases']} saker.")


if __name__ == "__main__":
    crawl_to_date("01.01.2025", delay=10.0)
