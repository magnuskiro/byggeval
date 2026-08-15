"""
FastAPI REST API for Byggeval web-presentasjon og saksutforsker.
"""

import os
import io
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from .database import Database
from .client import TonsbergInnsynClient
from .evaluator import ByggesakEvaluator
from .models import Byggesak, PreEvaluationReport

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
# Skånsom klient med 10 sekunder forsinkelse mellom hvert kall for å unngå abuse
client = TonsbergInnsynClient(delay_between_requests=10.0)

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
        skipped = 0
        for raw in raw_cases:
            if not ByggesakEvaluator.is_relevant_building_case(raw):
                skipped += 1
                continue
            try:
                case = ByggesakEvaluator.create_byggesak_model(raw)
                db.save_case(case)
                saved += 1
            except Exception as e:
                pass
                
        db.record_sync(cases_synced=saved, error_count=len(raw_cases) - saved - skipped, status="success")
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
    intake_filter: Optional[str] = Query(None, description="Mottakskontroll: recent_all, recent_complete, recent_missing, recent_pending, recent_late"),
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
        intake_filter=intake_filter,
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
def get_statistics(company: Optional[str] = Query(None, description="Filtrer statistikk på spesifikt utførende foretak / søker")):
    """Henter samlet statistikk og aggregeringer for dashboardet, med støtte for foretaksfiltrering."""
    stats = db.get_statistics(company=company)
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


def extract_text_from_file(data: bytes, filename: str) -> str:
    """Ekstraherer ren tekst fra opplastede PDF-er eller tekstfiler for forhåndsevaluering."""
    fn = filename.lower()
    if fn.endswith(".pdf") and PdfReader is not None:
        try:
            reader = PdfReader(io.BytesIO(data))
            text_parts = []
            for page in reader.pages[:15]:  # Begrens til første 15 sider
                t = page.extract_text()
                if t:
                    text_parts.append(t)
            return "\n".join(text_parts)
        except Exception:
            return ""
    elif fn.endswith((".txt", ".md", ".json", ".xml", ".csv")):
        try:
            return data.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return ""


@app.post("/api/pre-evaluate")
async def pre_evaluate_application(
    tiltak_tittel: str = Form(..., description="Tittel eller kort beskrivelse av tiltaket"),
    address_raw: Optional[str] = Form(None, description="Adresse eller gnr/bnr i Tønsberg"),
    beskrivelse: Optional[str] = Form(None, description="Utdypende prosjektbeskrivelse"),
    tomteareal_m2: Optional[float] = Form(None, description="Tomtens areal i m²"),
    bya_eksisterende_m2: Optional[float] = Form(None, description="Eksisterende bebygd areal (m²)"),
    bya_tiltak_m2: Optional[float] = Form(None, description="Nytt bebygd areal for omsøkt tiltak (m²)"),
    avstand_nabogrense_m: Optional[float] = Form(None, description="Korteste avstand til nabogrense i meter"),
    har_nabosamtykke: bool = Form(False, description="Foreligger skriftlig nabosamtykke"),
    har_avkjorsel_endring: bool = Form(False, description="Omfatter endring eller etablering av avkjørsel"),
    er_i_strandsone: bool = Form(False, description="Ligger i 100-metersbeltet langs sjøen"),
    er_i_lnfr: bool = Form(False, description="Ligger i LNFR-område"),
    har_dispensasjonssoknad: bool = Form(False, description="Det er utarbeidet dispensasjonssøknad"),
    har_nabomerknader: bool = Form(False, description="Det er mottatt nabomerknader"),
    har_situasjonsplan: bool = Form(False, description="Situasjonsplan 1:500 er vedlagt"),
    har_fasadetegninger: bool = Form(False, description="Fasadetegninger 1:100 er vedlagt"),
    har_snittegninger: bool = Form(False, description="Snittegninger 1:100 er vedlagt"),
    har_ansvarsretter: bool = Form(False, description="Gjennomføringsplan / ansvarsretter er avklart"),
    files: Optional[List[UploadFile]] = File(None, description="Opplastede tegninger, søknadsdokumenter eller PDF-er")
):
    """
    Kjører forhåndsevaluering av en ny, usendt byggesøknad.
    Beregner innvilgelsessannsynlighet %, kvalitetsscore, kompleksitet og gir konkrete forbedringsanbefalinger.
    """
    extracted_texts = []
    uploaded_filenames = []

    if files:
        for f in files:
            if not f.filename:
                continue
            uploaded_filenames.append(f.filename)
            try:
                content = await f.read()
                txt = extract_text_from_file(content, f.filename)
                if txt:
                    extracted_texts.append(f"--- Vedlegg: {f.filename} ---\n" + txt[:4000])
            except Exception:
                pass

    combined_file_text = "\n\n".join(extracted_texts)

    report = ByggesakEvaluator.pre_evaluate_application(
        tiltak_tittel=tiltak_tittel,
        address_raw=address_raw,
        beskrivelse=beskrivelse,
        extracted_file_text=combined_file_text,
        uploaded_filenames=uploaded_filenames,
        tomteareal_m2=tomteareal_m2,
        bya_eksisterende_m2=bya_eksisterende_m2,
        bya_tiltak_m2=bya_tiltak_m2,
        avstand_nabogrense_m=avstand_nabogrense_m,
        har_nabosamtykke=har_nabosamtykke,
        har_avkjorsel_endring=har_avkjorsel_endring,
        er_i_strandsone=er_i_strandsone,
        er_i_lnfr=er_i_lnfr,
        har_dispensasjonssoknad=har_dispensasjonssoknad,
        har_nabomerknader=har_nabomerknader,
        har_situasjonsplan=har_situasjonsplan,
        har_fasadetegninger=har_fasadetegninger,
        har_snittegninger=har_snittegninger,
        har_ansvarsretter=har_ansvarsretter
    )

    return report.model_dump()


# Monter statiske filer
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(static_dir, "index.html"))

