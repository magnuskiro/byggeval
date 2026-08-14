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
from .models import AddressInfo, EvaluationResult, Byggesak, Dokument


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
            legal_basis=deadline_info["legal_basis"]
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
        weeks = 12
        days = 84
        legal_basis = "Plan- og bygningsloven § 21-7 4. ledd (12-ukers standardfrist løper fra komplett søknad)"

        if stage == "Forhåndskonferanse":
            weeks = 2
            days = 14
            legal_basis = "Plan- og bygningsloven § 21-1 / SAK10 § 7-5 (2-ukers frist for avholdelse av forhåndskonferanse)"
        elif stage in ["Igangsettingstillatelse", "Ferdigattest omsøkt/utstedt"]:
            weeks = 3
            days = 21
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
            legal_basis = "Plan- og bygningsloven § 21-7 1. ledd / SAK10 § 7-1 (3-ukers frist: kurant tiltak i tråd med plan uten dispensasjoner)"
        elif "dispensasjon" in flags or "vernesone" in flags:
            weeks = 12
            days = 84
            legal_basis = "Plan- og bygningsloven § 21-7 4. ledd (12-ukers frist: krever dispensasjonsvedtak etter pbl kap 19)"

        # 1. Finn dato for søknad og eventuell siste tilleggsdokumentasjon / mangelbrev
        initial_date_str = sak_data.get("dato")
        initial_dt = None
        if initial_date_str:
            try:
                initial_dt = datetime.strptime(initial_date_str.strip(), "%d.%m.%Y")
            except Exception:
                pass

        docs = sak_data.get("dokumenter", [])
        latest_supplement_dt = None
        latest_supplement_str = None
        latest_mangelbrev_dt = None
        latest_mangelbrev_str = None

        for d in docs:
            dtit = d.get("tittel", "").lower() if isinstance(d, dict) else (d.tittel.lower() if hasattr(d, "tittel") else "")
            ddato = d.get("dato") if isinstance(d, dict) else (d.dato if hasattr(d, "dato") else None)
            if not ddato:
                continue

            parsed_d = None
            try:
                parsed_d = datetime.strptime(ddato.strip(), "%d.%m.%Y")
            except Exception:
                continue

            # Sjekk etterspørsel om mangler fra kommunen (mangelbrev / ber om tilleggsinfo)
            if any(w in dtit for w in ["mangelbrev", "tilleggsdokumentasjon og varsel", "ber om tilleggs", "mangler ved søknad", "etterlysning"]):
                if not latest_mangelbrev_dt or parsed_d > latest_mangelbrev_dt:
                    latest_mangelbrev_dt = parsed_d
                    latest_mangelbrev_str = ddato

            # Sjekk innsendt tilleggsdokumentasjon / supplering fra søker
            if any(w in dtit for w in ["ettersending", "supplering", "tilleggsopplysning", "revidert", "svar på mangel", "supplerende"]):
                if not latest_supplement_dt or parsed_d > latest_supplement_dt:
                    latest_supplement_dt = parsed_d
                    latest_supplement_str = ddato

        # Avgjør komplett søknadsdato
        complete_dt = initial_dt
        complete_date_str = initial_date_str

        # Dersom det er ettersendt tilleggsdokumentasjon etter opprinnelig dato:
        if latest_supplement_dt and (not initial_dt or latest_supplement_dt > initial_dt):
            complete_dt = latest_supplement_dt
            complete_date_str = latest_supplement_str

        # Sjekk om fristen er stanset/fryst pga ubesvart mangelbrev
        is_deadline_paused = False
        deadline_pause_reason = None
        if latest_mangelbrev_dt:
            if not latest_supplement_dt or latest_mangelbrev_dt > latest_supplement_dt:
                is_deadline_paused = True
                deadline_pause_reason = f"Kommunen etterspurte tilleggsdokumentasjon {latest_mangelbrev_str}. Fristen er fryst i påvente av svar."

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
            days_in_proc = max(0, (datetime.now().date() - complete_dt.date()).days)

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
            "legal_basis": legal_basis
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
        if isinstance(status, dict) and status.get("erFerdig"):
            return "Ferdigbehandlet"
            
        if any(w in text for w in ["ferdigattest"]):
            return "Ferdigattest omsøkt/utstedt"
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
        name_lower = name.lower()
        
        # Kjente selskapsformer og nøkkelord
        company_indicators = [
            r'\bas\b', r'\ba/s\b', r'\bans\b', r'\bda\b', r'\benk\b', r'\bsf\b', r'\bhf\b',
            'arkitekt', 'arkitektur', 'bygg', 'byggmester', 'tømrer', 'entreprenør',
            'ingeniør', 'konsult', 'consulting', 'hus', 'invest', 'tjenester',
            'vann & miljø', 'miljø', 'eiendom', 'bolig', 'sameie', 'borettslag',
            'advokat', 'plan', 'geodesi', 'takst', 'prosjekt'
        ]
        
        for pattern in company_indicators:
            if re.search(pattern, name_lower):
                return True
                
        # Hvis navnet har mer enn 2 ord og inneholder store forbokstaver på alle ord eller spesielle tegn
        if len(name.split()) >= 3 and any(char in name for char in ["&", "+", "-", "/"]):
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
        Skiller strengt mellom søkers innsendte søknader og kommunens formelle godkjenninger/avslag.
        """
        has_decision = False
        decision_type = "Ikke avgjort (Under behandling)"
        decision_doc_title = None
        decision_date = None

        # Prioritert leting etter offisielle vedtaksdokumenter
        for d in dokumenter:
            t = d.tittel.lower()
            
            # 1. Sjekk ferdigattest
            if ("ferdigattest" in t or "brukstillatelse" in t) and "søknad" not in t and "anmodning" not in t:
                has_decision = True
                decision_type = "Ferdigattest utstedt"
                decision_doc_title = d.tittel
                decision_date = d.dato
                break
                
            # 2. Sjekk igangsettingstillatelse
            if "igangsettingstillatelse" in t and "søknad" not in t and "anmodning" not in t:
                has_decision = True
                decision_type = "Innvilget / Igangsettingstillatelse gitt"
                decision_doc_title = d.tittel
                decision_date = d.dato
                break
                
            # 3. Sjekk rammetillatelse eller ett-trinnstillatelse
            if ("rammetillatelse" in t or "ett-trinnstillatelse" in t or "tillatelse i ett trinn" in t or "tillatelse til tiltak" in t) and "søknad" not in t and "anmodning" not in t:
                has_decision = True
                decision_type = "Innvilget / Tillatelse gitt"
                decision_doc_title = d.tittel
                decision_date = d.dato
                break

            # 4. Sjekk delegert vedtak / godkjenning
            if ("delegert vedtak" in t or "vedtak om tillatelse" in t or "svar på søknad - godkjent" in t) and "søknad" not in t:
                has_decision = True
                decision_type = "Innvilget / Delegert vedtak"
                decision_doc_title = d.tittel
                decision_date = d.dato
                break

            # 5. Sjekk avslag
            if ("vedtak om avslag" in t or "avslag på søknad" in t or "avslått" in t) and "søknad" not in t:
                has_decision = True
                decision_type = "Avslått av kommunen"
                decision_doc_title = d.tittel
                decision_date = d.dato
                break

            # 6. Sjekk pålegg / stans
            if "pålegg om stans" in t or "stansingsvedtak" in t or "vedtak om pålegg" in t:
                has_decision = True
                decision_type = "Pålegg / Stansingsvedtak"
                decision_doc_title = d.tittel
                decision_date = d.dato
                break

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
        er_ferdig = status_obj.get("erFerdig", False) if isinstance(status_obj, dict) else False

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
            primary_company=primary_company,
            companies=companies,
            address_info=address_info,
            evaluation=evaluation,
            dokumenter=dokumenter
        )
