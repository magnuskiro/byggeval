"""
SQLite database- og lagringslag for Byggeval.
"""

import json
import sqlite3
import os
from typing import List, Optional, Dict, Any, Tuple, Set
from datetime import datetime
from .models import Byggesak, AddressInfo, EvaluationResult, Dokument
from .geocoder import geocode_address


class Database:
    """Databasehåndtering for byggesaker, evalueringer og statistikk."""

    def __init__(self, db_path: str = "data/byggeval.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Oppretter nødvendige tabeller og indekser."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    identifikator TEXT PRIMARY KEY,
                    saksnummer TEXT,
                    tittel TEXT,
                    undertittel TEXT,
                    sakstype TEXT,
                    saks_beskrivelse TEXT,
                    dato TEXT,
                    saksbehandler TEXT,
                    status_tittel TEXT,
                    er_ferdig INTEGER,
                    innsyn_url TEXT,
                    
                    -- Utførende / firma / foretak
                    primary_company TEXT,
                    companies_text TEXT,
                    
                    -- Ekstraherte adressefelt
                    street_name TEXT,
                    house_number TEXT,
                    gnr INTEGER,
                    bnr INTEGER,
                    matrikkel TEXT,
                    latitude REAL,
                    longitude REAL,
                    
                    -- Evalueringsfelt for indeksering og filtrering
                    category TEXT,
                    subcategory TEXT,
                    complexity TEXT,
                    complexity_score INTEGER,
                    risk_level TEXT,
                    risk_score INTEGER,
                    stage TEXT,
                    
                    -- JSON-strukturer
                    address_json TEXT,
                    evaluation_json TEXT,
                    dokumenter_json TEXT,
                    raw_json TEXT,
                    
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            # Kjør sikre migrasjoner for eksisterende databaser
            try:
                cursor.execute("ALTER TABLE cases ADD COLUMN primary_company TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE cases ADD COLUMN companies_text TEXT")
            except sqlite3.OperationalError:
                pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    cases_synced INTEGER,
                    error_count INTEGER,
                    status TEXT
                )
            """)

            # Indekser for rask filtrering og søk
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_dato ON cases(dato)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_category ON cases(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_risk_level ON cases(risk_level)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_saksnummer ON cases(saksnummer)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_company ON cases(primary_company)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_gnr_bnr ON cases(gnr, bnr)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_stage ON cases(stage)")
            conn.commit()

    def save_case(self, case: Byggesak) -> None:
        """Lagrer eller oppdaterer en byggesak."""
        # Sørg for at koordinater er satt
        if case.address_info.latitude is None or case.address_info.longitude is None:
            lat, lon = geocode_address(
                case.address_info.street_name,
                case.address_info.house_number,
                case.address_info.gnr,
                case.address_info.bnr
            )
            case.address_info.latitude = lat
            case.address_info.longitude = lon

        eval_res = case.evaluation
        category = eval_res.category if eval_res else "Ukjent"
        subcategory = eval_res.subcategory if eval_res else None
        complexity = eval_res.complexity if eval_res else "Standard"
        complexity_score = eval_res.complexity_score if eval_res else 5
        risk_level = eval_res.risk_level if eval_res else "Lav"
        risk_score = eval_res.risk_score if eval_res else 15
        stage = eval_res.stage if eval_res else "Under saksbehandling"

        companies_str = " | ".join(case.companies) if case.companies else ""

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cases (
                    identifikator, saksnummer, tittel, undertittel, sakstype, saks_beskrivelse,
                    dato, saksbehandler, status_tittel, er_ferdig, innsyn_url,
                    primary_company, companies_text,
                    street_name, house_number, gnr, bnr, matrikkel, latitude, longitude,
                    category, subcategory, complexity, complexity_score, risk_level, risk_score, stage,
                    address_json, evaluation_json, dokumenter_json, raw_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identifikator) DO UPDATE SET
                    saksnummer=excluded.saksnummer,
                    tittel=excluded.tittel,
                    undertittel=excluded.undertittel,
                    sakstype=excluded.sakstype,
                    saks_beskrivelse=excluded.saks_beskrivelse,
                    dato=excluded.dato,
                    saksbehandler=excluded.saksbehandler,
                    status_tittel=excluded.status_tittel,
                    er_ferdig=excluded.er_ferdig,
                    innsyn_url=excluded.innsyn_url,
                    primary_company=excluded.primary_company,
                    companies_text=excluded.companies_text,
                    street_name=excluded.street_name,
                    house_number=excluded.house_number,
                    gnr=excluded.gnr,
                    bnr=excluded.bnr,
                    matrikkel=excluded.matrikkel,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    category=excluded.category,
                    subcategory=excluded.subcategory,
                    complexity=excluded.complexity,
                    complexity_score=excluded.complexity_score,
                    risk_level=excluded.risk_level,
                    risk_score=excluded.risk_score,
                    stage=excluded.stage,
                    address_json=excluded.address_json,
                    evaluation_json=excluded.evaluation_json,
                    dokumenter_json=excluded.dokumenter_json,
                    updated_at=excluded.updated_at
            """, (
                case.identifikator,
                case.saksnummer,
                case.tittel,
                case.undertittel,
                case.sakstype,
                case.saks_beskrivelse,
                case.dato,
                case.saksbehandler,
                case.status_tittel,
                1 if case.er_ferdig else 0,
                case.innsyn_url,
                case.primary_company,
                companies_str,
                case.address_info.street_name,
                case.address_info.house_number,
                case.address_info.gnr,
                case.address_info.bnr,
                case.address_info.matrikkel,
                case.address_info.latitude,
                case.address_info.longitude,
                category,
                subcategory,
                complexity,
                complexity_score,
                risk_level,
                risk_score,
                stage,
                case.address_info.model_dump_json(),
                case.evaluation.model_dump_json() if case.evaluation else "{}",
                json.dumps([d.model_dump() for d in case.dokumenter]),
                "{}",
                case.created_at,
                datetime.now().isoformat()
            ))
            conn.commit()

    def save_cases(self, cases: List[Byggesak]) -> int:
        """Lagrer en liste med saker i én transaksjon."""
        saved_count = 0
        for case in cases:
            self.save_case(case)
            saved_count += 1
        return saved_count

    def get_case(self, identifikator: str) -> Optional[Byggesak]:
        """Henter en enkelt sak etter identifikator."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cases WHERE identifikator = ?", (identifikator,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_case(row)

    def get_all_case_ids(self) -> Set[str]:
        """Henter et sett over alle lagrede saks-identifikatorer for å unngå unødige API-kall."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT identifikator FROM cases")
            rows = cursor.fetchall()
            return {row[0] for row in rows}

    def get_cases(
        self,
        search: Optional[str] = None,
        category: Optional[str] = None,
        risk_level: Optional[str] = None,
        stage: Optional[str] = None,
        company: Optional[str] = None,
        sort_by: str = "dato_desc",
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Byggesak], int]:
        """Henter filtrerte og paginerte saker samt totalt antall."""
        where_clauses = []
        params = []

        if search:
            search_param = f"%{search.strip()}%"
            where_clauses.append("(tittel LIKE ? OR saksnummer LIKE ? OR street_name LIKE ? OR matrikkel LIKE ? OR saksbehandler LIKE ? OR primary_company LIKE ? OR companies_text LIKE ?)")
            params.extend([search_param, search_param, search_param, search_param, search_param, search_param, search_param])

        if category and category != "all":
            where_clauses.append("category = ?")
            params.append(category)

        if risk_level and risk_level != "all":
            where_clauses.append("risk_level = ?")
            params.append(risk_level)

        if stage and stage != "all":
            where_clauses.append("stage = ?")
            params.append(stage)

        if company and company != "all":
            comp_param = f"%{company.strip()}%"
            where_clauses.append("(primary_company LIKE ? OR companies_text LIKE ?)")
            params.extend([comp_param, comp_param])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Sorteringslogikk
        order_sql = "ORDER BY rowid DESC"
        if sort_by == "dato_desc":
            order_sql = "ORDER BY substr(dato, 7, 4) || substr(dato, 4, 2) || substr(dato, 1, 2) DESC, rowid DESC"
        elif sort_by == "dato_asc":
            order_sql = "ORDER BY substr(dato, 7, 4) || substr(dato, 4, 2) || substr(dato, 1, 2) ASC"
        elif sort_by == "risk_desc":
            order_sql = "ORDER BY risk_score DESC"
        elif sort_by == "complexity_desc":
            order_sql = "ORDER BY complexity_score DESC"
        elif sort_by == "saksnummer_desc":
            order_sql = "ORDER BY saksnummer DESC"
        elif sort_by == "company_asc":
            order_sql = "ORDER BY primary_company ASC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Hent totalt antall
            count_query = f"SELECT COUNT(*) FROM cases {where_sql}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]

            # Hent rader
            query = f"SELECT * FROM cases {where_sql} {order_sql} LIMIT ? OFFSET ?"
            cursor.execute(query, params + [limit, offset])
            rows = cursor.fetchall()
            
            cases = [self._row_to_case(row) for row in rows]
            return cases, total

    def get_companies(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Henter liste over unike utførende firmaer og foretak med antall saker."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT primary_company as name, COUNT(*) as count
                FROM cases
                WHERE primary_company IS NOT NULL AND TRIM(primary_company) != ''
                GROUP BY primary_company
                ORDER BY count DESC, name ASC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_map_points(self) -> List[Dict[str, Any]]:
        """Henter lette punkter for kartvisning."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT identifikator, saksnummer, tittel, dato, street_name, house_number, matrikkel,
                       primary_company, latitude, longitude, category, subcategory, risk_level, risk_score, stage
                FROM cases
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                ORDER BY substr(dato, 7, 4) || substr(dato, 4, 2) || substr(dato, 1, 2) DESC
                LIMIT 500
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_statistics(self) -> Dict[str, Any]:
        """Genererer helhetlig statistikk og analyse for dashboardet."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Totaler
            cursor.execute("SELECT COUNT(*) FROM cases")
            total_cases = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM cases WHERE er_ferdig = 1 OR stage = 'Ferdigbehandlet'")
            completed_cases = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM cases WHERE risk_level IN ('Høy', 'Kritisk')")
            high_risk_cases = cursor.fetchone()[0]

            # Kategorifordeling
            cursor.execute("""
                SELECT category, COUNT(*) as count 
                FROM cases 
                GROUP BY category 
                ORDER BY count DESC
            """)
            category_breakdown = [dict(row) for row in cursor.fetchall()]

            # Risikofordeling
            cursor.execute("""
                SELECT risk_level, COUNT(*) as count 
                FROM cases 
                GROUP BY risk_level 
                ORDER BY count DESC
            """)
            risk_breakdown = [dict(row) for row in cursor.fetchall()]

            # Stadier
            cursor.execute("""
                SELECT stage, COUNT(*) as count 
                FROM cases 
                GROUP BY stage 
                ORDER BY count DESC
            """)
            stage_breakdown = [dict(row) for row in cursor.fetchall()]

            # Topp Utførende Firmaer
            cursor.execute("""
                SELECT primary_company as name, COUNT(*) as count
                FROM cases
                WHERE primary_company IS NOT NULL AND TRIM(primary_company) != ''
                GROUP BY primary_company
                ORDER BY count DESC
                LIMIT 10
            """)
            top_companies = [dict(row) for row in cursor.fetchall()]

            # Siste synkronisering
            cursor.execute("SELECT * FROM sync_history ORDER BY id DESC LIMIT 1")
            sync_row = cursor.fetchone()
            last_sync = dict(sync_row) if sync_row else None

            return {
                "total_cases": total_cases,
                "active_cases": total_cases - completed_cases,
                "completed_cases": completed_cases,
                "high_risk_cases": high_risk_cases,
                "category_breakdown": category_breakdown,
                "risk_breakdown": risk_breakdown,
                "stage_breakdown": stage_breakdown,
                "top_companies": top_companies,
                "last_sync": last_sync
            }

    def record_sync(self, cases_synced: int, error_count: int = 0, status: str = "success") -> None:
        """Registrerer en synkroniseringshendelse."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sync_history (timestamp, cases_synced, error_count, status)
                VALUES (?, ?, ?, ?)
            """, (datetime.now().isoformat(), cases_synced, error_count, status))
            conn.commit()

    def _row_to_case(self, row: sqlite3.Row) -> Byggesak:
        """Konverterer en databaserad til en Byggesak-modell."""
        address_dict = json.loads(row["address_json"]) if row["address_json"] else {}
        eval_dict = json.loads(row["evaluation_json"]) if row["evaluation_json"] else {}
        docs_raw = json.loads(row["dokumenter_json"]) if row["dokumenter_json"] else []

        dokumenter = [Dokument(**d) for d in docs_raw]

        keys = row.keys()
        companies_raw = row["companies_text"] if ("companies_text" in keys and row["companies_text"]) else ""
        companies_list = [c.strip() for c in companies_raw.split("|") if c.strip()] if companies_raw else []
        primary_company = row["primary_company"] if ("primary_company" in keys) else None

        return Byggesak(
            identifikator=row["identifikator"],
            saksnummer=row["saksnummer"],
            tittel=row["tittel"],
            undertittel=row["undertittel"] or "",
            sakstype=row["sakstype"] or "Byggesak",
            saks_beskrivelse=row["saks_beskrivelse"] or "Byggesak",
            dato=row["dato"],
            saksbehandler=row["saksbehandler"],
            status_tittel=row["status_tittel"] or "Under behandling",
            er_ferdig=bool(row["er_ferdig"]),
            innsyn_url=row["innsyn_url"],
            primary_company=primary_company,
            companies=companies_list,
            address_info=AddressInfo(**address_dict),
            evaluation=EvaluationResult(**eval_dict) if eval_dict else None,
            dokumenter=dokumenter,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or ""
        )
