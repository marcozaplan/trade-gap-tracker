import os
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
AGGREGATE_FILE = DATA_DIR / "gaps_country_year.parquet"
PARTNER_FILE = DATA_DIR / "gaps_partner.parquet"
MANIFEST_FILE = DATA_DIR / "manifest.json"

API_BASE = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
API_KEY = os.getenv("COMTRADE_API_KEY", "")

START_YEAR = 2010
END_YEAR = 2025

# HS chapters covering ores, precious metals and base metals
COMMODITY_GROUPS = {
    "26": "Ores, slag and ash",
    "71": "Precious metals and stones",
    "72": "Iron and steel",
    "73": "Articles of iron or steel",
    "74": "Copper",
    "75": "Nickel",
    "76": "Aluminium",
    "78": "Lead",
    "79": "Zinc",
    "80": "Tin",
    "81": "Other base metals",
}

ALL_COMMODITIES = "ALL"

# EITI implementing countries, M49 codes
EITI_COUNTRIES = {
    "004": "Afghanistan",
    "008": "Albania",
    "032": "Argentina",
    "051": "Armenia",
    "854": "Burkina Faso",
    "120": "Cameroon",
    "140": "Central African Republic",
    "148": "Chad",
    "152": "Chile",
    "170": "Colombia",
    "178": "Congo",
    "180": "Democratic Republic of the Congo",
    "384": "Côte d'Ivoire",
    "214": "Dominican Republic",
    "218": "Ecuador",
    "231": "Ethiopia",
    "276": "Germany",
    "288": "Ghana",
    "320": "Guatemala",
    "324": "Guinea",
    "328": "Guyana",
    "340": "Honduras",
    "360": "Indonesia",
    "368": "Iraq",
    "398": "Kazakhstan",
    "417": "Kyrgyzstan",
    "430": "Liberia",
    "450": "Madagascar",
    "454": "Malawi",
    "466": "Mali",
    "478": "Mauritania",
    "484": "Mexico",
    "496": "Mongolia",
    "508": "Mozambique",
    "104": "Myanmar",
    "528": "Netherlands",
    "562": "Niger",
    "566": "Nigeria",
    "578": "Norway",
    "586": "Pakistan",
    "598": "Papua New Guinea",
    "604": "Peru",
    "608": "Philippines",
    "678": "Sao Tome and Principe",
    "686": "Senegal",
    "690": "Seychelles",
    "694": "Sierra Leone",
    "090": "Solomon Islands",
    "740": "Suriname",
    "834": "Tanzania",
    "626": "Timor-Leste",
    "768": "Togo",
    "780": "Trinidad and Tobago",
    "788": "Tunisia",
    "800": "Uganda",
    "804": "Ukraine",
    "826": "United Kingdom",
    "887": "Yemen",
    "894": "Zambia",
}

DEFAULT_COUNTRY = "608"

# Partner codes that are aggregates or unspecified residuals, never a real counterpart
AGGREGATE_PARTNERS = {
    "000",  # World
    "097",  # EU — reported alongside its member states, so counting both double-counts
    "471", "473", "490", "527", "568", "577", "636", "637", "697", "837",
    "838", "839", "879", "899",
}

ANOMALY_THRESHOLD = 20.0  # percent of declared exports
REQUEST_DELAY = 1.5
PERIOD_CHUNK = 8
