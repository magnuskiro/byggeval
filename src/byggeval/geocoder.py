"""
Geokoding og koordinatberegning for adresser og matrikkel i Tønsberg kommune.
"""

import hashlib
import re
from typing import Optional, Tuple

# Kjerneområder og kjente steder i Tønsberg med senterkoordinater
TONSBERG_AREAS = {
    "sentrum": (59.2675, 10.4075),
    "halfdan wilhelmsens": (59.2710, 10.4190),
    "storgaten": (59.2660, 10.4090),
    "farmannsveien": (59.2700, 10.4050),
    "skallevold": (59.2780, 10.4950),
    "ringshaug": (59.2720, 10.4820),
    "tolvsrød": (59.2690, 10.4680),
    "vallø": (59.2610, 10.4900),
    "eik": (59.2920, 10.4350),
    "barkåker": (59.3180, 10.3850),
    "sem": (59.2810, 10.3300),
    "vear": (59.2600, 10.3620),
    "slagen": (59.3050, 10.4500),
    "kaldnes": (59.2630, 10.4010),
    "teie": (59.2550, 10.4120),
    "revetal": (59.3720, 10.2640),
    "ramnes": (59.3550, 10.2450),
    "vivestad": (59.4200, 10.1450),
    "våle": (59.4220, 10.2800),
    "undrumsdal": (59.3750, 10.3700),
    "fon": (59.4120, 10.2050),
    "presterød": (59.2700, 10.4550),
    "huitfeldt": (59.2730, 10.4150),
    "skogergaten": (59.2640, 10.4130),
    "dvergveien": (59.2830, 10.4420),
    "nyveien": (59.2680, 10.4180),
    "ramski": (59.2840, 10.4910),
    "trollveien": (59.2860, 10.4480),
    "gjelstad": (59.3300, 10.3100)
}

# Gårdsnummer (Gnr) intervaller for områder i Tønsberg (inkludert tidligere Re kommune)
GNR_AREAS = [
    (1, 40, (59.2670, 10.4100)),     # Tønsberg by / sentrum
    (41, 100, (59.2850, 10.4350)),   # Eik / Bydalen / Teigen
    (101, 180, (59.2750, 10.4800)),  # Søndre Slagen / Tolvsrød / Ringshaug / Skallevold
    (181, 250, (59.3100, 10.4500)),  # Nordre Slagen / Basberg / Råel
    (251, 350, (59.3200, 10.3800)),  # Barkåker / Jarlsberg
    (351, 450, (59.2850, 10.3300)),  # Sem / Aulerød / Vear
    (500, 650, (59.3700, 10.2600)),  # Revetal / Ramnes / Vivestad (tidl. Re)
    (651, 800, (59.4200, 10.2800)),  # Våle / Undrumsdal / Fon
    (1000, 1100, (59.2690, 10.4150)) # Tønsberg by / sentrale strøk
]


def geocode_address(street_name: Optional[str], house_number: Optional[str], gnr: Optional[int], bnr: Optional[int]) -> Tuple[float, float]:
    """
    Beregner geokoordinater (lat, lon) i Tønsberg kommune basert på gatenavn,
    husnummer og matrikkelnummer (gnr/bnr).
    """
    base_lat, base_lon = 59.2675, 10.4075  # Default: Tønsberg sentrum

    found = False

    # 1. Sjekk om gatenavn matcher kjente områder
    if street_name:
        street_lower = street_name.lower()
        for key, coords in TONSBERG_AREAS.items():
            if key in street_lower:
                base_lat, base_lon = coords
                found = True
                break

    # 2. Hvis ikke funnet via gate, sjekk Gnr
    if not found and gnr is not None:
        for start_gnr, end_gnr, coords in GNR_AREAS:
            if start_gnr <= gnr <= end_gnr:
                base_lat, base_lon = coords
                found = True
                break

    # 3. Legg til en deterministisk, stabil forskyvning (jitter) basert på unik adresse og husnummer
    seed_str = f"{street_name or ''}_{house_number or ''}_{gnr or ''}_{bnr or ''}"
    hash_val = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest()[:8], 16)
    
    # Forskyvning innenfor ca. +/- 300 meter for å spre markører på samme gate/gnr
    lat_offset = ((hash_val % 1000) - 500) / 100000.0
    lon_offset = (((hash_val // 1000) % 1000) - 500) / 50000.0

    if house_number:
        try:
            num = int(re.sub(r'\D', '', house_number))
            lat_offset += (num % 20) * 0.0002
            lon_offset += (num % 20) * 0.0003
        except ValueError:
            pass

    return round(base_lat + lat_offset, 6), round(base_lon + lon_offset, 6)
