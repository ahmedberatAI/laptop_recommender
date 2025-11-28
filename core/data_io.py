from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
import pandas as pd
import numpy as np
import pickle
import re

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

DATA_FILES = [
    DATA_DIR / "amazon_laptops.csv",
    DATA_DIR / "mediamarkt_laptops.csv",
    DATA_DIR / "incehesap_laptops.csv",
    DATA_DIR / "vatan_laptops.csv",
]
CACHE_FILE = DATA_DIR / "laptop_cache.pkl"
ALL_DATA_FILE = DATA_DIR / "all_data.csv"

LAST_STATUS: str = "not_loaded"
_LAST_FOUND_FILES: List[Path] = []
_LAST_LOADED_FILES: Dict[str, int] = {}


def _read_csv_with_encoding(path: Path, encoding: str, use_sniff: bool) -> Optional[pd.DataFrame]:
    """
    Attempt to read a CSV with a given encoding and delimiter sniffing.
    Returns the DataFrame on success or None on failure.
    """
    kwargs: Dict[str, object] = {"encoding": encoding}
    if encoding == "utf-8":
        kwargs["encoding_errors"] = "replace"
    if use_sniff:
        kwargs["sep"] = None
        kwargs["engine"] = "python"
    try:
        return pd.read_csv(path, **kwargs)
    except TypeError as type_err:
        # Older pandas versions may not support encoding_errors.
        if "encoding_errors" in str(type_err) and "unexpected" in str(type_err):
            kwargs.pop("encoding_errors", None)
            try:
                return pd.read_csv(path, **kwargs)
            except Exception:
                return None
        return None
    except Exception:
        return None


def _load_single_csv(path: Path) -> Optional[pd.DataFrame]:
    """Load a single CSV file with tolerant encoding and delimiter handling."""
    for encoding in ("utf-8-sig", "utf-8"):
        for use_sniff in (True, False):
            df = _read_csv_with_encoding(path, encoding, use_sniff)
            if df is not None:
                return df
    return None


def get_last_dataio_status() -> str:
    """Expose last load_data status for UI diagnostics."""
    return LAST_STATUS


def debug_data_inventory() -> dict:
    """Provide a snapshot of data discovery and loading details."""
    return {
        "project_root": str(PROJECT_ROOT),
        "data_dir": str(DATA_DIR),
        "found_files": [str(path) for path in _LAST_FOUND_FILES],
        "loaded_files": {name: int(count) for name, count in _LAST_LOADED_FILES.items()},
        "status": LAST_STATUS,
    }


def clean_price(price_str):
    """Normalize price text to an integer value; return None when invalid."""
    if pd.isna(price_str):
        return None

    if isinstance(price_str, (int, float)):
        price = int(price_str)
    else:
        cleaned = re.sub(r"[^\d]", "", str(price_str))
        if not cleaned:
            return None
        try:
            price = int(cleaned)
        except ValueError:
            return None

    if price < 1000 or price > 500_000:
        return None
    return price


def clean_ram_value(ram_str):
    """Extract RAM size in GB; default to 8 when it cannot be parsed."""
    if pd.isna(ram_str):
        return 8

    ram_text = str(ram_str).upper()
    match = re.search(r"\((\d+)\s*GB\)", ram_text)
    if match:
        return int(match.group(1))

    numbers = re.findall(r"(\d+)\s*GB", ram_text)
    if numbers:
        return max(int(n) for n in numbers)

    numbers = re.findall(r"\d+", ram_text)
    if numbers:
        value = int(numbers[0])
        if value in [4, 8, 12, 16, 24, 32, 48, 64, 128]:
            return value

    return 8


def clean_ssd_value(storage_str):
    """Extract SSD size in GB; default to 256 when it cannot be parsed."""
    if pd.isna(storage_str):
        return 256

    storage_text = str(storage_str).upper()
    tb_match = re.search(r"(\d+)\s*TB", storage_text)
    if tb_match:
        return int(tb_match.group(1)) * 1024

    gb_match = re.search(r"(\d+)\s*GB", storage_text)
    if gb_match:
        gb_val = int(gb_match.group(1))
        if gb_val in [128, 256, 512, 1024, 2048]:
            return gb_val
        if gb_val == 1000:
            return 1024
        if gb_val == 500:
            return 512

    numbers = re.findall(r"\d+", storage_text)
    if numbers:
        value = int(numbers[0])
        if value in [128, 256, 512, 1024, 2048]:
            return value
        if value == 1:
            return 1024

    return 256


def extract_brand(name):
    """Infer brand name from the product title."""
    if pd.isna(name):
        return "other"

    name_lower = str(name).lower()
    brand_keywords = {
        "apple": ["apple", "macbook", "mac "],
        "lenovo": ["lenovo", "thinkpad", "ideapad", "yoga", "legion"],
        "asus": ["asus", "rog", "zenbook", "vivobook", "tuf"],
        "dell": ["dell", "alienware", "xps", "inspiron", "latitude"],
        "hp": ["hp ", "hewlett", "omen", "pavilion", "elitebook", "victus", "omnibook"],
        "msi": ["msi ", "msi-", "msi_"],
        "acer": ["acer", "predator", "aspire", "nitro"],
        "microsoft": ["microsoft", "surface"],
        "huawei": ["huawei", "matebook"],
        "samsung": ["samsung", "galaxy book"],
        "monster": ["monster", "tulpar", "abra"],
        "casper": ["casper", "excalibur", "nirvana"],
    }

    for brand, keywords in brand_keywords.items():
        for keyword in keywords:
            if keyword in name_lower:
                return brand
    return "other"


def parse_screen_size(val) -> float:
    """
    Parse screen size text into inches.

    Values outside the 10-19.9 interval are rejected and np.nan is returned.
    """
    if pd.isna(val):
        return np.nan

    text = str(val).lower()
    text = text.replace(",", ".")
    text = re.sub(r"(\d{2})\s*\.\s*(\d)", r"\1.\2", text)

    for match in re.finditer(r"(\d{2}(?:\.\d)?)", text):
        try:
            size = float(match.group(1))
            if 10.0 <= size <= 19.9:
                return size
        except ValueError:
            continue

    return np.nan


def load_data(use_cache: bool = True) -> pd.DataFrame:
    """
    Discover, read, and merge CSV files in the data directory.

    - Uses CACHE_FILE when available (and not empty) if use_cache is True.
    - Tries encodings utf-8-sig then utf-8 (with replacement on errors).
    - Auto-detects delimiters via sep=None with the python engine, then falls back to defaults.
    - Keeps only non-empty frames, normalizes column casing, and maps a couple of key columns.
    """
    global LAST_STATUS, _LAST_FOUND_FILES, _LAST_LOADED_FILES

    _LAST_FOUND_FILES = []
    _LAST_LOADED_FILES = {}

    if use_cache and CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "rb") as file:
                cached_df = pickle.load(file)
            if isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
                LAST_STATUS = f"Loaded {len(cached_df)} rows from cache"
                _LAST_LOADED_FILES = {str(CACHE_FILE): len(cached_df)}
                return cached_df.copy()
            LAST_STATUS = "Cache was empty or invalid, reloading from CSV files"
        except Exception as exc:
            LAST_STATUS = f"Cache load failed ({exc}); reloading from CSV files"

    if not DATA_DIR.exists():
        LAST_STATUS = f"Data directory not found at {DATA_DIR}"
        return pd.DataFrame()

    csv_files = sorted(DATA_DIR.glob("*.csv"))
    if not csv_files:
        csv_files = sorted(DATA_DIR.glob("*laptops*.csv"))
    _LAST_FOUND_FILES = csv_files

    if not csv_files:
        LAST_STATUS = f"No CSV files found in {DATA_DIR}"
        return pd.DataFrame()

    frames: List[pd.DataFrame] = []
    loaded_counts: Dict[str, int] = {}

    for csv_file in csv_files:
        df = _load_single_csv(csv_file)
        if df is not None and not df.empty:
            df.columns = df.columns.str.lower().str.strip()
            frames.append(df)
            loaded_counts[str(csv_file)] = len(df)

    _LAST_LOADED_FILES = loaded_counts

    if not frames:
        LAST_STATUS = f"Found {len(csv_files)} CSV files but none contained usable rows"
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined.columns = combined.columns.str.lower().str.strip()

    if "price" not in combined.columns and "fiyat" in combined.columns:
        combined = combined.rename(columns={"fiyat": "price"})
    if "name" not in combined.columns:
        if "title" in combined.columns:
            combined = combined.rename(columns={"title": "name"})
        elif "urun" in combined.columns:
            combined = combined.rename(columns={"urun": "name"})

    LAST_STATUS = f"Loaded {len(combined)} rows from {len(loaded_counts)} CSV files"

    if use_cache:
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "wb") as file:
                pickle.dump(combined, file)
        except Exception:
            # Caching failures should not break data loading.
            pass

    return combined


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize and enrich the raw laptop dataset.

    - Normalize column names.
    - Clean price/ram/ssd fields.
    - Parse screen size and fill missing values with 15.6.
    - Add brand column and placeholder cpu_score/gpu_score columns.
    - Infer operating system.
    - Drop rows with missing name/price and prices below 5000.
    - Fill remaining missing hardware defaults.
    """
    clean_df = df.copy()
    clean_df.columns = clean_df.columns.str.lower().str.strip()

    if "name" not in clean_df.columns:
        clean_df["name"] = np.nan

    if "price" in clean_df.columns:
        clean_df["price"] = clean_df["price"].apply(clean_price)
    elif "fiyat" in clean_df.columns:
        clean_df["price"] = clean_df["fiyat"].apply(clean_price)

    if "ram" in clean_df.columns:
        clean_df["ram_gb"] = clean_df["ram"].apply(clean_ram_value)
    else:
        clean_df["ram_gb"] = 8

    if "ssd" in clean_df.columns:
        clean_df["ssd_gb"] = clean_df["ssd"].apply(clean_ssd_value)
    elif "storage" in clean_df.columns:
        clean_df["ssd_gb"] = clean_df["storage"].apply(clean_ssd_value)
    else:
        clean_df["ssd_gb"] = 256

    if "screen_size" in clean_df.columns:
        clean_df["screen_size"] = clean_df["screen_size"].apply(parse_screen_size)
    else:
        clean_df["screen_size"] = np.nan
    clean_df["screen_size"] = clean_df["screen_size"].fillna(15.6)

    clean_df["brand"] = clean_df["name"].apply(extract_brand)

    if "cpu_score" not in clean_df.columns:
        clean_df["cpu_score"] = 5.0
    if "gpu_score" not in clean_df.columns:
        clean_df["gpu_score"] = 3.0

    def detect_os(row: pd.Series) -> str:
        """Infer OS from explicit column, product name, or brand."""
        os_field = row.get("os", None)
        if pd.notna(os_field):
            os_text = str(os_field).lower()
            if any(x in os_text for x in ["windows", "win11", "win10", "w11", "w10"]):
                return "windows"
            if any(x in os_text for x in ["mac", "macos", "os x"]):
                return "macos"
            if any(x in os_text for x in ["ubuntu", "linux", "debian"]):
                return "linux"
            if any(x in os_text for x in ["dos", "free", "yok", "none"]):
                return "freedos"

        name_text = str(row.get("name", "")).lower()
        if any(x in name_text for x in ["windows 11", "win11", "w11", "windows 10", "win10"]):
            return "windows"
        if "macbook" in name_text or "mac " in name_text:
            return "macos"
        if any(x in name_text for x in ["freedos", "free dos", "fdos", "dos", "/dos"]):
            return "freedos"

        if row.get("brand") == "apple":
            return "macos"
        return "freedos"

    clean_df["os"] = clean_df.apply(detect_os, axis=1)

    clean_df = clean_df.dropna(subset=["price", "name"])
    clean_df = clean_df[clean_df["price"] > 5000]

    clean_df["ram_gb"] = clean_df["ram_gb"].fillna(8)
    clean_df["ssd_gb"] = clean_df["ssd_gb"].fillna(256)
    clean_df["screen_size"] = clean_df["screen_size"].fillna(15.6)
    clean_df["cpu_score"] = clean_df["cpu_score"].fillna(5.0)
    clean_df["gpu_score"] = clean_df["gpu_score"].fillna(3.0)

    return clean_df.reset_index(drop=True)


def append_to_all_data(timestamp: Optional[datetime] = None) -> int:
    """
    Append current CSV rows into ALL_DATA_FILE with metadata columns.

    Returns the number of appended rows.
    """
    scraped_at = (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    new_frames = []

    for path in DATA_FILES:
        if path.exists():
            df = pd.read_csv(path, encoding="utf-8")
            df["scraped_at"] = scraped_at
            df["source"] = path.stem.replace("_laptops", "")
            new_frames.append(df)

    if not new_frames:
        return 0

    new_data = pd.concat(new_frames, ignore_index=True)
    appended = len(new_data)

    if ALL_DATA_FILE.exists():
        existing = pd.read_csv(ALL_DATA_FILE, encoding="utf-8")
        combined = pd.concat([existing, new_data], ignore_index=True)
    else:
        combined = new_data

    ALL_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(ALL_DATA_FILE, index=False, encoding="utf-8-sig")
    return appended


def save_data(df: pd.DataFrame, filename: str = "laptop_data_export.csv") -> Path:
    """Save the given DataFrame under DATA_DIR and return the saved path."""
    filepath = DATA_DIR / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    return filepath
