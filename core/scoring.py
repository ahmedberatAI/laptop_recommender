from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import re

# =============================================================================
# Sabitler
# =============================================================================

DEV_PRESETS: Dict[str, Dict[str, Any]] = {
    "web": {
        "min_ram": 16,
        "min_ssd": 512,
        "screen_max": 15.6,
        "prefer_os": {"windows": 1.0, "macos": 1.0, "linux": 1.05},
        "need_dgpu": False,
        "need_cuda": False,
        "cpu_bias": {"hx": +1.0, "h": +0.5, "u": -0.2, "p": +0.2},
        "gpu_bias": {"igpu_ok": +0.3, "dgpu_penalty": -0.2},
        "port_bias": {"<=14": +0.3, "<=15.6": +0.2, ">16": -0.4},
    },
    "ml": {
        "min_ram": 32,
        "min_ssd": 1024,
        "screen_max": 16.0,
        "prefer_os": {"windows": 1.04, "macos": 0.98, "linux": 1.03},
        "need_dgpu": True,
        "need_cuda": True,
        "cpu_bias": {"hx": +0.8, "h": +0.5, "u": -0.6, "p": -0.2},
        "gpu_bias": {
            "rtx>=4060": +1.2,
            "rtx>=4050": +0.8,
            "rtx<4050": +0.3,
            "igpu": -2.0,
        },
        "port_bias": {"<=14": -0.2, "<=15.6": +0.2, ">16": -0.1},
    },
    "mobile": {
        "min_ram": 16,
        "min_ssd": 512,
        "screen_max": 14.5,
        "prefer_os": {"macos": 1.06, "windows": 1.0, "linux": 0.98},
        "need_dgpu": False,
        "need_cuda": False,
        "cpu_bias": {"u": +0.6, "p": +0.3, "h": -0.2, "hx": -0.5},
        "gpu_bias": {"igpu_ok": +0.5, "heavy_dgpu": -0.6},
        "port_bias": {"<=13.6": +0.8, "<=14.5": +0.5, "15-16": -0.2},
    },
    "gamedev": {
        "min_ram": 32,
        "min_ssd": 1024,
        "screen_max": 16.0,
        "prefer_os": {"windows": 1.04, "macos": 0.97, "linux": 1.0},
        "need_dgpu": True,
        "need_cuda": True,
        "cpu_bias": {"hx": +1.0, "h": +0.6, "u": -0.8, "p": -0.3},
        "gpu_bias": {
            "rtx>=4070": +1.2,
            "rtx>=4060": +0.9,
            "rtx>=4050": +0.5,
            "igpu": -2.5,
        },
        "port_bias": {"<=14": -0.2, "<=15.6": +0.2, ">16": +0.1},
    },
    "general": {
        "min_ram": 16,
        "min_ssd": 512,
        "screen_max": 15.6,
        "prefer_os": {"windows": 1.02, "macos": 1.02, "linux": 1.02},
        "need_dgpu": False,
        "need_cuda": False,
        "cpu_bias": {"h": +0.3, "p": +0.2, "u": 0.0, "hx": -0.1},
        "gpu_bias": {"igpu_ok": +0.3, "mid_dgpu": +0.1},
        "port_bias": {"<=14": +0.3, "<=15.6": +0.2, ">16": -0.2},
    },
}

GAMING_TITLE_SCORES: Dict[str, float] = {
    "Starfield": 7.5,
    "Call of Duty: Black Ops 6": 7.0,
    "Forza Horizon 5": 6.5,
    "Baldur's Gate 3": 6.6,
    "Helldivers 2": 6.5,
    "Cyberpunk 2077 (2.0)": 6.8,
    "Assassin's Creed Mirage": 5.5,
    "Forza Motorsport (2023)": 7.5,
    "Lies of P": 5.5,
    "Apex/Fortnite (yüksek ayar)": 5.0,
}

CPU_SCORES: Dict[str, float] = {
    "i9-14": 9.5,
    "i7-14": 8.5,
    "i5-14": 7.0,
    "i3-14": 5.0,
    "i9-13": 9.0,
    "i7-13": 8.0,
    "i5-13": 6.5,
    "i3-13": 4.5,
    "i9-12": 8.5,
    "i7-12": 7.5,
    "i5-12": 6.0,
    "i3-12": 4.0,
    "ryzen 9 7": 9.2,
    "ryzen 7 7": 8.2,
    "ryzen 5 7": 6.8,
    "ryzen 9 8": 9.5,
    "ryzen 7 8": 8.5,
    "ryzen 5 8": 7.0,
    "ultra 9": 9.0,
    "ultra 7": 8.0,
    "ultra 5": 7.0,
    "m4": 9.5,
    "m3": 9.0,
    "m2": 8.5,
    "m1": 8.0,
}

GPU_SCORES: Dict[str, float] = {
    "rtx 5090": 10.0,
    "rtx 5080": 9.5,
    "rtx 5070": 9.0,
    "rtx 5060": 8.5,
    "rtx 5050": 8.0,
    "rtx 4090": 9.8,
    "rtx 4080": 9.3,
    "rtx 4070": 8.8,
    "rtx 4060": 8.0,
    "rtx 4050": 7.2,
    "rtx 3080": 8.5,
    "rtx 3070": 7.8,
    "rtx 3060": 7.0,
    "rtx 3050": 6.0,
    "gtx 16": 5.0,
    "mx5": 4.0,
    "mx4": 3.5,
    "mx3": 3.0,
    "rx 7": 7.5,
    "rx 6": 6.5,
    "radeon": 5.0,
    "iris xe": 3.5,
    "iris plus": 3.0,
    "uhd": 2.0,
    "integrated": 2.0,
    "m4 gpu": 8.5,
    "m3 gpu": 8.0,
    "m2 gpu": 7.5,
    "m1 gpu": 7.0,
}

BRAND_PARAM_SCORES: Dict[str, Dict[str, float]] = {
    "apple": {
        "gaming": 65,
        "portability": 95,
        "productivity": 90,
        "design": 98,
        "dev": 92,
    },
    "lenovo": {
        "gaming": 85,
        "portability": 82,
        "productivity": 95,
        "design": 85,
        "dev": 93,
    },
    "asus": {
        "gaming": 92,
        "portability": 75,
        "productivity": 85,
        "design": 88,
        "dev": 85,
    },
    "dell": {"gaming": 80, "portability": 83, "productivity": 92, "design": 87, "dev": 90},
    "hp": {"gaming": 78, "portability": 82, "productivity": 88, "design": 90, "dev": 84},
    "huawei": {"gaming": 60, "portability": 90, "productivity": 82, "design": 92, "dev": 80},
    "samsung": {"gaming": 65, "portability": 92, "productivity": 80, "design": 91, "dev": 78},
    "msi": {"gaming": 95, "portability": 60, "productivity": 75, "design": 78, "dev": 80},
    "acer": {"gaming": 80, "portability": 78, "productivity": 78, "design": 75, "dev": 78},
    "microsoft": {"gaming": 55, "portability": 88, "productivity": 86, "design": 90, "dev": 85},
    "monster": {"gaming": 90, "portability": 55, "productivity": 70, "design": 70, "dev": 75},
    "casper": {"gaming": 75, "portability": 70, "productivity": 72, "design": 70, "dev": 73},
}

BRAND_SCORES: Dict[str, float] = {
    "apple": 9.5,
    "lenovo": 9.0,
    "dell": 8.8,
    "asus": 8.5,
    "hp": 8.3,
    "microsoft": 8.5,
    "huawei": 8.0,
    "samsung": 8.0,
    "msi": 8.0,
    "acer": 7.5,
    "monster": 7.0,
    "casper": 6.8,
    "other": 5.0,
}

USAGE_OPTIONS: Dict[int, Tuple[str, str]] = {
    1: ("gaming", "🎮 Oyun"),
    2: ("portability", "💼 Taşınabilirlik"),
    3: ("productivity", "📈 Üretkenlik"),
    4: ("design", "🎨 Tasarım"),
    5: ("dev", "👨‍💻 Yazılım Geliştirme"),
}

BASE_WEIGHTS: Dict[str, float] = {
    "price": 25,
    "performance": 20,
    "ram": 15,
    "storage": 10,
    "brand": 10,
    "brand_purpose": 10,
    "battery": 5,
    "portability": 5,
}

RTX_MODEL_SCORES: Dict[str, float] = {
    "5090": 10.0,
    "5080": 9.5,
    "5070": 9.0,
    "5060": 8.5,
    "5050": 8.0,
    "4090": 9.8,
    "4080": 9.3,
    "4070": 8.8,
    "4060": 8.0,
    "4050": 7.2,
    "3090": 8.9,
    "3080": 8.5,
    "3070": 7.8,
    "3060": 7.0,
    "3050": 6.0,
    "3500": 8.0,
}

GTX_MODEL_SCORES: Dict[str, float] = {"1660": 5.5, "1650": 5.0, "1050": 4.2}

MX_MODEL_SCORES: Dict[str, float] = {
    "570": 4.2,
    "550": 4.0,
    "450": 3.6,
    "350": 3.2,
    "330": 3.0,
}

RX_MODEL_SCORES: Dict[str, float] = {
    "7900": 8.8,
    "7800": 8.3,
    "7700": 7.8,
    "7600": 7.2,
    "7600M": 7.0,
    "6800": 7.5,
    "6700": 7.0,
    "6600": 6.6,
}

IMPORTANCE_MULT: Dict[int, float] = {
    1: 0.5,
    2: 0.75,
    3: 1.0,
    4: 1.5,
    5: 2.0,
}

MIN_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "gaming": {"gpu_score": 6.0, "ram_gb": 16, "cpu_score": 6.5},
    "portability": {"screen_size_max": 14.5, "weight_preference": "light"},
    "productivity": {"ram_gb": 16, "cpu_score": 6.0},
    "design": {"ram_gb": 16, "screen_quality": "high", "gpu_score": 5.0},
    "dev": {"ram_gb": 16, "cpu_score": 7.0, "ssd_gb": 512},
}

# =============================================================================
# CPU / GPU yardımcıları
# =============================================================================


def get_cpu_score(cpu_text: str | float | None) -> float:
    """CPU metninden 0-10 aralığında bir skor üretir."""
    if pd.isna(cpu_text):
        return 5.0

    cpu_lower = str(cpu_text).lower()

    for key, score in CPU_SCORES.items():
        if key in cpu_lower:
            if "hx" in cpu_lower:
                return min(10.0, score + 0.5)
            if " u" in cpu_lower or "-u" in cpu_lower:
                return max(1.0, score - 1.0)
            if " p" in cpu_lower or "-p" in cpu_lower:
                return score - 0.3
            return score

    if "i9" in cpu_lower or "ryzen 9" in cpu_lower:
        return 9.0
    if "i7" in cpu_lower or "ryzen 7" in cpu_lower:
        return 7.5
    if "i5" in cpu_lower or "ryzen 5" in cpu_lower:
        return 6.0
    if "i3" in cpu_lower or "ryzen 3" in cpu_lower:
        return 4.0

    return 5.0


def get_gpu_score(gpu_text: str | float | None) -> float:
    """GPU metninden 0-10 aralığında bir skor üretir."""
    if pd.isna(gpu_text):
        return 2.0

    s = str(gpu_text).lower()

    for kw in [
        "iris xe",
        "iris plus",
        "uhd graphics",
        "hd graphics",
        "radeon graphics",
        "radeon 780m",
        "radeon 760m",
        "radeon 680m",
        "vega 8",
        "vega 7",
        "vega 6",
        "vega 3",
        "integrated",
        "igpu",
        "apu graphics",
    ]:
        if kw in s:
            if "780m" in s or "680m" in s:
                return 3.5
            if "760m" in s or "660m" in s:
                return 3.0
            return 2.5

    arc_match = re.search(r"\barc\s*([a-z]?\d{3,4}m?)\b", s)
    if arc_match:
        code = arc_match.group(1).upper()
        if any(x in code for x in ["A770", "A750"]):
            return 7.5
        if any(x in code for x in ["A570", "A550"]):
            return 6.5
        if any(x in code for x in ["A370", "A350"]):
            return 5.5
        return 3.0

    m = re.search(r"rtx\s*([345]\d{3,4})", s) or re.search(r"rtx(\d{4})", s)
    if m:
        code = m.group(1)
        if code in RTX_MODEL_SCORES:
            return RTX_MODEL_SCORES[code]
        if code.startswith("50"):
            return 8.3
        if code.startswith("40"):
            return 8.0
        if code.startswith("30"):
            return 7.0
        return 6.5

    m = re.search(r"gtx\s*(\d{3,4})", s) or re.search(r"gtx(\d{3,4})", s)
    if m:
        code = m.group(1)
        return GTX_MODEL_SCORES.get(code, 4.5)

    m = re.search(r"\bmx\s*(\d{2,3})\b", s) or re.search(r"mx(\d{2,3})", s)
    if m:
        code = m.group(1)
        return MX_MODEL_SCORES.get(code, 3.5)

    m = re.search(r"\brx\s*(\d{3,4}m?)\b", s.replace(" ", ""))
    if m:
        code = m.group(1).upper()
        base = code.replace("M", "")
        if code in RX_MODEL_SCORES:
            return RX_MODEL_SCORES[code]
        if base in RX_MODEL_SCORES:
            return RX_MODEL_SCORES[base]
        if base.startswith("79"):
            return 8.6
        if base.startswith("78"):
            return 8.2
        if base.startswith("77"):
            return 7.7
        if base.startswith("76"):
            return 7.1
        if base.startswith("67"):
            return 6.9
        if base.startswith("66"):
            return 6.5
        return 5.5

    if re.search(r"\bm4\b", s):
        return 8.5
    if re.search(r"\bm3\b", s):
        return 8.0
    if re.search(r"\bm2\b", s):
        return 7.5
    if re.search(r"\bm1\b", s):
        return 7.0

    if any(x in s for x in ["geforce", "nvidia", "radeon", "discrete"]):
        return 4.0

    return 2.0


def normalize_gpu_model(gpu_text: str | float | None) -> str:
    """Ham GPU metnini okunabilir, tekilleştirilmiş bir etikete çevirir."""
    if pd.isna(gpu_text) or str(gpu_text).strip() == "":
        return "Integrated (generic)"

    s = str(gpu_text).lower().strip()

    m = re.search(r"\brtx[\s\-]?(\d{3,4})(?:\s*(ti|super|max\-q|laptop)?)?\b", s)
    if m:
        num = m.group(1)
        return f"GeForce RTX {num}"

    m = re.search(r"\bgtx[\s\-]?(\d{3,4})(?:\s*(ti|super))?\b", s)
    if m:
        num = m.group(1)
        suf = m.group(2)
        return f"GeForce GTX {num} {suf.upper()}" if suf else f"GeForce GTX {num}"

    m = re.search(r"\bmx[\s\-]?(\d{2,3})\b", s)
    if m:
        return f"NVIDIA MX {m.group(1)}"

    m = re.search(r"\brx[\s\-]?(\d{3,4})(?:\s*([ms]|xt|xtx))?\b", s.replace(" ", ""))
    if m:
        num = m.group(1)
        suf = m.group(2)
        if suf:
            suf = suf.upper()
            return f"Radeon RX {num}{suf}"
        return f"Radeon RX {num}"

    m = re.search(r"\barc[\s\-]?([a-z]?\d{3,4}m?)\b", s)
    if m:
        return f"Intel Arc {m.group(1).upper()}"

    m = re.search(r"\bm([1-4])\b", s)
    if m:
        return f"Apple M{m.group(1)} GPU"

    if "iris xe" in s:
        return "Intel Iris Xe (iGPU)"
    if "iris plus" in s:
        return "Intel Iris Plus (iGPU)"
    if "uhd graphics" in s or "hd graphics" in s or re.search(r"\buhd\b", s):
        return "Intel UHD (iGPU)"

    m = re.search(r"radeon\s*(\d{3})m\b", s)
    if m:
        return f"Radeon {m.group(1)}M (iGPU)"
    m = re.search(r"\bvega\s*(8|7|6|3)\b", s)
    if m:
        return f"Radeon Vega {m.group(1)} (iGPU)"

    if "integrated" in s or "igpu" in s or "apu graphics" in s:
        return "Integrated (generic)"

    if "geforce" in s or "nvidia" in s or "radeon" in s:
        return "Discrete GPU (Unknown)"

    return "GPU (Unlabeled)"


def _cpu_suffix(cpu_text: str) -> str:
    """CPU metninden HX/H/U/P tipini çıkarır."""
    s = (cpu_text or "").lower()
    if "hx" in s:
        return "hx"
    if re.search(r"(?<!h)h(?!x)", s):
        return "h"
    if "-p" in s or " p" in s:
        return "p"
    if "-u" in s or " u" in s:
        return "u"
    if "ultra" in s and re.search(r"\b2\d{2}v\b", s):
        return "p"
    return ""


def _has_dgpu(gpu_norm: str) -> bool:
    """Normalized etiketten cihazda ayrı GPU olup olmadığını çıkarır."""
    s = (gpu_norm or "").lower()
    return not any(k in s for k in ["(igpu)", "integrated", "intel uhd", "iris"])


def _is_nvidia_cuda(gpu_norm: str) -> bool:
    """Normalized etiketten NVIDIA/CUDA varlığını tespit eder."""
    return "rtx" in (gpu_norm or "").lower() or "geforce" in (gpu_norm or "").lower()


def _rtx_tier(gpu_norm: str) -> int:
    """RTX model numarasını döndürür (4060 -> 4060), yoksa 0."""
    m = re.search(r"rtx\s*(\d{4})", (gpu_norm or "").lower())
    return int(m.group(1)) if m else 0


# =============================================================================
# Skorlama yardımcıları
# =============================================================================


def compute_dev_fit(row: pd.Series, dev_mode: str) -> float:
    """
    Bir satırın belirli geliştirme profiline (web/ml/mobile/gamedev/general)
    uygunluğunu 0-100 aralığında hesaplar.
    """
    preset = DEV_PRESETS.get(dev_mode, DEV_PRESETS["general"])
    score = 0.0
    parts = 0.0

    ram = float(row.get("ram_gb", 8) or 8)
    score += min(1.0, ram / preset["min_ram"]) * 20
    parts += 20

    ssd = float(row.get("ssd_gb", 256) or 256)
    score += min(1.0, ssd / preset["min_ssd"]) * 15
    parts += 15

    cpu_suf = _cpu_suffix(str(row.get("cpu", "")))
    score += max(0.0, preset["cpu_bias"].get(cpu_suf, 0.0)) * 4
    parts += 4

    gpu_norm = str(row.get("gpu_norm", ""))
    has_dgpu = _has_dgpu(gpu_norm)
    if preset["need_dgpu"] and not has_dgpu:
        return 0.0
    if preset["need_cuda"] and not _is_nvidia_cuda(gpu_norm):
        return 0.0

    base_gpu = float(row.get("gpu_score", 3.0) or 3.0)
    gpu_pts = min(1.0, base_gpu / 8.0) * 20

    tier = _rtx_tier(gpu_norm)
    if dev_mode == "ml":
        if tier >= 4060:
            gpu_pts += 5
        elif tier >= 4050:
            gpu_pts += 3
        elif has_dgpu:
            gpu_pts += 1
    if dev_mode == "gamedev":
        if tier >= 4070:
            gpu_pts += 6
        elif tier >= 4060:
            gpu_pts += 4
        elif tier >= 4050:
            gpu_pts += 2
    if dev_mode in ["web", "general"] and has_dgpu:
        gpu_pts -= 1.5
    if dev_mode == "mobile" and has_dgpu:
        gpu_pts -= 2.5

    gpu_pts = max(0.0, min(25.0, gpu_pts))
    score += gpu_pts
    parts += 25

    screen = float(row.get("screen_size", 15.6) or 15.6)
    if screen <= 13.6:
        port_bonus = preset["port_bias"].get("<=13.6", 0.0)
    elif screen <= 14.5:
        port_bonus = preset["port_bias"].get("<=14.5", preset["port_bias"].get("<=14", 0.0))
    elif screen <= 15.6:
        port_bonus = preset["port_bias"].get("<=15.6", 0.0)
    elif screen > 16:
        port_bonus = preset["port_bias"].get(">16", -0.2)
    else:
        port_bonus = preset["port_bias"].get("15-16", 0.0)

    size_ok = 1.0 if screen <= preset["screen_max"] else 0.7
    score += size_ok * 10 + (port_bonus * 10)
    parts += 20

    os_val = str(row.get("os", "freedos")).lower()
    os_mult = preset["prefer_os"].get(os_val, 0.98)
    score *= os_mult

    if any(k in gpu_norm.lower() for k in ["apple m1", "apple m2", "apple m3", "apple m4"]):
        if dev_mode in ["mobile", "general", "web"]:
            score += 3.0

    scaled = (score / parts) * 100 if parts else 0.0
    return float(np.clip(scaled, 0.0, 100.0))


def get_dynamic_weights(usage_key: str) -> Dict[str, float]:
    """Kullanım amacına göre ağırlıkları üretir ve 100'e normalize eder."""
    weights = BASE_WEIGHTS.copy()

    if usage_key == "gaming":
        weights.update(
            {
                "performance": 40,
                "ram": 15,
                "storage": 10,
                "battery": 3,
                "portability": 2,
                "price": 15,
                "brand": 7,
                "brand_purpose": 8,
            }
        )
    elif usage_key == "portability":
        weights.update(
            {
                "performance": 10,
                "ram": 10,
                "storage": 8,
                "battery": 20,
                "portability": 25,
                "price": 15,
                "brand": 6,
                "brand_purpose": 6,
            }
        )
    elif usage_key == "productivity":
        weights.update(
            {
                "performance": 25,
                "ram": 20,
                "storage": 12,
                "battery": 8,
                "portability": 8,
                "price": 15,
                "brand": 6,
                "brand_purpose": 6,
            }
        )
    elif usage_key == "design":
        weights.update(
            {
                "performance": 22,
                "ram": 18,
                "storage": 15,
                "battery": 10,
                "portability": 10,
                "price": 12,
                "brand": 7,
                "brand_purpose": 6,
            }
        )
    elif usage_key == "dev":
        weights.update(
            {
                "performance": 28,
                "ram": 22,
                "storage": 15,
                "battery": 8,
                "portability": 7,
                "price": 12,
                "brand": 4,
                "brand_purpose": 4,
            }
        )

    total = sum(weights.values())
    if total > 0:
        factor = 100.0 / total
        for key in list(weights.keys()):
            weights[key] = weights[key] * factor

    return weights


def calculate_score(row: pd.Series, preferences: Dict[str, Any]) -> Tuple[float, str]:
    """Tek bir laptop satırı için toplam puanı ve açıklamasını döndürür."""
    score_parts: Dict[str, float] = {}
    usage_key = preferences.get("usage_key", "productivity")
    prod_profile = preferences.get("productivity_profile", "office")
    weights = get_dynamic_weights(usage_key)

    price = float(row["price"])
    min_b = float(preferences["min_budget"])
    max_b = float(preferences["max_budget"])
    if min_b <= price <= max_b:
        price_range = max_b - min_b
        if price_range > 0:
            price_score = 100 * (1 - (price - min_b) / price_range)
        else:
            price_score = 100.0
        mid = (min_b + max_b) / 2
        distance = abs(price - mid) / (price_range / 2) if price_range > 0 else 0
        mid_bonus = max(0.0, (1 - distance) * 4)
        price_score = min(100.0, price_score * 0.95 + mid_bonus)
    else:
        penalty = (min_b - price) / min_b if price < min_b else (price - max_b) / max_b
        price_score = max(0.0, 50 * (1 - penalty))
    score_parts["price"] = price_score * weights["price"] / 100

    cpu_score = row.get("cpu_score", 5.0)
    gpu_score = row.get("gpu_score", 3.0)
    cpu_w, gpu_w = 0.7, 0.3
    if usage_key == "gaming":
        cpu_w, gpu_w = 0.3, 0.7
    elif usage_key == "design":
        cpu_w, gpu_w = 0.5, 0.5
    elif usage_key == "portability":
        cpu_w, gpu_w = 0.8, 0.2
    elif usage_key in ["dev", "productivity"]:
        # Ported from main_recommender.py: multitask üretkenlikte CPU'ya daha fazla ağırlık ver
        if usage_key == "productivity" and prod_profile == "multitask":
            cpu_w, gpu_w = 0.85, 0.15
    perf_score = (cpu_score * cpu_w + gpu_score * gpu_w) * 10
    score_parts["performance"] = perf_score * weights["performance"] / 100

    ram_gb = row.get("ram_gb", 8)
    if ram_gb >= 64:
        ram_score = 100
    elif ram_gb >= 32:
        ram_score = 90
    elif ram_gb >= 24:
        ram_score = 80
    elif ram_gb >= 16:
        ram_score = 70
    elif ram_gb >= 12:
        ram_score = 55
    elif ram_gb >= 8:
        ram_score = 40
    else:
        ram_score = 20
    score_parts["ram"] = ram_score * weights["ram"] / 100

    ssd_gb = row.get("ssd_gb", 256)
    if ssd_gb >= 2048:
        storage_score = 100
    elif ssd_gb >= 1024:
        storage_score = 85
    elif ssd_gb >= 512:
        storage_score = 70
    elif ssd_gb >= 256:
        storage_score = 50
    else:
        storage_score = 30
    score_parts["storage"] = storage_score * weights["storage"] / 100

    brand = row.get("brand", "other")
    brand_score = BRAND_SCORES.get(brand, 5.0) * 10
    score_parts["brand"] = brand_score * weights["brand"] / 100

    brand_purpose = BRAND_PARAM_SCORES.get(brand, {}).get(usage_key, 70)
    score_parts["brand_purpose"] = brand_purpose * weights["brand_purpose"] / 100

    screen_size = row.get("screen_size", 15.6)
    battery_score = 50
    cpu_text = str(row.get("cpu", "")).lower()
    if any(x in cpu_text for x in ["m1", "m2", "m3", "m4"]):
        battery_score += 30
    elif re.search(r"i[3579]-\d+u", cpu_text) or cpu_text.endswith("-u"):
        battery_score += 20
    elif re.search(r"i[3579]-\d+p", cpu_text) or "-p" in cpu_text:
        battery_score += 10
    elif "hx" in cpu_text or cpu_text.endswith("-hx"):
        battery_score -= 20
    elif re.search(r"i[3579]-\d+h(?!x)", cpu_text) or cpu_text.endswith("-h") or " h " in cpu_text:
        battery_score -= 10
    elif "ryzen" in cpu_text and (" u" in cpu_text or cpu_text.endswith("u")):
        battery_score += 20
    elif "ryzen" in cpu_text and "hs" in cpu_text:
        battery_score += 5
    elif "ryzen" in cpu_text and (
        "hx" in cpu_text or ((" h" in cpu_text or cpu_text.endswith("h")) and "hs" not in cpu_text)
    ):
        battery_score -= 15
    elif "ultra" in cpu_text:
        battery_score += 15

    if gpu_score < 3:
        battery_score += 15
    elif gpu_score > 7:
        battery_score -= 20
    elif gpu_score > 5:
        battery_score -= 10
    battery_score = max(0, min(100, battery_score))
    score_parts["battery"] = battery_score * weights["battery"] / 100

    portability_score = 50
    if screen_size <= 13:
        portability_score += 40
    elif screen_size <= 14:
        portability_score += 30
    elif screen_size <= 15:
        portability_score += 10
    elif screen_size >= 17:
        portability_score -= 30
    else:
        portability_score -= 10
    if gpu_score < 3:
        portability_score += 10
    elif gpu_score > 7:
        portability_score -= 15
    portability_score = max(0, min(100, portability_score))
    score_parts["portability"] = portability_score * weights["portability"] / 100

    os_val = row.get("os", "freedos")
    os_multiplier = 1.0
    if usage_key == "gaming":
        os_multiplier = 1.0
    elif usage_key in ["design", "dev"]:
        if os_val == "macos":
            os_multiplier = 1.05
        elif os_val == "windows":
            os_multiplier = 1.03
        elif os_val == "linux":
            os_multiplier = 1.02
        elif os_val == "freedos":
            os_multiplier = 0.95
    elif usage_key == "productivity":
        if os_val in ["windows", "macos"]:
            os_multiplier = 1.02
        elif os_val == "freedos":
            os_multiplier = 0.97

    total_score = sum(score_parts.values()) * os_multiplier
    total_score = min(100.0, max(0.0, total_score))

    if usage_key == "dev":
        dev_mode = preferences.get("dev_mode", "general")
        dev_fit = compute_dev_fit(row, dev_mode)
        total_score = 0.7 * total_score + 0.3 * dev_fit
        total_score = min(100.0, max(0.0, total_score))

    breakdown = " | ".join(f"{k}:{v:.1f}" for k, v in score_parts.items())
    return total_score, breakdown


def filter_by_usage(df: pd.DataFrame, usage_key: str, preferences: Dict[str, Any]) -> pd.DataFrame:
    """Kullanım amacına göre ön filtreleme uygular."""
    filtered = df.copy()

    if usage_key == "gaming":
        min_needed = float(preferences.get("min_gpu_score_required", 6.0))
        if "gpu_score" in filtered.columns:
            filtered = filtered[filtered["gpu_score"] >= min_needed]
        if "ram_gb" in filtered.columns:
            filtered = filtered[filtered["ram_gb"] >= 8]

    elif usage_key == "portability":
        if "screen_size" in filtered.columns:
            filtered = filtered[filtered["screen_size"] <= 14.5]
        if len(filtered) > 50 and "gpu_score" in filtered.columns:
            filtered = filtered[filtered["gpu_score"] <= 5.0]
        elif len(filtered) > 30 and "gpu_score" in filtered.columns:
            filtered = filtered[filtered["gpu_score"] <= 6.0]

    elif usage_key == "productivity":
        if "ram_gb" in filtered.columns:
            filtered = filtered[filtered["ram_gb"] >= 8]
        if "cpu_score" in filtered.columns:
            filtered = filtered[filtered["cpu_score"] >= 5.0]

    elif usage_key == "design":
        if "ram_gb" in filtered.columns:
            filtered = filtered[filtered["ram_gb"] >= 16]
        if "gpu_score" in filtered.columns:
            filtered = filtered[filtered["gpu_score"] >= 4.0]
        if "screen_size" in filtered.columns:
            filtered = filtered[filtered["screen_size"] >= 14.0]

    elif usage_key == "dev":
        if "ram_gb" in filtered.columns:
            filtered = filtered[filtered["ram_gb"] >= 16]
        if "cpu_score" in filtered.columns:
            filtered = filtered[filtered["cpu_score"] >= 6.0]
        if "ssd_gb" in filtered.columns:
            filtered = filtered[filtered["ssd_gb"] >= 256]

        dev_mode = preferences.get("dev_mode", "general")
        preset = DEV_PRESETS.get(dev_mode, DEV_PRESETS["general"])
        if "ram_gb" in filtered.columns:
            filtered = filtered[filtered["ram_gb"] >= preset["min_ram"]]
        if "ssd_gb" in filtered.columns:
            filtered = filtered[filtered["ssd_gb"] >= preset["min_ssd"]]
        if "screen_size" in filtered.columns:
            filtered = filtered[filtered["screen_size"] <= preset["screen_max"]]

        if preset.get("need_dgpu") or preset.get("need_cuda"):
            if "gpu_norm" in filtered.columns:
                filtered = filtered[filtered["gpu_norm"].apply(_has_dgpu)]
                if preset.get("need_cuda"):
                    filtered = filtered[filtered["gpu_norm"].apply(_is_nvidia_cuda)]

    if len(filtered) < 5 and len(df) > 5:
        if usage_key == "gaming" and "gpu_score" in df.columns:
            return df[df["gpu_score"] >= 5.0]
        if usage_key == "portability" and "screen_size" in df.columns:
            return df[df["screen_size"] <= 15.6]
        if usage_key in ["design", "dev"] and "ram_gb" in df.columns:
            return df[df["ram_gb"] >= 12]
        return df

    return filtered


def get_recommendations(
    df: pd.DataFrame, preferences: Dict[str, Any], top_n: int = 5
) -> pd.DataFrame:
    """
    Bütçe ve kullanım amacına göre skorlayıp sıralanmış öneriler döndürür.
    Çıktı DataFrame'ine skor ve breakdown ekler, attrs ile meta taşır.
    """
    usage_key = preferences.get("usage_key", "productivity")
    usage_label = preferences.get("usage_label", "")

    min_budget = float(preferences.get("min_budget", 0))
    max_budget = float(preferences.get("max_budget", np.inf))
    budget_filtered = df[(df["price"] >= min_budget) & (df["price"] <= max_budget)].copy()

    if budget_filtered.empty:
        return pd.DataFrame()

    filtered = filter_by_usage(budget_filtered, usage_key, preferences)

    if usage_key == "gaming" and not filtered.empty:
        min_gpu = float(preferences.get("gaming_min_gpu", preferences.get("min_gpu_score_required", 6.0)))
        if "gpu_score" in filtered.columns:
            filtered = filtered[filtered["gpu_score"] >= min_gpu]
        if filtered.empty:
            return pd.DataFrame()

    if "url" in filtered.columns:
        filtered = filtered.drop_duplicates(subset=["url"], keep="first")
    filtered = filtered.drop_duplicates(subset=["name", "price"], keep="first")

    if filtered.empty:
        return pd.DataFrame()

    scores: List[float] = []
    breakdowns: List[str] = []
    for _, row in filtered.iterrows():
        score, breakdown = calculate_score(row, preferences)
        scores.append(score)
        breakdowns.append(breakdown)
    filtered["score"] = scores
    filtered["score_breakdown"] = breakdowns

    filtered = filtered.sort_values(by=["score", "price"], ascending=[False, True])

    recommendations: List[pd.Series] = []
    seen_brands: set[str] = set()
    for _, row in filtered.iterrows():
        brand = row.get("brand")
        if len(recommendations) < 3:
            if brand not in seen_brands or len(recommendations) < 2:
                recommendations.append(row)
                seen_brands.add(brand)
        else:
            recommendations.append(row)
        if len(recommendations) >= top_n:
            break

    result_df = pd.DataFrame(recommendations)
    if not result_df.empty:
        result_df.attrs["usage_label"] = usage_label
        result_df.attrs["avg_score"] = result_df["score"].mean()
        result_df.attrs["price_range"] = (result_df["price"].min(), result_df["price"].max())

    return result_df
