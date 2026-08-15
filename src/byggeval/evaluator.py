"""
Evalueringsmotor for byggesaker:
- Parser adresser og matrikkel (gnr/bnr/fnr/snr)
- Kategoriserer tiltak
- Beregner risiko- og kompleksitetsscore
- Genererer sammendrag og anbefalinger
"""

import re
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
from .models import AddressInfo, EvaluationResult, Byggesak, Dokument, LegalCheckpoint, PreEvaluationReport, ImprovementAction


class ByggesakEvaluator:
    """Intelligent analysator og evalueringsmotor for byggesaker."""

    @staticmethod
    def parse_address_and_matrikkel(title: str, undertittel: str = "") -> AddressInfo:
        """
        Parser adresse, husnummer, bokstav og gnr/bnr fra saks- og dokumenttitler.
        Eksempel: 'Halfdan Wilhelmsens alle 16 - 1009/47 - bruksendring'
                  'Skallevoldveien 35 C - 137/78 - forhåndskonferanse'
                  'Vivestadlinna 680 - 612/22 - minirenseanlegg'
        """
        info = AddressInfo(raw_address=title)
        combined = f"{title} {undertittel}".strip()

        # 1. Let etter Gnr/Bnr i formatet '1009/47' eller 'Gnr 137 Bnr 78' eller '137/78/0'
        matrikkel_match = re.search(r'\b(\d{1,5})\s*/\s*(\d{1,5})(?:\s*/\s*(\d{1,4}))?(?:\s*/\s*(\d{1,4}))?\b', combined)
        if matrikkel_match:
            gnr = int(matrikkel_match.group(1))
            bnr = int(matrikkel_match.group(2))
            info.gnr = gnr
            info.bnr = bnr
            info.matrikkel = f"{gnr}/{bnr}"
            if matrikkel_match.group(3):
                info.fnr = int(matrikkel_match.group(3))
            if matrikkel_match.group(4):
                info.snr = int(matrikkel_match.group(4))

        # 2. Splitt tittel på ' - ' for å hente adresse fra første ledd
        parts = [p.strip() for p in title.split('-') if p.strip()]
        if parts:
            first_part = parts[0]
            # Sjekk om første del ser ut som en adresse (inneholder ord og ev. tall/bokstav)
            # f.eks. 'Halfdan Wilhelmsens alle 16', 'Skallevoldveien 35 C', 'Huitfeldts gate 3'
            addr_match = re.search(r'^([A-ZÆØÅa-zæøå\s\.\-]+?)(?:\s+(\d+)\s*([A-Za-z])?)?$', first_part)
            if addr_match:
                street = addr_match.group(1).strip()
                # Filtrer ut ord som ikke er gatenavn
                non_streets = ['søknad', 'klage', 'anmodning', 'varsel', 'vedtak', 'innsyn', 'dispensasjon']
                if not any(w in street.lower() for w in non_streets):
                    info.street_name = street
                    if addr_match.group(2):
                        info.house_number = addr_match.group(2)
                    if addr_match.group(3):
                        info.house_letter = addr_match.group(3).upper()

        return info

    @staticmethod
    def is_relevant_building_case(raw_sak: Dict[str, Any]) -> bool:
        """
        Sjekker om saken er en reell byggesak som krever kommunal saksbehandling,
        og filtrerer bort rene orienteringsmeldinger som 'melding om bygning som er unntatt søknadsplikt'.
        """
        title = (raw_sak.get("tittel") or "").lower()
        undertittel = (raw_sak.get("undertittel") or "").lower()
        
        # Samle tekst fra saksdokumenter
        docs = raw_sak.get("dokumenter", [])
        docs_text = " ".join([
            (d.get("tittel") if isinstance(d, dict) else getattr(d, "tittel", "")) or "" 
            for d in docs
        ]).lower()
        
        all_text = f"{title} {undertittel} {docs_text}"
        
        # Sjekk om det er melding om tiltak unntatt søknadsplikt
        is_unntatt_notification = any(pattern in all_text for pattern in [
            "unntatt søknadsplikt",
            "unntatt fra søknadsplikt",
            "melding om bygning som er unntatt",
            "melding om tiltak som er unntatt",
            "melding om frittliggende bygning",
            "melding etter pbl § 20-5",
            "melding om tiltak"
        ])
        
        # Hvis det kun er en melding om unntatt tiltak og INGEN reell søknad om tillatelse/dispensasjon/forhåndskonferanse:
        has_actual_application = any(pattern in all_text for pattern in [
            "søknad om tillatelse",
            "søknad om rammetillatelse",
            "søknad om ett-trinn",
            "søknad om igangsetting",
            "søknad om dispensasjon",
            "forhåndskonferanse",
            "ulovlighet",
            "tilsyn",
            "rammetillatelse",
            "ett-trinnstillatelse"
        ])
        
        if is_unntatt_notification and not has_actual_application:
            return False
            
        return True

    @classmethod
    def evaluate_case(cls, sak_data: Dict[str, Any]) -> EvaluationResult:
        """
        Gjennomfører en helhetlig evaluering av en byggesak basert på tittel,
        dokumenter, sakstype og saksgang.
        """
        title = sak_data.get("tittel", "")
        undertittel = sak_data.get("undertittel", "")
        sakstype = sak_data.get("sakstype", "Byggesak")
        saksbeskrivelse = sak_data.get("saksBeskrivelse", "")
        dokumenter = sak_data.get("dokumenter", [])
        
        all_text = f"{title} {undertittel} {sakstype} {saksbeskrivelse} " + " ".join(
            d.get("tittel", "") + " " + d.get("undertittel", "") for d in dokumenter
        )
        all_text_lower = all_text.lower()

        # 1. Bestem hovedkategori og underkategori
        category, subcategory = cls._categorize(all_text_lower, title.lower())

        # 2. Identifiser risikofaktorer og flagg
        risk_factors: List[str] = []
        flags: List[str] = []
        risk_score = 15  # Grunnscore
        complexity_score = 4

        # Sjekk dispensasjon
        if any(w in all_text_lower for w in ["dispensasjon", "unntak fra", "fravik", "pbl § 19"]):
            risk_factors.append("Søknad om dispensasjon fra plan- og bygningsloven eller arealplan")
            flags.append("dispensasjon")
            risk_score += 25
            complexity_score += 2

        # Sjekk ulovlighet / tilsyn
        if any(w in all_text_lower for w in ["ulovlighet", "tilsyn", "pålegg", "stansingsvarsel", "tvangsmulkt", "avvik"]):
            risk_factors.append("Ulovlighetsoppfølging, tilsyn eller pålegg registrert")
            flags.append("ulovlighet")
            risk_score += 35
            complexity_score += 2

        # Sjekk nabovarsel / nabomerknad / klage
        if any(w in all_text_lower for w in ["merknad fra nabo", "naboklage", "klage", "protest", "innsigelse", "nabovarsel"]):
            risk_factors.append("Nabomerknader, klage eller naboinnsigelser i saken")
            flags.append("nabokonflikt")
            risk_score += 20
            complexity_score += 1

        # Sjekk strandsone / vern / kulturminner
        if any(w in all_text_lower for w in ["strandsone", "100-metersbelte", "verneområde", "kulturminne", "sefrak", "fredet", "lnf", "landbruk"]):
            risk_factors.append("Berører strandsonen, LNF-område eller kulturminne/vernesone")
            flags.append("vernesone")
            risk_score += 20
            complexity_score += 2

        # Sjekk riving + nybygg
        if "riving" in all_text_lower and ("nybygg" in all_text_lower or "ny enebolig" in all_text_lower or "oppføring" in all_text_lower):
            risk_factors.append("Kombinert riving og nyoppføring på eksisterende tomt")
            flags.append("riving_og_nybygg")
            complexity_score += 1
            risk_score += 10

        # Sjekk minirenseanlegg / VA
        if any(w in all_text_lower for w in ["minirenseanlegg", "utslippstillatelse", "vann og avløp", "forurensning"]):
            flags.append("utslipp_va")
            if "minirenseanlegg" in all_text_lower:
                risk_factors.append("Utslippstillatelse / minirenseanlegg krever godkjenning etter forurensningsforskriften")
                risk_score += 10

        # Sjekk geoteknikk / ras / flom
        if any(w in all_text_lower for w in ["geoteknisk", "kvikkleire", "flomsone", "skredfare", "grunnforhold"]):
            risk_factors.append("Krevende grunnforhold eller fareområde (kvikkleire/flom/skred)")
            flags.append("geofare")
            risk_score += 25
            complexity_score += 2

        # Beregn dager i prosess
        days_in_process = cls._calculate_days_in_process(sak_data.get("dato"))

        # Sjekk ferdigattest
        if any(w in all_text_lower for w in ["ferdigattest", "midlertidig brukstillatelse", "attest"]):
            flags.append("ferdigattest")

        # Begrens score innenfor gyldige intervaller
        risk_score = min(100, max(5, risk_score))
        complexity_score = min(10, max(1, complexity_score))

        # Bestem risikonivå
        if risk_score >= 70:
            risk_level = "Kritisk"
        elif risk_score >= 45:
            risk_level = "Høy"
        elif risk_score >= 25:
            risk_level = "Moderat"
        else:
            risk_level = "Lav"

        # Bestem kompleksitetsnivå
        if complexity_score >= 8:
            complexity = "Svært kompleks"
        elif complexity_score >= 6:
            complexity = "Kompleks"
        elif complexity_score >= 4:
            complexity = "Standard"
        else:
            complexity = "Enkel"

        # Bestem saksstadium
        stage = cls._determine_stage(sak_data, all_text_lower)

        # Beregn lovpålagte saksbehandlingsfrister og gjenværende tid (pbl § 21-7 / SAK10)
        # Fristen løper fra det tidspunkt søknaden er komplett!
        deadline_info = cls._calculate_deadlines(
            sak_data,
            category=category,
            subcategory=subcategory,
            flags=flags,
            stage=stage
        )

        # Beregn dager i prosess fra komplett søknad
        days_in_process = deadline_info.get("days_in_process") or cls._calculate_days_in_process(sak_data.get("dato"))

        # Vurder mottakskontroll og kompletthet etter SAK10 § 7-1 (for nyere saker 0-75 dager)
        intake_info = cls._evaluate_intake_control(sak_data, deadline_info, stage)

        # Generer norsk sammendrag og anbefaling
        summary = cls._generate_summary(title, category, subcategory, risk_level, risk_factors, stage)
        recommendation = cls._generate_recommendation(category, risk_factors, stage)

        return EvaluationResult(
            category=category,
            subcategory=subcategory,
            complexity=complexity,
            complexity_score=complexity_score,
            risk_level=risk_level,
            risk_score=risk_score,
            risk_factors=risk_factors,
            flags=flags,
            stage=stage,
            summary=summary,
            recommendation=recommendation,
            days_in_process=days_in_process,
            statutory_deadline_weeks=deadline_info["weeks"],
            statutory_deadline_days=deadline_info["days"],
            complete_application_date=deadline_info["complete_application_date"],
            is_deadline_paused=deadline_info["is_deadline_paused"],
            deadline_pause_reason=deadline_info["deadline_pause_reason"],
            deadline_date=deadline_info["deadline_date"],
            days_remaining=deadline_info["days_remaining"],
            deadline_status=deadline_info["deadline_status"],
            legal_basis=deadline_info["legal_basis"],
            initial_application_date=deadline_info.get("initial_application_date"),
            initial_statutory_deadline_weeks=deadline_info.get("initial_statutory_deadline_weeks", 3),
            initial_statutory_deadline_date=deadline_info.get("initial_statutory_deadline_date"),
            first_municipal_response_date=deadline_info.get("first_municipal_response_date"),
            first_response_delay_days=deadline_info.get("first_response_delay_days"),
            is_late_deficiency_notice=deadline_info.get("is_late_deficiency_notice", False),
            fee_reduction_entitled=deadline_info.get("fee_reduction_entitled", False),
            fee_reduction_percentage=deadline_info.get("fee_reduction_percentage", 0),
            statutory_consequence_note=deadline_info.get("statutory_consequence_note"),
            is_recent_case=intake_info["is_recent_case"],
            intake_status=intake_info["intake_status"],
            intake_status_label=intake_info["intake_status_label"],
            intake_deficiency_details=intake_info["intake_deficiency_details"],
            intake_days_since_submission=intake_info["intake_days_since_submission"],
            intake_statutory_window_status=intake_info["intake_statutory_window_status"]
        )

    @classmethod
    def _calculate_deadlines(
        cls,
        sak_data: Dict[str, Any],
        category: str,
        subcategory: Optional[str],
        flags: List[str],
        stage: str
    ) -> Dict[str, Any]:
        """
        Beregner lovpålagt saksbehandlingsfrist etter Plan- og bygningsloven § 21-7 og SAK10.
        VIKTIG: Saksbehandlingstiden løper fra det tidspunkt søknaden er KOMPLETT (SAK10 § 7-1 / § 7-2).
        Dersom kommunen har sendt mangelbrev / etterspurt tilleggsdokumentasjon, fryses fristen inntil
        komplett supplering er mottatt.
        """
        # 1. Bestem opprinnelig forventet lovfrist basert på innsendt søknad
        initial_weeks = 3
        initial_days = 21
        if "dispensasjon" in flags or "vernesone" in flags or category in ["Nybygg", "Næring / Formålsbygg"]:
            initial_weeks = 12
            initial_days = 84

        weeks = initial_weeks
        days = initial_days
        legal_basis = f"Plan- og bygningsloven § 21-7 ({initial_weeks}-ukers standardfrist løper fra komplett søknad)"

        if stage == "Forhåndskonferanse":
            weeks = 2
            days = 14
            initial_weeks = 2
            initial_days = 14
            legal_basis = "Plan- og bygningsloven § 21-1 / SAK10 § 7-5 (2-ukers frist for forhåndskonferanse)"
        elif stage in ["Igangsettingstillatelse", "Ferdigattest omsøkt/utstedt"]:
            weeks = 3
            days = 21
            initial_weeks = 3
            initial_days = 21
            legal_basis = "Plan- og bygningsloven § 21-7 2. ledd / SAK10 § 7-3/4 (3-ukers frist for igangsetting/ferdigattest)"
        elif (
            category in ["Tilbygg & Påbygg", "Garasje & Uthus", "Fasadeendring", "Riving", "Bruksendring"]
            and "dispensasjon" not in flags
            and "nabokonflikt" not in flags
            and "vernesone" not in flags
            and "geofare" not in flags
            and "utslipp_va" not in flags
        ):
            weeks = 3
            days = 21
            initial_weeks = 3
            initial_days = 21
            legal_basis = "Plan- og bygningsloven § 21-7 1. ledd / SAK10 § 7-1 (3-ukers frist: kurant tiltak i tråd med plan uten dispensasjoner)"
        elif "dispensasjon" in flags or "vernesone" in flags:
            weeks = 12
            days = 84
            initial_weeks = 12
            initial_days = 84
            legal_basis = "Plan- og bygningsloven § 21-7 4. ledd (12-ukers frist: krever dispensasjonsvedtak etter pbl kap 19)"

        # 2. Undersøk dokumenter for mangelbrev, dispensasjonskrav og innsendt supplering
        initial_date_str = sak_data.get("dato")
        initial_dt = None
        initial_deadline_dt = None
        initial_deadline_str = None
        if initial_date_str:
            try:
                from datetime import timedelta
                initial_dt = datetime.strptime(initial_date_str.strip(), "%d.%m.%Y")
                initial_deadline_dt = initial_dt + timedelta(days=initial_days)
                initial_deadline_str = initial_deadline_dt.strftime("%d.%m.%Y")
            except Exception:
                pass

        docs = sak_data.get("dokumenter") or sak_data.get("journalposter") or []
        latest_supplement_dt = None
        latest_supplement_str = None
        latest_mangelbrev_dt = None
        latest_mangelbrev_str = None
        first_municipal_response_dt = None
        first_municipal_response_str = None
        has_dispensation_demand = False

        mangel_keywords = [
            "mangelbrev", "etterlyser", "etterlysning", "etterspør", "ber om tilleggs", 
            "tilleggsdokumentasjon", "mangler ved søknad", "avvist", "varsel om avslag",
            "krever dispensasjon", "avstandsbestemmelsen i vegloven"
        ]

        supplement_keywords = [
            "ettersending", "supplering", "tilleggsopplysning", "revidert", "svar på mangel", 
            "supplerende", "situasjonsplan", "dispensasjon fra", "søknad om dispensasjon",
            "redegjørelse", "nabovarsel", "kvittering", "fullmakt", "fasadetegning", "snittegning"
        ]

        for d in docs:
            dtit = d.get("tittel", "").lower() if isinstance(d, dict) else (d.tittel.lower() if hasattr(d, "tittel") else "")
            ddato = d.get("dato") if isinstance(d, dict) else (d.dato if hasattr(d, "dato") else None)
            dfra = d.get("fra", []) if isinstance(d, dict) else (d.fra if hasattr(d, "fra") else [])
            if not ddato:
                continue

            parsed_d = None
            try:
                parsed_d = datetime.strptime(ddato.strip(), "%d.%m.%Y")
            except Exception:
                continue

            is_municipal = (not dfra) or any("kommune" in str(f).lower() for f in dfra)
            is_applicant = bool(dfra) and not is_municipal

            # Registrer første kommunale respons/mangelbrev
            if is_municipal and (not initial_dt or parsed_d > initial_dt):
                if not first_municipal_response_dt or parsed_d < first_municipal_response_dt:
                    first_municipal_response_dt = parsed_d
                    first_municipal_response_str = ddato

            # Sjekk om det er dispensasjonskrav/mangelbrev fra kommunen
            if any(w in dtit for w in mangel_keywords) and is_municipal:
                if not latest_mangelbrev_dt or parsed_d > latest_mangelbrev_dt:
                    latest_mangelbrev_dt = parsed_d
                    latest_mangelbrev_str = ddato
                if "dispensasjon" in dtit or "vegloven" in dtit:
                    has_dispensation_demand = True

            # Sjekk innsendt dokumentasjon / svar fra søker etter opprinnelig innsending
            if not is_municipal or any(w in dtit for w in supplement_keywords):
                if not any(w in dtit for w in mangel_keywords):
                    if is_applicant or any(w in dtit for w in supplement_keywords):
                        if not initial_dt or parsed_d > initial_dt:
                            if not latest_supplement_dt or parsed_d > latest_supplement_dt:
                                latest_supplement_dt = parsed_d
                                latest_supplement_str = ddato

        # Hvis det kreves dispensasjon (pbl kap 19 eller vegloven § 29), oppjusteres frist til 12 uker
        if has_dispensation_demand or "dispensasjon" in flags or "vernesone" in flags:
            weeks = 12
            days = 84
            if has_dispensation_demand or "vegloven" in str(sak_data):
                legal_basis = "Plan- og bygningsloven § 21-7 4. ledd jf. SAK10 § 7-4 3. ledd (12-ukers frist løper fra komplett dispensasjonssøknad/situasjonsplan mottatt)"
            else:
                legal_basis = "Plan- og bygningsloven § 21-7 4. ledd / SAK10 § 7-2 (12-ukers frist: krever dispensasjonsvedtak etter pbl kap 19)"

        # 3. Avgjør juridisk komplett søknadsdato (pbl § 21-7 jf. SAK10 § 7-4)
        complete_dt = initial_dt
        complete_date_str = initial_date_str

        # Dersom det er ettersendt nødvendig dokumentasjon eller dispensasjonssøknad etter opprinnelig innsending:
        if latest_supplement_dt and (not initial_dt or latest_supplement_dt > initial_dt):
            complete_dt = latest_supplement_dt
            complete_date_str = latest_supplement_str

        # 4. Sjekk om fristen er stanset/fryst pga ubesvart mangelbrev (SAK10 § 7-4 2. ledd)
        is_deadline_paused = False
        deadline_pause_reason = None
        if latest_mangelbrev_dt:
            if not latest_supplement_dt or latest_mangelbrev_dt > latest_supplement_dt:
                is_deadline_paused = True
                deadline_pause_reason = f"Kommunen etterspurte tilleggsdokumentasjon/dispensasjon {latest_mangelbrev_str}. Fristen er stanset i påvente av svar."

        # 5. Juridisk analyse av forsinket mangelbrev og gebyravkorting
        is_late_deficiency_notice = False
        fee_reduction_entitled = False
        fee_reduction_percentage = 0
        first_response_delay_days = None
        statutory_consequence_note = None

        if initial_dt and first_municipal_response_dt:
            first_response_delay_days = (first_municipal_response_dt.date() - initial_dt.date()).days
            if initial_deadline_dt and first_municipal_response_dt.date() > initial_deadline_dt.date():
                is_late_deficiency_notice = True
                fee_reduction_entitled = True
                days_over = (first_municipal_response_dt.date() - initial_deadline_dt.date()).days
                overdue_weeks = max(1, (days_over // 7) + 1)
                fee_reduction_percentage = min(100, overdue_weeks * 25)
                statutory_consequence_note = (
                    f"⚠️ Forsinket mangelbrev / fristbrudd: Kommunen brukte {first_response_delay_days} dager "
                    f"på første henvendelse (opprinnelig lovfrist var {initial_days} dager). "
                    f"Lovpålagt fristoverskridelse inntrådte før kommunens etterlysning. "
                    f"Søker har rettskrav på {fee_reduction_percentage}% gebyravkorting etter pbl § 21-7 4. ledd."
                )

        deadline_date = None
        days_remaining = None
        deadline_status = "God tid"
        days_in_proc = None

        if complete_dt:
            from datetime import timedelta
            deadline_dt = complete_dt + timedelta(days=days)
            deadline_date = deadline_dt.strftime("%d.%m.%Y")
            
            # Beregn gjenværende dager mot dagens dato
            delta = (deadline_dt.date() - datetime.now().date()).days
            days_remaining = delta
            days_in_proc = max(0, (datetime.now().date() - (initial_dt.date() if initial_dt else complete_dt.date())).days)

            if stage in ["Vedtatt / Tillatelse gitt", "Ferdigbehandlet"]:
                deadline_status = "Vedtatt / Avsluttet"
            elif is_deadline_paused:
                deadline_status = "Frist stanset (Mangelbrev)"
            elif days_remaining < 0:
                deadline_status = "Fristoverskridelse"
            elif days_remaining <= 14:
                deadline_status = "Nærmer seg frist"
            else:
                deadline_status = "God tid"

        return {
            "weeks": weeks,
            "days": days,
            "complete_application_date": complete_date_str,
            "is_deadline_paused": is_deadline_paused,
            "deadline_pause_reason": deadline_pause_reason,
            "deadline_date": deadline_date,
            "days_remaining": days_remaining,
            "days_in_process": days_in_proc,
            "deadline_status": deadline_status,
            "legal_basis": legal_basis,
            "initial_application_date": initial_date_str,
            "initial_statutory_deadline_weeks": initial_weeks,
            "initial_statutory_deadline_date": initial_deadline_str,
            "first_municipal_response_date": first_municipal_response_str,
            "first_response_delay_days": first_response_delay_days,
            "is_late_deficiency_notice": is_late_deficiency_notice,
            "fee_reduction_entitled": fee_reduction_entitled,
            "fee_reduction_percentage": fee_reduction_percentage,
            "statutory_consequence_note": statutory_consequence_note
        }

    @staticmethod
    def _categorize(text: str, title: str) -> Tuple[str, Optional[str]]:
        """Kategoriserer tiltaket og eventuell underkategori."""
        if any(w in text for w in ["tilsyn", "ulovlighet", "ulovlig", "stansingsvarsel"]):
            return "Ulovlighet & Tilsyn", "Ulovlighetsoppfølging"
            
        if any(w in text for w in ["ny enebolig", "oppføring av enebolig", "nytt bolighus"]):
            return "Nybygg", "Enebolig"
            
        if any(w in text for w in ["rekkehus", "tomannsbolig", "firemannsbolig", "leilighetsbygg", "flermannsbolig"]):
            return "Nybygg", "Boligkompleks / Rekkehus"
            
        if any(w in text for w in ["næringsbygg", "lagerbygg", "kontorbygg", "forretningsbygg", "nettstasjon", "skole", "barnehage"]):
            return "Næring / Formålsbygg", "Næringsbygg"

        if any(w in text for w in ["hytte", "fritidsbolig", "anneks til hytte"]):
            return "Nybygg", "Fritidsbolig"

        if any(w in text for w in ["tilbygg", "påbygg", "underbygg", "vinterhage", "hagestue", "veranda", "terrasse", "balkong"]):
            sub = "Hagestue / Terrasse" if any(w in text for w in ["hagestue", "vinterhage", "terrasse"]) else "Tilbygg / Påbygg"
            return "Tilbygg & Påbygg", sub

        if any(w in text for w in ["bruksendring", "tilleggsdel til hoveddel", "kjeller og loft", "hybel", "sekundærleilighet"]):
            return "Bruksendring", "Kjeller/Loft/Hybel"

        if any(w in text for w in ["garasje", "carport", "uthus", "bod", "biloppstillingsplass"]):
            return "Garasje & Uthus", "Garasje / Carport"

        if any(w in text for w in ["riving av garasje", "riving av enebolig", "riving", "fjerning av bygg"]):
            return "Riving", "Riving av bygg"

        if any(w in text for w in ["fasadeendring", "endring av fasade", "vindusendring", "takopplett", "takendring"]):
            return "Fasadeendring", "Fasade & Tak"

        if any(w in text for w in ["minirenseanlegg", "utslipp", "vann og avløp", "renseanlegg", "stikkledning"]):
            return "Vann & Avløp / Utslipp", "Minirenseanlegg"

        if any(w in text for w in ["forhåndskonferanse", "anmodning om forhåndskonferanse"]):
            return "Forhåndskonferanse", "Veiledning"

        if any(w in text for w in ["deling", "fradeling", "grensejustering", "oppmåling"]):
            return "Deling & Oppmåling", "Eiendomsdeling"

        if any(w in text for w in ["støttemur", "terrenginngrep", "brygge", "flytebrygge", "gjerde", "spilegjerde"]):
            return "Utemiljø & Terreng", "Støttemur / Brygge"

        if "nybygg" in text or "oppføring" in text:
            return "Nybygg", "Oppføring av tiltak"

        return "Byggesak (Annet)", "Generell byggesak"

    @staticmethod
    def _determine_stage(sak_data: Dict[str, Any], text: str) -> str:
        """Bestemmer hvor i saksbehandlingsløpet saken befinner seg."""
        status = sak_data.get("status", {})
        status_tittel = status.get("tittel", "") if isinstance(status, dict) else ""
        
        if any(w in text for w in ["ferdigattest utstedt", "ferdigattest"]):
            return "Ferdigattest"
            
        if (isinstance(status, dict) and status.get("erFerdig")) or status_tittel in ["Avsluttet", "Ferdigbehandlet", "Arkivert"]:
            return "Ferdigbehandlet"
            
        if any(w in text for w in ["igangsettingstillatelse", "igangsetting"]):
            return "Igangsettingstillatelse"
        if any(w in text for w in ["rammetillatelse", "tillatelse i ett trinn", "delegert vedtak", "godkjent søknad"]):
            return "Vedtatt / Tillatelse gitt"
        if any(w in text for w in ["forhåndskonferanse"]):
            return "Forhåndskonferanse"
        if any(w in text for w in ["ulovlighet", "stansingsvarsel"]):
            return "Ulovlighetsoppfølging pågår"
        if any(w in text for w in ["manglende opplysninger", "tilleggsdokumentasjon", "supplering"]):
            return "Avventer tilleggsdokumentasjon"

        return "Under saksbehandling"

    @staticmethod
    def _calculate_days_in_process(date_str: Optional[str]) -> Optional[int]:
        """Beregner antall dager saken har vært til behandling."""
        if not date_str:
            return None
        try:
            # Parse norsk datoformat 'DD.MM.YYYY'
            dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
            delta = datetime.now() - dt
            return max(0, delta.days)
        except Exception:
            return None

    @classmethod
    def _evaluate_intake_control(
        cls,
        sak_data: Dict[str, Any],
        deadline_info: Dict[str, Any],
        stage: str
    ) -> Dict[str, Any]:
        """
        Vurderer kommunal mottakskontroll og kompletthet etter SAK10 § 7-1 og PBL § 21-7.
        Spesielt rettet mot nyere saker (0-75 dager / 1-2 måneder gamle):
        - Sjekker om kommunen har overholdt 3-ukers mottakskontrollvinduet
        - Vurderer om søknaden er komplett fra start eller om fristen er stanset med mangelbrev
        - Avdekker forsinkede mangelbrev og krav på gebyravkorting
        """
        dato_str = sak_data.get("dato")
        days_since = cls._calculate_days_in_process(dato_str)
        is_recent = bool(days_since is not None and days_since <= 75)
        
        is_paused = deadline_info.get("is_deadline_paused", False)
        pause_reason = deadline_info.get("deadline_pause_reason")
        is_late_notice = deadline_info.get("is_late_deficiency_notice", False)
        delay_days = deadline_info.get("first_response_delay_days")
        fee_reduction = deadline_info.get("fee_reduction_percentage", 0)
        
        # Samle eventuelle mangelårsaker
        deficiency_details = []
        if pause_reason:
            deficiency_details.append(pause_reason)
            
        # Sjekk om saken er ferdigbehandlet
        if stage in ["Vedtatt / Tillatelse gitt", "Ferdigattest", "Ferdigbehandlet", "Avslått av kommunen"] or deadline_info.get("deadline_status") == "Vedtatt / Avsluttet":
            return {
                "is_recent_case": is_recent,
                "intake_status": "Ferdigbehandlet",
                "intake_status_label": "Ferdigbehandlet av kommunen",
                "intake_deficiency_details": deficiency_details,
                "intake_days_since_submission": days_since,
                "intake_statutory_window_status": "Avsluttet (Vedtak fattet)"
            }
            
        if is_paused:
            if is_late_notice:
                return {
                    "is_recent_case": is_recent,
                    "intake_status": "Forsinket mangelbrev",
                    "intake_status_label": f"Forsinket mangelbrev ({fee_reduction}% gebyravkorting)",
                    "intake_deficiency_details": deficiency_details,
                    "intake_days_since_submission": days_since,
                    "intake_statutory_window_status": f"Mangelbrev sendt etter {delay_days} dager (Lovfrist brutt)"
                }
            else:
                return {
                    "is_recent_case": is_recent,
                    "intake_status": "Mangelbrev utstedt",
                    "intake_status_label": "Frist stanset (Mangelbrev innen 3 uker)",
                    "intake_deficiency_details": deficiency_details,
                    "intake_days_since_submission": days_since,
                    "intake_statutory_window_status": f"Mangelbrev sendt etter {delay_days or 'få'} dager (Lovlig stans)"
                }
                
        # Ingen mangelbrev registrert
        if days_since is not None and days_since <= 21:
            days_left = max(0, 21 - days_since)
            return {
                "is_recent_case": is_recent,
                "intake_status": "Avventer mottakskontroll",
                "intake_status_label": f"Avventer mottakskontroll ({days_left} dager igjen av 3-ukersfristen)",
                "intake_deficiency_details": deficiency_details,
                "intake_days_since_submission": days_since,
                "intake_statutory_window_status": f"Innenfor 3-ukersfristen ({days_since}/21 dager)"
            }
        elif days_since is not None and days_since > 21:
            return {
                "is_recent_case": is_recent,
                "intake_status": "Komplett søknad",
                "intake_status_label": "Komplett søknad (Mottakskontroll passert uten mangler)",
                "intake_deficiency_details": deficiency_details,
                "intake_days_since_submission": days_since,
                "intake_statutory_window_status": "3-ukersfrist utløpt uten mangelbrev (Fristen løper uavbrutt)"
            }
        else:
            return {
                "is_recent_case": is_recent,
                "intake_status": "Under behandling",
                "intake_status_label": "Under behandling",
                "intake_deficiency_details": deficiency_details,
                "intake_days_since_submission": days_since,
                "intake_statutory_window_status": "Løpende behandling"
            }

    @staticmethod
    def _generate_summary(
        title: str,
        category: str,
        subcategory: Optional[str],
        risk_level: str,
        risk_factors: List[str],
        stage: str
    ) -> str:
        """Genererer en kortfattet, profesjonell sammendragstekst på norsk."""
        sub_str = f" ({subcategory})" if subcategory else ""
        text = f"Saken omfatter {category.lower()}{sub_str}. Gjeldende saksstadium er '{stage}' med risikovurdering '{risk_level}'."
        if risk_factors:
            text += f" Nøkkelfaktorer som påvirker vurderingen: {'; '.join(risk_factors[:2])}."
        else:
            text += " Tiltaket fremstår som en ordinær sak uten registrerte vesentlige avvik eller dispensasjonskrav."
        return text

    @staticmethod
    def _generate_recommendation(
        category: str,
        risk_factors: List[str],
        stage: str
    ) -> str:
        """Genererer faglige råd/anbefalinger til saksbehandler eller interessent."""
        if any("Ulovlighet" in rf for rf in risk_factors):
            return "Kritisk oppfølging påkrevet. Verifiser at pålegg overholdes og vurder eventuell tvangsmulkt ved fristoversittelse."
        if any("dispensasjon" in rf.lower() for rf in risk_factors):
            return "Krever særskilt dispensasjonsvurdering etter pbl kapittel 19. Kontroller at fordelene klart overstiger ulempene og at naboer er varslet spesifikt."
        if any("strandsonen" in rf.lower() for rf in risk_factors):
            return "Tiltaket berører sårbart areal/strandsone. Vurder dispensasjonsforbud og innhent uttalelse fra regionale miljømyndigheter."
        if stage == "Forhåndskonferanse":
            return "Gjennomgå planstatus, utnyttelsesgrad og tilknytningsplikt for vann/avløp før formell ett-trinns søknad innsendes."
        return "Ordinær saksgang etter plan- og bygningsloven § 20-1. Påse komplett ansvarsrett og nabovarsling."

    @staticmethod
    def extract_companies(raw_sak: Dict[str, Any], dokumenter: List[Dokument]) -> Tuple[Optional[str], List[str]]:
        """
        Ekstraherer utførende foretak, arkitekter, entreprenører og søkere fra dokumenter og sak.
        """
        companies_set = set()
        all_senders = []

        # 1. Hent avsendere fra dokumenter
        for d in dokumenter:
            for sender in d.fra:
                if sender and isinstance(sender, str):
                    s_clean = sender.strip()
                    if s_clean:
                        all_senders.append(s_clean)
                        # Sjekk om det er et firma eller foretak
                        if ByggesakEvaluator._is_company_name(s_clean):
                            companies_set.add(s_clean)

        # 2. Sjekk også 'fra' i rådokumenter eller saksbeskrivelse
        for d in raw_sak.get("dokumenter", []):
            for s in d.get("fra", []):
                if s and isinstance(s, str) and ByggesakEvaluator._is_company_name(s.strip()):
                    companies_set.add(s.strip())
            # Sjekk tittel på dokumenter for firmanavn på slutten (f.eks. "... - Firma AS")
            doc_title = d.get("tittel", "") if isinstance(d, dict) else getattr(d, "tittel", "")
            if " - " in doc_title:
                candidate = doc_title.split(" - ")[-1].strip()
                if ByggesakEvaluator._is_company_name(candidate) and len(candidate) > 3:
                    companies_set.add(candidate)
            # Sjekk "fra [Firma AS]" i tittel
            fra_match = re.search(r'\bfra\s+([A-ZÆØÅ][A-Za-zæøå0-9\s&+\.\-]+?(?:\s+AS|\s+A/S|\s+ANS|\s+DA|\s+ENK|\s+Arkitekter|\s+Bygg|\s+Eiendom)?)(?:\s+på\s+vegne|\s*$|\s*-)', doc_title)
            if fra_match:
                candidate = fra_match.group(1).strip()
                if ByggesakEvaluator._is_company_name(candidate):
                    companies_set.add(candidate)

        # 3. Sjekk sakstittel og undertittel
        for t in [raw_sak.get("tittel", ""), raw_sak.get("undertittel", "")]:
            if not t:
                continue
            if " - " in t:
                candidate = t.split(" - ")[-1].strip()
                if ByggesakEvaluator._is_company_name(candidate) and len(candidate) > 3:
                    companies_set.add(candidate)
            fra_match = re.search(r'\bfra\s+([A-ZÆØÅ][A-Za-zæøå0-9\s&+\.\-]+?(?:\s+AS|\s+A/S|\s+ANS|\s+DA|\s+ENK|\s+Arkitekter|\s+Bygg|\s+Eiendom)?)(?:\s+på\s+vegne|\s*$|\s*-)', t)
            if fra_match:
                candidate = fra_match.group(1).strip()
                if ByggesakEvaluator._is_company_name(candidate):
                    companies_set.add(candidate)

        companies_list = sorted(list(companies_set))
        
        # Bestem primærfirma / hovedansvarlig
        primary_company = None
        if companies_list:
            primary_company = companies_list[0]
        elif all_senders:
            primary_company = all_senders[0]

        return primary_company, companies_list

    @staticmethod
    def _is_company_name(name: str) -> bool:
        """Sjekker om en avsenderstreng representerer et firma, foretak eller profesjonell aktør."""
        name_lower = name.lower().strip()
        
        # Ignorer generiske byggetiltaksord
        generic_terms = [
            "nybygg", "enebolig", "fritidsbolig", "tilbygg", "påbygg", "garasje", "bruksendring",
            "fasadeendring", "redskapsbod", "uthus", "riving", "sprinkleranlegg", "støttemur",
            "forhåndskonferanse", "dispensasjon", "rammetillatelse", "søknad", "klage"
        ]
        if any(name_lower == g or name_lower.startswith(g + " ") for g in generic_terms):
            # Med mindre det eksplisitt inneholder AS / Byggmester / Arkitekt etc
            if not any(k in name_lower for k in [" as", " a/s", "arkitekt", "byggmester", "entreprenør"]):
                return False
        
        # Kjente selskapsformer og nøkkelord
        company_indicators = [
            r'\bas\b', r'\ba/s\b', r'\bans\b', r'\bda\b', r'\benk\b', r'\bsf\b', r'\bhf\b',
            'arkitekt', 'arkitektur', 'byggmester', 'tømrer', 'entreprenør',
            'ingeniør', 'konsult', 'consulting', 'advokat', 'geodesi', 'takst'
        ]
        
        for pattern in company_indicators:
            if re.search(pattern, name_lower):
                return True
                
        # Sammensatte firmanavn med bygg/eiendom/hus
        if len(name.split()) >= 2:
            if any(w in name_lower for w in ["bygg", "eiendom", "hus", "prosjekt", "miljø", "invest"]):
                if not any(g in name_lower for g in ["ny enebolig", "nytt bolighus", "nybygg"]):
                    return True

        return False

    @classmethod
    def create_byggesak_model(cls, raw_sak: Dict[str, Any]) -> Byggesak:
        """Konverterer rå API-data fra Tønsberg til en fullverdig Byggesak med evaluering."""
        title = raw_sak.get("tittel", "")
        undertittel = raw_sak.get("undertittel", "")
        identifikator = raw_sak.get("identifikator", "")
        saksnummer = raw_sak.get("saksnummer", "")
        dato = raw_sak.get("dato", "")
        saksbehandler = raw_sak.get("saksbehandler")
        
        # Parse adresse og matrikkel
        address_info = cls.parse_address_and_matrikkel(title, undertittel)

        # Parse dokumenter
        dokumenter: List[Dokument] = []
        for d in raw_sak.get("dokumenter", []):
            dokumenter.append(Dokument(
                identifikator=d.get("identifikator", ""),
                friendly_id=d.get("friendlyId"),
                tittel=d.get("tittel", ""),
                undertittel=d.get("undertittel", ""),
                fra=d.get("fra", []) if isinstance(d.get("fra"), list) else [],
                til=d.get("til", []) if isinstance(d.get("til"), list) else [],
                dato=d.get("dato"),
                saksbehandler=d.get("saksbehandler"),
                ansvarlig_enhet=d.get("ansvarligEnhet"),
                antall_vedlegg=d.get("antallVedlegg", 0),
                synlighet=d.get("synlighet", 1),
                paragraf_id=d.get("paragrafID", "")
            ))

    @staticmethod
    def extract_official_decision(raw_sak: Dict[str, Any], dokumenter: List[Dokument]) -> Dict[str, Any]:
        """
        Analyserer journalposter for å finne om det foreligger et offisielt enkeltvedtak fra Tønsberg kommune.
        Skiller strengt mellom søkers innsendte søknader og kommunens formelle godkjenninger/avslag/avvisninger.
        Sjekker fra nyeste til eldste dokument for å hente den gjeldende statusen.
        """
        has_decision = False
        decision_type = "Ikke avgjort (Under behandling)"
        decision_doc_title = None
        decision_date = None

        # Sjekk fra nyeste til eldste dokument for å fange opp siste formelle saksbehandlerutfall
        for d in reversed(dokumenter):
            t = d.tittel.lower()
            dato = d.dato

            # 1. Delvis innvilgelse / Avslag på dispensasjon
            if ("avslag på dispensasjon" in t or "avslag dispensasjon" in t or "delvis avslag" in t or "rammetillatelse og avslag" in t or "tillatelse og avslag" in t):
                return {
                    "has_official_decision": True,
                    "official_decision_type": "Delvis innvilget / Avslag på dispensasjon",
                    "decision_document_title": d.tittel,
                    "decision_date": dato
                }

            # 2. Formelt avslag på søknad
            if ("vedtak om avslag" in t or "avslag på søknad" in t or "avslått" in t or "søknaden avslås" in t or "avslag" in t) and "varsel" not in t and "klage på avslag" not in t and not t.startswith("søknad"):
                return {
                    "has_official_decision": True,
                    "official_decision_type": "Avslått av kommunen",
                    "decision_document_title": d.tittel,
                    "decision_date": dato
                }

            # 3. Formell avvisning av søknad (f.eks. ufullstendig eller manglende rettslig interesse)
            if ("avvisning av søknad" in t or "avvising av søknad" in t or "søknaden avvises" in t or "avvist søknad" in t) and "varsel" not in t:
                return {
                    "has_official_decision": True,
                    "official_decision_type": "Avvist av kommunen",
                    "decision_document_title": d.tittel,
                    "decision_date": dato
                }

            # 4. Formelt varsel om avslag / avvisning
            if ("varsel om avslag" in t or "varsel om avvisning" in t or "varsel om mulig avslag" in t or "varsel om avvising" in t):
                return {
                    "has_official_decision": False,
                    "official_decision_type": "Varsel om avslag",
                    "decision_document_title": d.tittel,
                    "decision_date": dato
                }

            # 5. Søknad trukket av søker (ofte etter varsel om avslag)
            if "trukket søknad" in t or "bekrefter trukket" in t or "søknad trekkes" in t:
                return {
                    "has_official_decision": False,
                    "official_decision_type": "Trukket av søker",
                    "decision_document_title": d.tittel,
                    "decision_date": dato
                }

            # 6. Ferdigattest / midlertidig brukstillatelse
            if ("ferdigattest" in t or "brukstillatelse" in t) and "søknad" not in t and "anmodning" not in t:
                return {
                    "has_official_decision": True,
                    "official_decision_type": "Ferdigattest utstedt",
                    "decision_document_title": d.tittel,
                    "decision_date": dato
                }

            # 7. Igangsettingstillatelse
            if "igangsettingstillatelse" in t and "søknad" not in t and "anmodning" not in t:
                return {
                    "has_official_decision": True,
                    "official_decision_type": "Innvilget / Igangsettingstillatelse gitt",
                    "decision_document_title": d.tittel,
                    "decision_date": dato
                }

            # 8. Rammetillatelse eller ett-trinnstillatelse
            if ("rammetillatelse" in t or "ett-trinnstillatelse" in t or "tillatelse i ett trinn" in t or "tillatelse til tiltak" in t or "tillatelse § 20-3" in t or "tillatelse § 20-4" in t) and "søknad" not in t and "anmodning" not in t:
                return {
                    "has_official_decision": True,
                    "official_decision_type": "Innvilget / Tillatelse gitt",
                    "decision_document_title": d.tittel,
                    "decision_date": dato
                }

            # 9. Delegert vedtak / godkjenning
            if ("delegert vedtak" in t or "vedtak om tillatelse" in t or "svar på søknad - godkjent" in t or "godkjent søknad" in t) and "søknad" not in t:
                return {
                    "has_official_decision": True,
                    "official_decision_type": "Innvilget / Delegert vedtak",
                    "decision_document_title": d.tittel,
                    "decision_date": dato
                }

            # 10. Pålegg / stansingsvedtak
            if "pålegg om stans" in t or "stansingsvedtak" in t or "vedtak om pålegg" in t:
                return {
                    "has_official_decision": True,
                    "official_decision_type": "Pålegg / Stansingsvedtak",
                    "decision_document_title": d.tittel,
                    "decision_date": dato
                }

        return {
            "has_official_decision": has_decision,
            "official_decision_type": decision_type,
            "decision_document_title": decision_doc_title,
            "decision_date": decision_date
        }

    @classmethod
    def create_byggesak_model(cls, raw_sak: Dict[str, Any]) -> Byggesak:
        """Konverterer rå API-data fra Tønsberg til en fullverdig Byggesak med evaluering."""
        title = raw_sak.get("tittel", "")
        undertittel = raw_sak.get("undertittel", "")
        identifikator = raw_sak.get("identifikator", "")
        saksnummer = raw_sak.get("saksnummer", "")
        dato = raw_sak.get("dato", "")
        saksbehandler = raw_sak.get("saksbehandler")
        
        # Parse adresse og matrikkel
        address_info = cls.parse_address_and_matrikkel(title, undertittel)

        # Parse dokumenter
        dokumenter: List[Dokument] = []
        for d in raw_sak.get("dokumenter", []):
            dokumenter.append(Dokument(
                identifikator=d.get("identifikator", ""),
                friendly_id=d.get("friendlyId"),
                tittel=d.get("tittel", ""),
                undertittel=d.get("undertittel", ""),
                fra=d.get("fra", []) if isinstance(d.get("fra"), list) else [],
                til=d.get("til", []) if isinstance(d.get("til"), list) else [],
                dato=d.get("dato"),
                saksbehandler=d.get("saksbehandler"),
                ansvarlig_enhet=d.get("ansvarligEnhet"),
                antall_vedlegg=d.get("antallVedlegg", 0),
                synlighet=d.get("synlighet", 1),
                paragraf_id=d.get("paragrafID", "")
            ))

        # Ekstraher firmaer og utførende foretak
        primary_company, companies = cls.extract_companies(raw_sak, dokumenter)

        # Ekstraher offisielt kommunalt vedtak
        decision_info = cls.extract_official_decision(raw_sak, dokumenter)

        # Kjør evaluering
        evaluation = cls.evaluate_case(raw_sak)

        status_obj = raw_sak.get("status", {})
        status_tittel = status_obj.get("tittel", "Under behandling") if isinstance(status_obj, dict) else "Under behandling"
        er_ferdig = bool(status_obj.get("erFerdig", False)) or (status_tittel in ["Avsluttet", "Ferdigbehandlet", "Arkivert"]) or (decision_info.get("official_decision_type") == "Ferdigattest utstedt") or (evaluation is not None and evaluation.stage in ["Ferdigbehandlet", "Ferdigattest"])

        innsyn_url = f"https://www.tonsberg.kommune.no/tjenester/innsyn/sok-i-postlister-saker-og-dokumenter/#/details/{identifikator}"

        return Byggesak(
            identifikator=identifikator,
            saksnummer=saksnummer,
            tittel=title,
            undertittel=undertittel,
            sakstype=raw_sak.get("sakstype", "Arkivsak"),
            saks_beskrivelse=raw_sak.get("saksBeskrivelse", "Byggesak"),
            dato=dato,
            saksbehandler=saksbehandler,
            status_tittel=status_tittel,
            er_ferdig=er_ferdig,
            innsyn_url=innsyn_url,
            official_status=status_tittel,
            has_official_decision=decision_info["has_official_decision"],
            official_decision_type=decision_info["official_decision_type"],
            decision_document_title=decision_info["decision_document_title"],
            decision_date=decision_info["decision_date"],
            complete_application_date=evaluation.complete_application_date if evaluation else None,
            is_deadline_paused=evaluation.is_deadline_paused if evaluation else False,
            is_late_deficiency_notice=evaluation.is_late_deficiency_notice if evaluation else False,
            fee_reduction_percentage=evaluation.fee_reduction_percentage if evaluation else 0,
            is_recent_case=evaluation.is_recent_case if evaluation else False,
            intake_status=evaluation.intake_status if evaluation else "Ikke vurdert",
            intake_days_since_submission=evaluation.intake_days_since_submission if evaluation else None,
            primary_company=primary_company,
            companies=companies,
            address_info=address_info,
            evaluation=evaluation,
            dokumenter=dokumenter
        )

    @classmethod
    def pre_evaluate_application(
        cls,
        tiltak_tittel: str,
        address_raw: Optional[str] = None,
        beskrivelse: Optional[str] = None,
        extracted_file_text: Optional[str] = None,
        uploaded_filenames: Optional[List[str]] = None,
        tomteareal_m2: Optional[float] = None,
        bya_eksisterende_m2: Optional[float] = None,
        bya_tiltak_m2: Optional[float] = None,
        avstand_nabogrense_m: Optional[float] = None,
        har_nabosamtykke: bool = False,
        har_avkjorsel_endring: bool = False,
        er_i_strandsone: bool = False,
        er_i_lnfr: bool = False,
        har_dispensasjonssoknad: bool = False,
        har_nabomerknader: bool = False,
        har_situasjonsplan: bool = False,
        har_fasadetegninger: bool = False,
        har_snittegninger: bool = False,
        har_ansvarsretter: bool = False,
    ) -> PreEvaluationReport:
        """
        Utfører en omfattende forhåndsevaluering av en ny byggesak før den sendes inn til kommunen.
        Beregner godkjenningssannsynlighet, kvalitetsscore, kompleksitet, lovfrister og
        gir konkrete, prioriterte forbedringstiltak basert på plan- og bygningsloven og KPA Tønsberg.
        """
        uploaded_filenames = uploaded_filenames or []
        beskrivelse_text = beskrivelse or ""
        file_text = extracted_file_text or ""
        full_text = f"{tiltak_tittel} {address_raw or ''} {beskrivelse_text} {file_text} {' '.join(uploaded_filenames)}".lower()

        # 1. Parse adresse og matrikkel
        addr_info = cls.parse_address_and_matrikkel(f"{address_raw or ''} {tiltak_tittel}")
        addr_str = addr_info.raw_address if addr_info.raw_address else (address_raw or "Ikke spesifisert")
        matrikkel_str = f"Gnr {addr_info.gnr} / Bnr {addr_info.bnr}" if addr_info.gnr else None

        # 2. Kategoriser tiltaket
        category, subcategory = cls._categorize(full_text, tiltak_tittel)

        # 3. Automatisk deteksjon fra tekst / filnavn dersom ikke eksplisitt angitt
        if not er_i_strandsone:
            er_i_strandsone = any(w in full_text for w in ["strandsone", "100-metersbelte", "100 metersbelte", "sjøkant", "vannkant", "strandkanten"])
        if not er_i_lnfr:
            er_i_lnfr = any(w in full_text for w in ["lnf", "lnfr", "landbruksområde", "spredt bolig", "landbruk"])
        if not har_avkjorsel_endring:
            har_avkjorsel_endring = any(w in full_text for w in ["avkjørsel", "avkjørselstillatelse", "ny avkjørsel", "flytte avkjørsel", "frisikt", "vegloven"])
        if not har_dispensasjonssoknad:
            har_dispensasjonssoknad = any(w in full_text for w in ["dispensasjonssøknad", "søknad om dispensasjon", "pbl § 19-2", "dispensasjon etter pbl"])
        if not har_situasjonsplan:
            har_situasjonsplan = any(w in full_text for w in ["situasjonsplan", "situasjonskart"]) or any("sit" in f.lower() or "kart" in f.lower() for f in uploaded_filenames)
        if not har_fasadetegninger:
            har_fasadetegninger = any(w in full_text for w in ["fasade", "fasader", "fasadetegning"]) or any("fasade" in f.lower() for f in uploaded_filenames)
        if not har_snittegninger:
            har_snittegninger = any(w in full_text for w in ["snitt", "snittegning", "terrengsnitt"]) or any("snitt" in f.lower() for f in uploaded_filenames)
        if not har_ansvarsretter:
            har_ansvarsretter = any(w in full_text for w in ["ansvarsrett", "gjennomføringsplan", "ansvarlig søker", "prosjekterende", "utførende"])

        # 4. BYA- og Tomteutnyttelsesberegning (TEK17 Kap. 5 / KPA Tønsberg)
        bya_summary = None
        bya_overskridelse = 0.0
        bya_prosent = 0.0
        kpa_limit = 25.0  # Standard KPA Tønsberg boligområde

        if tomteareal_m2 and tomteareal_m2 > 0:
            tomt = float(tomteareal_m2)
            eks_bya = float(bya_eksisterende_m2 or 0.0)
            tiltak_bya = float(bya_tiltak_m2 or 0.0)
            
            # Parkeringskrav i TEK17 / KPA: 18m² per biloppstillingsplass hvis ikke integrert i tiltaket
            req_parking_bya = 0.0
            if category in ["Nybygg", "Bruksendring"] and tiltak_bya < 40:
                req_parking_bya = 36.0  # 2 plasser for ny enebolig
            elif category == "Tilbygg & Påbygg" and eks_bya > 0 and tiltak_bya > 30:
                req_parking_bya = 18.0  # 1 plass

            tot_bya = eks_bya + tiltak_bya + req_parking_bya
            bya_prosent = round((tot_bya / tomt) * 100, 1)
            bya_overskridelse = max(0.0, round(bya_prosent - kpa_limit, 1))

            bya_summary = {
                "tomteareal_m2": tomt,
                "eksisterende_bya_m2": eks_bya,
                "tiltak_bya_m2": tiltak_bya,
                "parkering_tillegg_bya_m2": req_parking_bya,
                "total_bya_m2": tot_bya,
                "beregnet_bya_prosent": bya_prosent,
                "kpa_tillatt_bya_prosent": kpa_limit,
                "overskridelse_prosentpoeng": bya_overskridelse,
                "er_innenfor_kpa": bya_overskridelse == 0.0,
                "status_tekst": f"Overskridelse (+{bya_overskridelse} %-poeng)" if bya_overskridelse > 0 else "Konform (Innenfor tillatt %-BYA)"
            }

        # 5. Evaluer de 8 lovmessige sjekkpunktene (PBL-rammeverket)
        legal_checkpoints: List[LegalCheckpoint] = []
        improvements: List[ImprovementAction] = []
        missing_attachments: List[str] = []
        strengths: List[str] = []

        # Sjekkpunkt 1: Strandsonen (PBL § 1-8)
        if er_i_strandsone:
            if har_dispensasjonssoknad:
                cp1_status = "Krever avklaring / Mangel"
                cp1_risk = "Høy"
                cp1_findings = "Tiltaket ligger i 100-metersbeltet langs sjøen. Dispensasjon er omsøkt, men utløser obligatorisk regional høring (Statsforvalteren og Vestfold Fylkeskommune)."
                cp1_reqs = "Dokumenter at allmenne ferdsels- og naturinteresser ikke forringes, og at tiltaket har 'klart større fordeler enn ulemper' (pbl § 19-2)."
                improvements.append(ImprovementAction(
                    priority="Høy",
                    category="Strandsone (§ 1-8)",
                    title="Forsterk strandsonebegrunnelsen",
                    description="Statsforvalteren har streng innsigelsespraksis i strandsonen i Vestfold.",
                    action_required="Legg ved særskilt redegjørelse for at tiltaket ikke privatiserer strandsonen eller hindrer allmennhetens ferdsel."
                ))
            else:
                cp1_status = "Kritisk planavvik / Avslagsrisiko"
                cp1_risk = "Kritisk"
                cp1_findings = "Tiltaket er plassert i 100-metersbeltet langs sjøen (pbl § 1-8) uten vedlagt dispensasjonssøknad. Automatisk avslagsgrunn!"
                cp1_reqs = "Det må utarbeides og vedlegges en formell dispensasjonssøknad etter pbl kapittel 19 før innsending."
                improvements.append(ImprovementAction(
                    priority="Høy",
                    category="Strandsone (§ 1-8)",
                    title="Obligatorisk dispensasjonssøknad mangler",
                    description="Tiltak i strandsonen er underlagt generelt byggeforbud etter pbl § 1-8.",
                    action_required="Send inn begrunnet søknad om dispensasjon fra pbl § 1-8 som nabovarsles særskilt."
                ))
        else:
            cp1_status = "Ivaretatt / Konform"
            cp1_risk = "Lav"
            cp1_findings = "Tiltaket ligger utenfor 100-metersbeltet langs sjøen. Ingen konflikt med pbl § 1-8."
            cp1_reqs = "Ingen særvilkår for strandsone."
            strengths.append("Plassert utenfor strandsone og byggeforbudssoner (§ 1-8).")

        legal_checkpoints.append(LegalCheckpoint(
            id="pbl_1_8",
            title="Strandsonen og 100-metersbeltet",
            legal_reference="Plan- og bygningsloven § 1-8 / SPR",
            status=cp1_status,
            risk_level=cp1_risk,
            findings=cp1_findings,
            requirements_to_pass=cp1_reqs
        ))

        # Sjekkpunkt 2: Arealplan og Grad av utnytting (%-BYA)
        if bya_summary and not bya_summary["er_innenfor_kpa"]:
            if har_dispensasjonssoknad:
                cp2_status = "Krever avklaring / Mangel"
                cp2_risk = "Høy"
                cp2_findings = f"Beregnet %-BYA er {bya_prosent} %, som overskrider tillatt ramme ({kpa_limit} %) med {bya_overskridelse} %-poeng. Dispensasjon er omsøkt."
                cp2_reqs = f"Begrunn overskridelsen på {bya_overskridelse} %-poeng i henhold til de to kumulative vilkårene i pbl § 19-2."
                improvements.append(ImprovementAction(
                    priority="Høy",
                    category="Arealplan & BYA",
                    title="Vurder å redusere tiltakets fotavtrykk",
                    description=f"Tomten overskrider KPA-grensen med {bya_overskridelse} %-poeng. Tønsberg kommune er restriktive til overutnyttelse.",
                    action_required=f"Reduser tiltakets bebygde areal med ca. {round(bya_overskridelse * (tomteareal_m2 or 500) / 100, 1)} m² for å unngå dispensasjonskrav."
                ))
            else:
                cp2_status = "Kritisk planavvik / Avslagsrisiko"
                cp2_risk = "Kritisk"
                cp2_findings = f"Beregnet %-BYA ({bya_prosent} %) overskrider kommuneplanens arealdel ({kpa_limit} %) med {bya_overskridelse} %-poeng uten dispensasjonssøknad."
                cp2_reqs = "Reduser fotavtrykket eller legg ved dispensasjonssøknad etter pbl § 19-2 for overskridelse av utnyttingsgrad."
                improvements.append(ImprovementAction(
                    priority="Høy",
                    category="Arealplan & BYA",
                    title="Ulovlig overutnyttelse av tomt",
                    description="Søknaden overskrider tillatt %-BYA i strid med kommuneplanens arealdel (KPA).",
                    action_required="Enten reduser arealet slik at %-BYA er under 25 %, eller søk dispensasjon fra KPA."
                ))
        elif bya_summary:
            cp2_status = "Ivaretatt / Konform"
            cp2_risk = "Lav"
            cp2_findings = f"Beregnet %-BYA er {bya_prosent} %, som er fullt ut i samsvar med tillatt utnyttingsgrad ({kpa_limit} %)."
            cp2_reqs = "Overhold fotavtrykket som vist i situasjonsplanen."
            strengths.append(f"Tomteutnyttelse (%-BYA = {bya_prosent} %) er innenfor KPA Tønsbergs krav på {kpa_limit} %.")
        else:
            cp2_status = "Krever avklaring / Mangel"
            cp2_risk = "Moderat"
            cp2_findings = "Tomtestørrelse eller bebygd areal er ikke oppgitt. Utnyttelsesgrad (%-BYA) kan ikke kontrolleres."
            cp2_reqs = "Legg inn tomtens areal og eksisterende/nytt bebygd areal for automatisk kontroll."
            improvements.append(ImprovementAction(
                priority="Medium",
                category="Arealplan & BYA",
                title="Dokumenter tomtens arealregnskap",
                description="Kommunen krever at %-BYA er nøyaktig utregnet på situasjonsplanen.",
                action_required="Oppgi tomtens areal og bebygd areal (inkl. parkering) i søknadsskjemaet."
            ))

        legal_checkpoints.append(LegalCheckpoint(
            id="pbl_bya",
            title="Arealplan og utnyttingsgrad (%-BYA)",
            legal_reference="PBL § 11-7 / TEK17 kap. 5 / KPA Tønsberg",
            status=cp2_status,
            risk_level=cp2_risk,
            findings=cp2_findings,
            requirements_to_pass=cp2_reqs
        ))

        # Sjekkpunkt 3: Plassering og Nabogrenser (PBL § 29-4)
        if avstand_nabogrense_m is not None and avstand_nabogrense_m < 4.0:
            if har_nabosamtykke:
                cp3_status = "Ivaretatt / Konform"
                cp3_risk = "Lav"
                cp3_findings = f"Avstand til nabogrense er {avstand_nabogrense_m} m (< 4m), men skriftlig nabosamtykke foreligger (pbl § 29-4 tredje ledd bokstav a)."
                cp3_reqs = "Legg ved det signerte nabosamtykket som vedlegg i søknaden."
                strengths.append("Skriftlig nabosamtykke foreligger for plassering nærmere enn 4 meter (§ 29-4).")
            elif category == "Garasje & Uthus" and avstand_nabogrense_m >= 1.0 and (bya_tiltak_m2 or 0) <= 50.0:
                cp3_status = "Ivaretatt / Konform"
                cp3_risk = "Lav"
                cp3_findings = f"Frittliggende garasje under 50 m² plassert {avstand_nabogrense_m} m fra nabogrense (SAK10 § 4-1 / pbl § 29-4 tredje ledd bokstav b)."
                cp3_reqs = "Sikre at mønehøyde ikke overstiger 4,0 meter og gesimshøyde 3,0 meter."
                strengths.append("Garasjen oppfyller 1-metersregelen etter SAK10 § 4-1 for småbygg.")
            elif har_dispensasjonssoknad:
                cp3_status = "Krever avklaring / Mangel"
                cp3_risk = "Høy"
                cp3_findings = f"Avstand til nabogrense ({avstand_nabogrense_m} m) krever dispensasjon fra 4-metersregelen. Dispensasjon er omsøkt."
                cp3_reqs = "Begrunn hvorfor tiltakets plassering ikke medfører vesentlig ulempe for naboen (lys, innsyn, brannsikring)."
                improvements.append(ImprovementAction(
                    priority="Høy",
                    category="Nabogrense (§ 29-4)",
                    title="Innhent skriftlig nabosamtykke for å unngå dispensasjon",
                    description="Dersom naboen signerer nabosamtykke, slipper du dispensasjonsbehandling etter § 19-2 og 12-ukers frist.",
                    action_required="Be naboen signere standarderklæring om samtykke til nær plassering etter pbl § 29-4."
                ))
            else:
                cp3_status = "Kritisk planavvik / Avslagsrisiko"
                cp3_risk = "Kritisk"
                cp3_findings = f"Plassert {avstand_nabogrense_m} m fra nabogrense uten nabosamtykke eller dispensasjonssøknad. I strid med pbl § 29-4!"
                cp3_reqs = "Innhent skriftlig samtykke fra berørt nabo, eller søk dispensasjon fra pbl § 29-4."
                improvements.append(ImprovementAction(
                    priority="Høy",
                    category="Nabogrense (§ 29-4)",
                    title="Mangler nabosamtykke eller dispensasjon fra avstandskrav",
                    description="Byggverk kan ikke plasseres nærmere enn 4 meter uten samtykke eller dispensasjon.",
                    action_required="Innhent signert nabosamtykke fra berørt naboeiendom."
                ))
        else:
            cp3_status = "Ivaretatt / Konform"
            cp3_risk = "Lav"
            cp3_findings = "Plassering overholder lovens 4-meterskrav til nabogrense (pbl § 29-4 andre ledd)."
            cp3_reqs = "Påløper ingen avstandskrav."
            strengths.append("Overholder lovfestet avstandskrav på minimum 4,0 meter til nabogrenser (§ 29-4).")

        legal_checkpoints.append(LegalCheckpoint(
            id="pbl_29_4",
            title="Plassering og avstand til nabogrense",
            legal_reference="Plan- og bygningsloven § 29-4 / SAK10 § 4-1",
            status=cp3_status,
            risk_level=cp3_risk,
            findings=cp3_findings,
            requirements_to_pass=cp3_reqs
        ))

        # Sjekkpunkt 4: Infrastruktur og Avkjørsel (PBL § 27-4 / Vegloven § 40)
        if har_avkjorsel_endring:
            cp4_status = "Krever avklaring / Mangel"
            cp4_risk = "Moderat"
            cp4_findings = "Endring eller etablering av avkjørsel krever godkjenning fra vegmyndigheten samt inntegnet frisikttrekant (pbl § 27-4)."
            cp4_reqs = "Tegn inn frisiktsone (4 x 20 meter ved 30-50 km/t) på situasjonsplanen og vis snuplass på egen tomt."
            improvements.append(ImprovementAction(
                priority="Medium",
                category="Vei & Avkjørsel (§ 27-4)",
                title="Tegn inn frisikttrekant og snuplass på situasjonsplanen",
                description="Kommunen og vegmyndigheten avslår eller stanser søknader som medfører rygging ut på offentlig gate.",
                action_required="Vis frisiktsone (4x20m) og biloppstillingsplass/snuareal på situasjonsplanen."
            ))
        else:
            cp4_status = "Ivaretatt / Konform"
            cp4_risk = "Lav"
            cp4_findings = "Ingen endring av avkjørsel eller vegtilknytning registrert. Adkomst er sikret (pbl § 27-4)."
            cp4_reqs = "Ingen særskilt avkjørselsbehandling nødvendig."
            strengths.append("Ingen konflikt med vegtilknytning eller avkjørselsmyndighet (§ 27-4).")

        legal_checkpoints.append(LegalCheckpoint(
            id="pbl_27_4",
            title="Infrastruktur, adkomst og avkjørsel",
            legal_reference="Plan- og bygningsloven § 27-4 / Vegloven § 40",
            status=cp4_status,
            risk_level=cp4_risk,
            findings=cp4_findings,
            requirements_to_pass=cp4_reqs
        ))

        # Sjekkpunkt 5: Naturfarer og byggegrunn (PBL § 28-1)
        legal_checkpoints.append(LegalCheckpoint(
            id="pbl_28_1",
            title="Naturfarer, geoteknikk og byggegrunn",
            legal_reference="Plan- og bygningsloven § 28-1 / TEK17 kap. 7",
            status="Ivaretatt / Konform",
            risk_level="Lav",
            findings="Ingen kjente akutte faresoner registrert på eiendommen.",
            requirements_to_pass="Sikre tilstrekkelig overvannshåndtering og radonforebygging etter TEK17."
        ))

        # Sjekkpunkt 6: Visuell kvalitet og estetikk (PBL § 29-2)
        legal_checkpoints.append(LegalCheckpoint(
            id="pbl_29_2",
            title="Visuelle kvaliteter og estetikk",
            legal_reference="Plan- og bygningsloven § 29-2 / SAK10",
            status="Ivaretatt / Konform",
            risk_level="Lav",
            findings="Tiltaket forutsettes tilpasset eksisterende bygningsmiljø og strøkets karakter.",
            requirements_to_pass="Vis fargevalg og materialbruk på fasadetegningene."
        ))

        # Sjekkpunkt 7: Dispensasjonsvurdering (PBL Kapittel 19)
        disp_needed = er_i_strandsone or (bya_overskridelse > 0) or (avstand_nabogrense_m is not None and avstand_nabogrense_m < 4.0 and not har_nabosamtykke)
        if disp_needed:
            if har_dispensasjonssoknad:
                cp7_status = "Krever avklaring / Mangel"
                cp7_risk = "Moderat"
                cp7_findings = "Dispensasjon er omsøkt. Kommunen må foreta en skjønnsmessig vurdering av lovvilkårene i pbl § 19-2."
                cp7_reqs = "Sørg for at begrunnelsen vektlegger at fordelene er klart større enn ulempene for allmennheten."
            else:
                cp7_status = "Kritisk planavvik / Avslagsrisiko"
                cp7_risk = "Kritisk"
                cp7_findings = "Tiltaket krever dispensasjon fra plan eller lovbestemmelser, men formell dispensasjonssøknad mangler."
                cp7_reqs = "Utarbeid en særskilt dispensasjonssøknad og send ut særskilt nabovarsel før innsending."
        else:
            cp7_status = "Ivaretatt / Konform"
            cp7_risk = "Lav"
            cp7_findings = "Tiltaket er i tråd med gjeldende plan- og lovverk. Ingen dispensasjonsbehandling påkrevd."
            cp7_reqs = "Ingen dispensasjonssøknad nødvendig."
            strengths.append("Ingen dispensasjonskrav etter pbl kapittel 19.")

        legal_checkpoints.append(LegalCheckpoint(
            id="pbl_19_2",
            title="Dispensasjonsvilkår og begrunnelse",
            legal_reference="Plan- og bygningsloven §§ 19-1 og 19-2",
            status=cp7_status,
            risk_level=cp7_risk,
            findings=cp7_findings,
            requirements_to_pass=cp7_reqs
        ))

        # Sjekkpunkt 8: Saksbehandlingskrav & Vedleggskontroll (PBL § 21-7 / SAK10)
        if not har_situasjonsplan:
            missing_attachments.append("Situasjonsplan i målestokk 1:500 på oppdatert kartgrunnlag med inntegnede avstander og mål.")
        if not har_fasadetegninger:
            missing_attachments.append("Fasadetegninger (1:100) av alle berørte fasader med terrenglinjer (eksisterende og nytt).")
        if not har_snittegninger:
            missing_attachments.append("Snittegning (1:100) med gesims- og mønehøyde over gjennomsnittlig planert terreng.")
        if har_nabomerknader:
            missing_attachments.append("Tilsvar til innkomne nabomerknader samt redegjørelse for eventuelle tilpasninger.")
        if har_avkjorsel_endring:
            missing_attachments.append("Avkjørselsplan med inntegnet frisiktsone (4x20m) og godkjenning fra vegmyndigheten.")

        if missing_attachments:
            cp8_status = "Krever avklaring / Mangel"
            cp8_risk = "Moderat"
            cp8_findings = f"Det mangler {len(missing_attachments)} sentrale vedlegg. Dette vil medføre at kommunen stanser fristen med mangelbrev."
            cp8_reqs = "Vedlegg alle påkrevde tegninger og dokumenter før innsending."
            improvements.append(ImprovementAction(
                priority="Medium",
                category="Vedlegg & Dokumentasjon",
                title=f"Kompletter søknaden med {len(missing_attachments)} manglende vedlegg",
                description="Ufullstendige søknader forårsaker forsinkelser og nullstiller kommunens saksbehandlingsfrist.",
                action_required="Last opp/legg ved alle manglende tegninger og dokumenter før innsending."
            ))
        else:
            cp8_status = "Ivaretatt / Konform"
            cp8_risk = "Lav"
            cp8_findings = "Alle grunnleggende vedlegg og tegninger er identifisert og ivaretatt."
            cp8_reqs = "Kontroller at tegningene er i riktig målestokk (1:500 / 1:100) ved innsending."
            strengths.append("Komplett sett med situasjonsplan, fasade- og snittegninger registrert.")

        legal_checkpoints.append(LegalCheckpoint(
            id="pbl_21_7",
            title="Saksbehandlingskrav og vedleggskompletthet",
            legal_reference="Plan- og bygningsloven § 21-7 / SAK10 kap. 5",
            status=cp8_status,
            risk_level=cp8_risk,
            findings=cp8_findings,
            requirements_to_pass=cp8_reqs
        ))

        # 6. Beregn Kvantitativ Kvalitetsscore og Innvilgelsessannsynlighet %
        quality_score = 90
        risk_score = 15

        critical_count = sum(1 for cp in legal_checkpoints if cp.status == "Kritisk planavvik / Avslagsrisiko")
        warning_count = sum(1 for cp in legal_checkpoints if cp.status == "Krever avklaring / Mangel")

        quality_score -= (critical_count * 35)
        quality_score -= (warning_count * 12)
        quality_score -= (len(missing_attachments) * 6)
        if har_nabomerknader:
            quality_score -= 10

        # Beregn sannsynlighet
        if critical_count > 0:
            approval_probability_pct = max(10, min(35, quality_score - 20))
            probability_verdict = "Kritisk planbrudd / Høy risiko for avslag (Må rettes før innsending)"
            risk_level = "Kritisk"
            risk_score = 85
        elif warning_count >= 2 or len(missing_attachments) >= 2:
            approval_probability_pct = max(40, min(74, quality_score - 5))
            probability_verdict = "Moderat risiko for mangelbrev (Bør suppleres før innsending)"
            risk_level = "Moderat"
            risk_score = 45
        elif warning_count == 1 or len(missing_attachments) == 1:
            approval_probability_pct = max(75, min(89, quality_score))
            probability_verdict = "God søknad med mindre avklaringspunkter"
            risk_level = "Lav"
            risk_score = 25
        else:
            approval_probability_pct = min(98, max(90, quality_score + 5))
            probability_verdict = "Svært høy sannsynlighet for innvilgelse (Klar til innsending)"
            risk_level = "Lav"
            risk_score = 10

        quality_score = max(10, min(99, quality_score))

        # 7. Kompleksitetsberegning
        complexity_score = 3
        if er_i_strandsone:
            complexity_score += 3
        if disp_needed:
            complexity_score += 2
        if har_avkjorsel_endring:
            complexity_score += 1
        if category in ["Nybygg", "Næring / Formålsbygg"]:
            complexity_score += 2
        elif category in ["Tilbygg & Påbygg", "Garasje & Uthus"]:
            complexity_score += 1

        complexity_score = min(10, max(1, complexity_score))
        if complexity_score >= 8:
            complexity_level = "Svært kompleks"
        elif complexity_score >= 6:
            complexity_level = "Kompleks"
        elif complexity_score >= 4:
            complexity_level = "Standard"
        else:
            complexity_level = "Enkel"

        # 8. Saksbehandlingsfrist
        if disp_needed or har_nabomerknader or er_i_strandsone or category in ["Nybygg", "Næring / Formålsbygg"]:
            statutory_deadline_weeks = 12
            statutory_deadline_basis = "12 ukers lovpålagt frist (pbl § 21-7 første ledd). Saken omfatter dispensasjon, nabomerknader eller ordinært søknadspliktig tiltak."
        else:
            statutory_deadline_weeks = 3
            statutory_deadline_basis = "3 ukers lovpålagt frist (pbl § 21-7 andre ledd). Tiltaket er i samsvar med plan og bestemmelser, uten dispensasjon eller nabomerknader."

        # 9. Generer oppsummering og anbefaling
        summary = (
            f"Forhåndsevaluering av '{tiltak_tittel}' ({category}). "
            f"Søknadskvaliteten er vurdert til {quality_score}/100 med en estimert godkjenningssannsynlighet på {approval_probability_pct} %. "
            f"Tiltaket er klassifisert som '{complexity_level}' (kompleksitet {complexity_score}/10). "
            f"{'Saken krever 12 ukers ordinær saksbehandling pga. dispensasjon/naboforhold.' if statutory_deadline_weeks == 12 else 'Søknaden kvalifiserer for rask 3-ukers behandlingstid etter pbl § 21-7.'}"
        )

        if critical_count > 0:
            recommendations = (
                f"STOPP: Søknaden bør IKKE sendes inn i nåværende form! Det er avdekket {critical_count} kritiske plan- eller lovavvik "
                f"(bl.a. {', '.join([cp.title for cp in legal_checkpoints if cp.status == 'Kritisk planavvik / Avslagsrisiko'])}). "
                f"Følg tiltakslisten og rett opp disse punktene før innsending for å unngå formelt avslag eller tidkrevende omgjøringsprosesser."
            )
        elif improvements or missing_attachments:
            recommendations = (
                f"ANBEFALING: Søknaden har gode forutsetninger, men bør suppleres med {len(missing_attachments)} manglende vedlegg "
                f"og avklaring av {len(improvements)} tiltakspunkter før innsending. "
                f"Dette vil sikre at kommunen ikke stanser saksbehandlingsfristen med mangelbrev."
            )
        else:
            recommendations = (
                "GRØNT LYS: Søknaden fremstår som komplett, lovkonform og godt forberedt. "
                "Søknaden kan trygt sendes inn til Tønsberg kommune via Byggesøknaden / Fellestjenester Bygg."
            )

        snippet = (extracted_file_text[:300] + "...") if extracted_file_text and len(extracted_file_text) > 300 else extracted_file_text

        return PreEvaluationReport(
            tiltak_tittel=tiltak_tittel,
            category=category,
            subcategory=subcategory,
            address=addr_str,
            matrikkel=matrikkel_str,
            approval_probability_pct=approval_probability_pct,
            probability_verdict=probability_verdict,
            quality_score=quality_score,
            complexity_score=complexity_score,
            complexity_level=complexity_level,
            risk_level=risk_level,
            risk_score=risk_score,
            statutory_deadline_weeks=statutory_deadline_weeks,
            statutory_deadline_basis=statutory_deadline_basis,
            bya_summary=bya_summary,
            improvements=improvements,
            missing_attachments=missing_attachments,
            strengths=strengths,
            legal_checkpoints=legal_checkpoints,
            summary=summary,
            recommendations=recommendations,
            extracted_text_snippet=snippet
        )

