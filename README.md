# Byggeval – Byggesak Evaluering (Tønsberg Kommune)

Et moderne, automatisert system for innhenting, parsing, faglig risikovurdering og interaktiv visualisering av byggesaker fra Tønsberg kommunes postlister og innsynsløsning.

Repository: [https://github.com/magnuskiro/byggeval](https://github.com/magnuskiro/byggeval)

---

## 🌟 Hovedfunksjoner

1. **Direkte Innsyn-integrasjon mot Tønsberg kommune:**
   - Innhenting via Tønsberg kommunes offisielle postliste- og innsyns-API (`/api/presentation/v2/nye-innsyn`).
   - Henter både overordnede saksdata og fullstendige journalposter, parter (søker/ansvarlig søker), saksbehandlere og dokumenter.
   - Paginering og filtrering på sakstyper (Byggesak, Tilsyn/Ulovlighet, Plansaker, Delingssaker).

2. **Intelligent Evalueringsmotor (`ByggesakEvaluator`):**
   - **Adresse- og Matrikkelparser:** Automatisk deteksjon og uthenting av gatenavn, husnummer, bokstav, samt Gnr/Bnr (Gårds- og bruksnummer som f.eks. `1009/47` eller `137/78`).
   - **Klassifisering:** Automatisk kategorisering i Nybygg (enebolig/rekkehus/fritidsbolig), Tilbygg/Påbygg, Bruksendring (kjeller/loft/hybel), Garasje/Carport, Riving, Fasadeendring, Ulovlighet/Tilsyn, Minirenseanlegg/VA, m.m.
   - **Risiko- og Kompleksitetsvurdering:** Poengberegning (1-100) basert på dispensasjonskrav, berøring av strandsone/verneområder, nabomerknader og eventuell ulovlighetsoppfølging.
   - **Faglig sammendrag & rådgivning:** Generering av tiltakssammendrag og konkrete råd til videre saksbehandling.

3. **Interaktiv Web-Presentasjon:**
   - **Saksutforsker:** Raskt sanntidssøk i tittel, adresse, saksnummer og saksbehandler. Filtrering på kategori, risikonivå og sortering. Både kortvisning og tabellvisning.
   - **Saksdetaljer & Tidslinje:** Slide-over panel med komplett evalueringsrapport, identifiserte risikofaktorer, tidslinje for journalposter og direkte lenke til kommunens journal.
   - **Kartvisning (Leaflet):** Geografisk plassering av alle byggesaker i Tønsberg med fargekodede markører for risikoprofil.
   - **Statistikk & Analyse (Chart.js):** Visuell oversikt over kategorifordeling, risikoprofil og saksstadier.
   - **Live Synkronisering:** Mulighet for å trigge ny innhenting direkte fra nettleseren med sanntids framdriftsindikator.

---

## 🏗️ Prosjektstruktur

```
byggeval/
├── data/                  # SQLite database og lokal datalagring
├── src/
│   └── byggeval/
│       ├── __init__.py
│       ├── models.py      # Pydantic datamodeller
│       ├── client.py      # Tønsberg Innsyn API-klient
│       ├── evaluator.py   # Evalueringsmotor og adresseparser
│       ├── geocoder.py    # Geokoding for Tønsberg
│       ├── database.py    # SQLite databaselag
│       ├── api.py         # FastAPI REST API
│       └── fetch_cli.py   # CLI-verktøy for datahenting
├── static/                # Web frontend
│   ├── index.html         # Responsivt web-grensesnitt
│   ├── styles.css         # Skreddersydd CSS-designsystem
│   └── app.js             # Frontend-logikk og kart/grafer
├── tests/                 # Automatiske tester
│   ├── test_client.py     # API-tester mot Tønsberg
│   ├── test_evaluator.py  # Evaluerings- og parsetester
│   ├── test_database.py   # Databasetester
│   └── test_api.py        # REST API tester
├── fetch_cases.py         # Startskript for innhenting
├── server.py              # Startskript for webserver
├── requirements.txt       # Avhengigheter
└── README.md
```

---

## 🚀 Kom i gang

### 1. Kloning og oppsett av virtuelt miljø
```bash
git clone https://github.com/magnuskiro/byggeval.git
cd byggeval

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Kjør testene
```bash
pytest -v
```

### 3. Hent byggesaker fra Tønsberg kommune
For å hente de nyeste byggesakene og lagre dem i databasen:
```bash
python fetch_cases.py --pages 5 --page-size 20
```

Valgfrie parametere:
- `--pages <antall>`: Antall sider (standard: 3)
- `--page-size <antall>`: Saker per side (standard: 20)
- `--search <tekst>`: Søkefilter (f.eks. `--search "tilbygg"`)
- `--all-types`: Hent alle sakstyper, ikke bare byggesaker

### 4. Start webapplikasjonen
```bash
python server.py
```
Åpne nettleseren på [http://localhost:8000](http://localhost:8000).

---

## 📡 REST API-endepunkter

| Metode | Endepunkt | Beskrivelse |
|---|---|---|
| `GET` | `/api/cases` | Henter saker med støtte for `search`, `category`, `risk_level`, `sort_by`, `limit`, `offset` |
| `GET` | `/api/cases/{id}` | Henter fullstendige detaljer og dokumenter for en sak |
| `GET` | `/api/stats` | Henter aggregert statistikk og risikofordeling |
| `GET` | `/api/map` | Henter geokodede punkter for kartvisning |
| `POST` | `/api/sync` | Trigger asynkron innhenting fra Tønsberg API |
| `GET` | `/api/sync/status` | Henter status på pågående synkronisering |

---

## 📄 Lisens
Utviklet for evaluering av byggesaker i Tønsberg kommune. MIT-lisens.
