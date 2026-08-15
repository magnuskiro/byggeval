"""
Datamodeller for Byggeval.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class Dokument(BaseModel):
    """Representerer et enkeltdokument / journalpost i en sak."""
    identifikator: str
    friendly_id: Optional[str] = None  # f.eks. 2026/100903
    tittel: str
    undertittel: Optional[str] = ""
    fra: List[str] = Field(default_factory=list)
    til: List[str] = Field(default_factory=list)
    dato: Optional[str] = None
    saksbehandler: Optional[str] = None
    ansvarlig_enhet: Optional[str] = None
    antall_vedlegg: int = 0
    synlighet: int = 1  # 1 = Offentlig, 2/3 = Skjermet
    paragraf_id: Optional[str] = ""


class AddressInfo(BaseModel):
    """Ekstrahert adresse- og matrikkelinformasjon."""
    raw_address: Optional[str] = None
    street_name: Optional[str] = None
    house_number: Optional[str] = None
    house_letter: Optional[str] = None
    gnr: Optional[int] = None  # Gårdsnummer
    bnr: Optional[int] = None  # Bruksnummer
    fnr: Optional[int] = None  # Festenummer
    snr: Optional[int] = None  # Seksjonsnummer
    matrikkel: Optional[str] = None  # f.eks. "1009/47"
    city: str = "Tønsberg"
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class LegalCheckpoint(BaseModel):
    """Enkelt juridisk vurderingstema i henhold til Plan- og bygningsloven og særlover."""
    id: str  # f.eks. "strandsone", "plan_bya", "plassering_nabo", "infrastruktur_vei", "naturfarer_geo", "visuell_kultur", "dispensasjon", "prosess_ansvar"
    title: str  # f.eks. "Strandsonen og 100-metersbeltet (PBL § 1-8)"
    legal_reference: str  # f.eks. "pbl § 1-8 / SPR for strandsonen"
    status: str  # "Ivaretatt / Konform", "Krever avklaring / Mangel", "Kritisk planavvik / Avslagsrisiko", "Ikke relevant"
    risk_level: str  # "Lav", "Moderat", "Høy", "Kritisk"
    findings: str  # Detaljert saksbehandlervurdering av saken opp mot lovkravet
    requirements_to_pass: Optional[str] = None  # Konkrete krav søker må oppfylle for godkjenning


class EvaluationResult(BaseModel):
    """Resultat fra automatisk evaluering og risikovurdering av byggesaken."""
    category: str  # f.eks. Nybygg, Tilbygg, Bruksendring, Riving, Garasje, Ulovlighet, VA, etc.
    subcategory: Optional[str] = None  # f.eks. Enebolig, Fritidsbolig, Næringsbygg, Hybel
    complexity: str = "Standard"  # Enkel, Standard, Kompleks, Svært kompleks
    complexity_score: int = 5  # 1 - 10
    risk_level: str = "Lav"  # Lav, Moderat, Høy, Kritisk
    risk_score: int = 20  # 1 - 100
    risk_factors: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    stage: str = "Under saksbehandling"  # Mottatt, Under saksbehandling, Vedtatt, Igangsetting, Ferdigattest, Ulovlighet
    summary: str = ""
    recommendation: Optional[str] = None
    days_in_process: Optional[int] = None
    
    # Helhetlig juridisk vurderingsramme etter Plan- og bygningsloven
    legal_checkpoints: List[LegalCheckpoint] = Field(default_factory=list)
    
    # Lovpålagt saksbehandlingsfrist og gjenværende tid (pbl § 21-7 / SAK10)
    statutory_deadline_weeks: int = 12  # 3 eller 12 uker (SAK10 § 7-1 / § 7-2)
    statutory_deadline_days: int = 84
    complete_application_date: Optional[str] = None  # Dato søknaden var komplett (fristen løper herfra iht. pbl § 21-7)
    is_deadline_paused: bool = False  # True dersom fristen er stanset grunnet mangelbrev/tilleggsopplysninger
    deadline_pause_reason: Optional[str] = None
    deadline_date: Optional[str] = None  # f.eks. "02.11.2026"
    days_remaining: Optional[int] = None  # f.eks. 14 (positiv) eller -5 (overskredet)
    deadline_status: str = "God tid"  # "God tid", "Nærmer seg frist", "Fristoverskridelse", "Vedtatt / Avsluttet", "Frist stanset (Mangelbrev)"
    legal_basis: Optional[str] = None  # f.eks. "Plan- og bygningsloven § 21-7 (12-ukers frist løper fra komplett søknad)"
    
    # Juridisk analyse av opprinnelig innsending, saksbehandlingstid og forsinkede mangelbrev
    initial_application_date: Optional[str] = None
    initial_statutory_deadline_weeks: int = 3
    initial_statutory_deadline_date: Optional[str] = None
    first_municipal_response_date: Optional[str] = None
    first_response_delay_days: Optional[int] = None
    is_late_deficiency_notice: bool = False  # True hvis kommunen sendte mangelbrev ETTER at opprinnelig lovfrist utløp
    fee_reduction_entitled: bool = False  # True hvis søker har lovkrav på gebyravkorting etter pbl § 21-7 4. ledd
    fee_reduction_percentage: int = 0  # 0, 25, 50, 75, 100 %
    statutory_consequence_note: Optional[str] = None  # Juridisk forklaring på hva som skjedde og konsekvenser
    
    # Tydelig merking av evaluert analyse
    is_automated_analysis: bool = True
    analysis_disclaimer: str = "Automatisert analyse og faglig veiledning fra Byggeval. Erstattet ikke kommunens formelle enkeltvedtak."


class Byggesak(BaseModel):
    """Hovedmodell for en byggesak i Tønsberg kommune."""
    identifikator: str  # f.eks. a-e8411f20...
    saksnummer: str  # f.eks. 2026/15947
    tittel: str
    undertittel: Optional[str] = ""
    sakstype: str = "Byggesak"
    saks_beskrivelse: str = "Byggesak"
    dato: str  # f.eks. 10.08.2026
    saksbehandler: Optional[str] = None
    status_tittel: str = "Under behandling"
    er_ferdig: bool = False
    innsyn_url: Optional[str] = None
    
    # Offisiell kommunal status og formelt vedtak
    official_status: str = "Under behandling"  # Kommunens offisielle saksstatus
    has_official_decision: bool = False  # Om det foreligger formelt kommunalt vedtak
    official_decision_type: Optional[str] = "Ikke avgjort (Under behandling)"  # F.eks. "Innvilget / Rammetillatelse", "Innvilget / Ett-trinnstillatelse", "Igangsettingstillatelse", "Ferdigattest", "Avslag"
    decision_document_title: Optional[str] = None  # Tittel på det offisielle vedtaksdokumentet
    decision_date: Optional[str] = None  # Dato for kommunens vedtak
    complete_application_date: Optional[str] = None  # Dato for komplett søknad (fristen løper herfra)
    is_deadline_paused: bool = False  # Frist stanset pga mangelbrev
    is_late_deficiency_notice: bool = False  # Forsinket mangelbrev fra kommunen
    fee_reduction_percentage: int = 0  # Krav på gebyrreduksjon (0 - 100 %)
    
    # Utførende / foretak / søker
    primary_company: Optional[str] = None  # Hovedansvarlig firma / søker
    companies: List[str] = Field(default_factory=list)  # Alle involverte firmaer
    
    address_info: AddressInfo = Field(default_factory=AddressInfo)
    evaluation: Optional[EvaluationResult] = None
    dokumenter: List[Dokument] = Field(default_factory=list)
    
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SyncStats(BaseModel):
    """Statistikk over synkronisering."""
    last_sync: Optional[str] = None
    total_cases: int = 0
    synced_cases: int = 0
    errors: int = 0
    status: str = "idle"


class ImprovementAction(BaseModel):
    """Konkret forbedringsforslag for å øke innvilgelsessannsynligheten."""
    priority: str  # "Høy", "Medium", "Lav"
    category: str  # f.eks. "Plangrunnlag & BYA", "Strandsone", "Nabosamtykke", "Vedlegg"
    title: str
    description: str
    action_required: str  # Hva søker må gjøre konkret


class PreEvaluationReport(BaseModel):
    """Omfattende rapport for forhåndsevaluering av usendt byggesøknad."""
    tiltak_tittel: str
    category: str
    subcategory: Optional[str] = None
    address: Optional[str] = None
    matrikkel: Optional[str] = None
    
    # Kvantitative nøkkeltall & score
    approval_probability_pct: int  # 0 - 100 %
    probability_verdict: str  # f.eks. "Høy sannsynlighet for innvilgelse"
    quality_score: int  # 0 - 100
    complexity_score: int  # 1 - 10
    complexity_level: str  # Enkel, Standard, Kompleks, Svært kompleks
    risk_level: str  # Lav, Moderat, Høy, Kritisk
    risk_score: int  # 0 - 100
    
    # Saksbehandlingsfrist & lovhjemmel
    statutory_deadline_weeks: int  # 3 eller 12 uker
    statutory_deadline_basis: str  # Begrunnelse for fristvalg (pbl § 21-7 / SAK10)
    
    # Areal- og utnyttelsesberegning (%-BYA)
    bya_summary: Optional[Dict[str, Any]] = None
    
    # Forbedringstiltak og sjekkpunkter
    improvements: List[ImprovementAction] = Field(default_factory=list)
    missing_attachments: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    legal_checkpoints: List[LegalCheckpoint] = Field(default_factory=list)
    
    # Oppsummering og saksbehandlerråd
    summary: str
    recommendations: str
    evaluated_at: str = Field(default_factory=lambda: datetime.now().strftime("%d.%m.%Y %H:%M"))
    extracted_text_snippet: Optional[str] = None

