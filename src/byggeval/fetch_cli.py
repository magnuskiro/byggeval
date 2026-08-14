"""
Kommandolinjeverktøy for å hente ned byggesaker fra Tønsberg kommune.
"""

import argparse
import sys
import logging
from .client import TonsbergInnsynClient
from .evaluator import ByggesakEvaluator
from .database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("byggeval.fetcher")


def run_fetch(
    pages: int = 3,
    page_size: int = 20,
    search_term: str = None,
    sakstype: str = TonsbergInnsynClient.SAKSTYPE_BYGGESAK,
    db_path: str = "data/byggeval.db",
    delay: float = 10.0,
    force_refresh: bool = False,
    count: int = None
):
    """Kjører skånsom innhenting og lagring av byggesaker."""
    effective_pages = pages
    if count and pages == 3:
        # Beregn nok sider til å hente ønsket antall nye saker selv om mange allerede finnes
        effective_pages = max(15, (count // page_size) + 20)

    target_str = f", Mål: {count} nye saker" if count else ""
    logger.info(f"Starter skånsom innhenting fra Tønsberg kommune (Sider: {effective_pages}, Pr side: {page_size}, Forsinkelse: {delay}s{target_str}, Søk: '{search_term or 'Ingen'}')...")
    
    client = TonsbergInnsynClient(delay_between_requests=delay)
    db = Database(db_path=db_path)
    
    existing_ids = set() if force_refresh else db.get_all_case_ids()
    if existing_ids:
        logger.info(f"Fant {len(existing_ids)} saker allerede i lokal database. Hopper over uendrede detaljkall for å skåne serveren.")

    raw_cases = client.fetch_cases_batch(
        max_pages=effective_pages,
        page_size=page_size,
        sakstype=sakstype,
        search_term=search_term,
        fetch_details=True,
        skip_existing_ids=existing_ids,
        limit_cases=count
    )
    
    logger.info(f"Mottok {len(raw_cases)} nye unike saker fra Tønsberg API. Starter evaluering og lagring...")
    
    saved_cases = []
    skipped_count = 0
    for raw in raw_cases:
        if not ByggesakEvaluator.is_relevant_building_case(raw):
            skipped_count += 1
            logger.info(f"Hopper over sak {raw.get('saksnummer', 'Uten saksnr')} ('{raw.get('tittel', '')}') – gjelder tiltak unntatt søknadsplikt.")
            continue
        try:
            case = ByggesakEvaluator.create_byggesak_model(raw)
            db.save_case(case)
            saved_cases.append(case)
        except Exception as e:
            logger.error(f"Feil ved evaluering/lagring av sak {raw.get('identifikator')}: {e}")
            
    db.record_sync(cases_synced=len(saved_cases), error_count=len(raw_cases) - len(saved_cases) - skipped_count, status="success")
    
    logger.info(f"Fullført! Lagret {len(saved_cases)} nye relevante byggesaker i databasen ({skipped_count} saker unntatt søknadsplikt ble filtrert bort).")
    
    # Skriv ut sammendrag
    stats = db.get_statistics()
    print("\n" + "=" * 60)
    print(f"📊 BYGGEVAL STATUS - TØNSBERG KOMMUNE")
    print("=" * 60)
    print(f"Totalt antall saker i database: {stats['total_cases']}")
    print(f"Aktive saker:                    {stats['active_cases']}")
    print(f"Ferdigbehandlede:                {stats['completed_cases']}")
    print(f"Høy/Kritisk risiko:              {stats['high_risk_cases']}")
    print("-" * 60)
    print("Kategorifordeling:")
    for cat in stats['category_breakdown']:
        print(f"  • {cat['category']}: {cat['count']}")
    print("-" * 60)
    print("Risikofordeling:")
    for r in stats['risk_breakdown']:
        print(f"  • {r['risk_level']}: {r['count']}")
    print("=" * 60 + "\n")
    
    return saved_cases


def main():
    parser = argparse.ArgumentParser(description="Byggeval - Hent byggesaker fra Tønsberg kommune (skånsom og rate-limited)")
    parser.add_argument("--pages", type=int, default=3, help="Antall sider å hente (default: 3)")
    parser.add_argument("--count", type=int, default=None, help="Mål for antall nye saker som skal hentes inn (f.eks. 150)")
    parser.add_argument("--page-size", type=int, default=20, help="Antall saker per side (default: 20)")
    parser.add_argument("--delay", type=float, default=10.0, help="Forsinkelse i sekunder mellom forespørsler (default: 10.0s for å unngå abuse)")
    parser.add_argument("--search", type=str, default=None, help="Søketekst for filtrering")
    parser.add_argument("--force", action="store_true", help="Hent detaljer på nytt for saker som allerede finnes i databasen")
    parser.add_argument("--all-types", action="store_true", help="Hent alle sakstyper, ikke bare byggesak")
    parser.add_argument("--db", type=str, default="data/byggeval.db", help="Sti til databasefil")
    
    args = parser.parse_args()
    
    sakstype = None if args.all_types else TonsbergInnsynClient.SAKSTYPE_BYGGESAK
    run_fetch(
        pages=args.pages,
        page_size=args.page_size,
        search_term=args.search,
        sakstype=sakstype,
        db_path=args.db,
        delay=args.delay,
        force_refresh=args.force,
        count=args.count
    )


if __name__ == "__main__":
    main()
