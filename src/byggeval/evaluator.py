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
            days_in_process=days_in_process
        )

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

        # Ekstraher firmaer og utførende foretak
        primary_company, companies = cls.extract_companies(raw_sak, dokumenter)

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
            primary_company=primary_company,
            companies=companies,
            address_info=address_info,
            evaluation=evaluation,
            dokumenter=dokumenter
        )
