"""
FastAPI REST API for Byggeval web-presentasjon og saksutforsker.
"""

import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import Database
from .client import TonsbergInnsynClient
from .evaluator import ByggesakEvaluator
from .models import Byggesak

app = FastAPI(
    title="Byggeval - Tønsberg Byggesaker API",
    description="API for innhenting, evaluering og presentasjon av byggesaker fra Tønsberg kommune",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database(db_path=os.getenv("BYGGEVAL_DB_PATH", "data/byggeval.db"))
# Skånsom klient med 0.6 sekunder forsinkelse mellom hvert kall
client = TonsbergInnsynClient(delay_between_requests=0.6)

# Sync status tracker
sync_state = {
    "is_syncing": False,
    "last_sync": None,
    "last_result": None,
    "progress": ""
}


class SyncRequest(BaseModel):
    pages: int = Field(default=2, ge=1, le=5, description="Maks 5 sider per synkronisering for skånsom drift")
    page_size: int = Field(default=20, ge=5, le=30)
    search: Optional[str] = None
    sakstype: Optional[str] = TonsbergInnsynClient.SAKSTYPE_BYGGESAK
    force_refresh: bool = Field(default=False, description="Hent også saker som allerede er lagret")


def perform_sync(pages: int, page_size: int, search: Optional[str], sakstype: Optional[str], force_refresh: bool = False):
    """Bakgrunnsprosess for skånsom synkronisering."""
    global sync_state
    sync_state["is_syncing"] = True
    sync_state["progress"] = "Kobler til Tønsberg kommunes innsynsløsning..."
    
    try:
        # Hent kjente saks-IDer for å unngå å laste ned samme sak mange ganger
        existing_ids = set() if force_refresh else db.get_all_case_ids()

        def update_progress(msg: str):
            sync_state["progress"] = msg

        raw_cases = client.fetch_cases_batch(
            max_pages=pages,
            page_size=page_size,
            sakstype=sakstype,
            search_term=search,
            fetch_details=True,
            skip_existing_ids=existing_ids,
            progress_callback=update_progress
        )
        
        sync_state["progress"] = f"Evaluerer og lagrer {len(raw_cases)} nye saker..."
        saved = 0
        for raw in raw_cases:
            try:
                case = ByggesakEvaluator.create_byggesak_model(raw)
                db.save_case(case)
                saved += 1
            except Exception as e:
                pass
                
        db.record_sync(cases_synced=saved, error_count=len(raw_cases) - saved, status="success")
        if saved == 0 and len(existing_ids) > 0:
            sync_state["last_result"] = "Ingen nye saker funnet (databasen er allerede oppdatert)."
        else:
            sync_state["last_result"] = f"Synkroniserte {saved} nye saker skånsomt."
    except Exception as e:
        sync_state["last_result"] = f"Feil: {str(e)}"
    finally:
        sync_state["is_syncing"] = False
        sync_state["progress"] = ""


@app.get("/api/cases")
def get_cases(
    search: Optional[str] = Query(None, description="Tekstsøk i tittel, saksnr, adresse, saksbehandler eller firma/utførende"),
    category: Optional[str] = Query(None, description="Kategori (f.eks. Nybygg, Tilbygg & Påbygg, Ulovlighet & Tilsyn)"),
    risk_level: Optional[str] = Query(None, description="Risikonivå (Lav, Moderat, Høy, Kritisk)"),
    stage: Optional[str] = Query(None, description="Saksstadium"),
    company: Optional[str] = Query(None, description="Firma / utførende foretak / søker"),
    deadline_status: Optional[str] = Query(None, description="Friststatus: God tid, Nærmer seg frist, Fristoverskridelse, Vedtatt / Avsluttet"),
    sort_by: str = Query("dato_desc", description="Sortering: dato_desc, dato_asc, deadline_asc, risk_desc, complexity_desc, saksnummer_desc, company_asc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """Henter en liste over byggesaker med støtte for søk, filtrering på firma/kategori/risiko/frister og paginering."""
    cases, total = db.get_cases(
        search=search,
        category=category,
        risk_level=risk_level,
        stage=stage,
        company=company,
        deadline_status=deadline_status,
        sort_by=sort_by,
        limit=limit,
        offset=offset
    )
    return {
        "cases": [c.model_dump() for c in cases],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/api/companies")
def get_companies(limit: int = Query(100, ge=1, le=500)):
    """Henter oversikt over registrerte utførende firmaer, arkitekter og entreprenører med sakstall."""
    companies = db.get_companies(limit=limit)
    return {"companies": companies, "total": len(companies)}


@app.get("/api/cases/{identifikator}")
def get_case_detail(identifikator: str):
    """Henter fullstendige detaljer for en spesifikk byggesak."""
    case = db.get_case(identifikator)
    if not case:
        # Forsøk å hente direkte fra Tønsberg API hvis ikke i database
        try:
            raw = client.fetch_case_details(identifikator)
            if raw:
                case = ByggesakEvaluator.create_byggesak_model(raw)
                db.save_case(case)
        except Exception:
            pass

    if not case:
        raise HTTPException(status_code=404, detail="Saken ble ikke funnet")

    return case.model_dump()


@app.get("/api/stats")
def get_statistics():
    """Henter samlet statistikk og aggregeringer for dashboardet."""
    stats = db.get_statistics()
    stats["sync_state"] = sync_state
    return stats


@app.get("/api/map")
def get_map_points():
    """Henter geokodede punkter for kartvisning."""
    return db.get_map_points()


@app.post("/api/sync")
def trigger_sync(req: SyncRequest, background_tasks: BackgroundTasks):
    """Trigget synkronisering i bakgrunnen."""
    global sync_state
    if sync_state["is_syncing"]:
        return {"status": "already_running", "message": "En synkronisering pågår allerede."}

    background_tasks.add_task(perform_sync, req.pages, req.page_size, req.search, req.sakstype)
    return {"status": "started", "message": f"Synkronisering startet for {req.pages} sider."}


@app.get("/api/sync/status")
def get_sync_status():
    """Henter status for pågående synkronisering."""
    return sync_state


# Monter statiske filer
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(static_dir, "index.html"))
