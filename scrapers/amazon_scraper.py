import os, sys, re, time, random, argparse, json
from urllib.parse import urljoin, urlencode
import requests
import pandas as pd
from bs4 import BeautifulSoup

# Playwright yalnız captcha/0 ürün olduğunda devreye girecek
PLAYWRIGHT_AVAILABLE = True
try:
    from playwright.sync_api import sync_playwright
except Exception:
    PLAYWRIGHT_AVAILABLE = False

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
# === BEGIN: main_recommender uyumluluk yardımcıları ===

import math


def _price_to_int_tl(x):
    """
    TR sayısal formatlarını doğru yorumlar:
      - '24.999,00 TL'  -> 24999
      - '18.499 TL'     -> 18499
      - '18,499 TL'     -> 18499  (nadiren görülürse)
      - '18 499,00 TL'  -> 18499 (NBSP dahil)
    """
    if x is None:
        return None
    s = str(x).strip().replace('\u00A0', ' ')  # NBSP -> boşluk

    # Sadece rakam, nokta ve virgül kalsın
    num = ''.join(ch for ch in s if ch.isdigit() or ch in '.,')
    if not num:
        return None

    # Hem nokta hem virgül varsa -> nokta binlik, virgül ondalık
    if '.' in num and ',' in num:
        num = num.replace('.', '').replace(',', '.')  # 24.999,00 -> 24999.00
    else:
        # Sadece virgül varsa; 18,499 gibi (binlik) mi, 18,49 (ondalık) mı?
        if ',' in num and '.' not in num:
            parts = num.split(',')
            # Son parça tam 2 hane ise bunu ondalık kabul edelim (18,49 -> 18.49)
            if len(parts[-1]) == 2:
                num = num.replace('.', '').replace(',', '.')
            else:
                # Aksi halde binlik kabul edip virgülleri kaldır
                num = num.replace(',', '')
        else:
            # Sadece nokta varsa: TR'de genelde binliktir -> kaldır
            num = num.replace('.', '')

    try:
        val = float(num)
        # Gerçekte TL tam sayı; yuvarlayıp int'e çevir
        return int(round(val))
    except:
        return None


def _ram_to_gb(x):
    if x is None: return 8
    s = str(x).upper()
    # 8GB, 16 GB, 8+8GB, (16 GB) gibi
    nums = [int(n) for n in __import__('re').findall(r'(\d+)\s*GB', s)]
    if nums: return max(nums)
    # sadece sayı varsa
    nums = __import__('re').findall(r'\d+', s)
    if nums:
        n = int(nums[0])
        if n in [4, 8, 12, 16, 24, 32, 48, 64, 128]:
            return n
    return 8


def _ssd_to_gb(x):
    if x is None: return 256
    s = str(x).upper()
    m = __import__('re').search(r'(\d+)\s*TB', s)
    if m:
        return int(m.group(1)) * 1024
    m = __import__('re').search(r'(\d+)\s*GB', s)
    if m:
        g = int(m.group(1))
        if g == 1000: return 1024
        if g == 500:  return 512
        return g
    # sadece sayı
    m = __import__('re').search(r'(\d+)', s)
    if m:
        v = int(m.group(1))
        if v == 1: return 1024
        if v in [128, 256, 512, 1024, 2048]:
            return v
    return 256


def _screen_to_float(val):
    if val is None: return 15.6
    s = str(val).lower().replace(',', '.')
    s = __import__('re').sub(r'(\d{2})\s*\.\s*(\d)', r'\1.\2', s)  # "16 . 1" -> "16.1"
    for m in __import__('re').finditer(r'(\d{2}(?:\.\d)?)', s):
        try:
            x = float(m.group(1))
            if 10.0 <= x <= 19.9:
                return x
        except:
            pass
    return 15.6


def _normalize_os(name, os_field, brand_guess=None):
    s_list = []
    if os_field: s_list.append(str(os_field).lower())
    if name:     s_list.append(str(name).lower())
    s = " ".join(s_list)
    if any(k in s for k in ['windows 11', 'win11', 'w11', 'windows 10', 'win10', 'w10', 'windows']):
        return 'windows'
    if any(k in s for k in ['macbook', 'mac ', 'macos', 'os x']) or (brand_guess == 'apple'):
        return 'macos'
    if any(k in s for k in ['ubuntu', 'linux', 'debian']):
        return 'linux'
    if any(k in s for k in ['freedos', 'free dos', 'fdos', ' dos ']):
        return 'freedos'
    return 'freedos'


def _brand_from_name(name):
    if not name: return 'other'
    nl = str(name).lower()
    brands = {
        'apple': ['apple', 'macbook', 'mac '],
        'lenovo': ['lenovo', 'thinkpad', 'ideapad', 'yoga', 'legion'],
        'asus': ['asus', 'rog', 'zenbook', 'vivobook', 'tuf'],
        'dell': ['dell', 'alienware', 'xps', 'inspiron', 'latitude'],
        'hp': ['hp ', 'hewlett', 'omen', 'pavilion', 'elitebook', 'victus', 'omnibook'],
        'msi': ['msi ', 'msi-', 'msi_'],
        'acer': ['acer', 'predator', 'aspire', 'nitro'],
        'microsoft': ['microsoft', 'surface'],
        'huawei': ['huawei', 'matebook'],
        'samsung': ['samsung', 'galaxy book'],
        'monster': ['monster', 'tulpar', 'abra'],
        'casper': ['casper', 'excalibur', 'nirvana'],
    }
    for b, keys in brands.items():
        if any(k in nl for k in keys):
            return b
    return 'other'
def _normalize_os_compat(name, os_field, brand_guess=None):
    """_normalize_os tek argümanlı veya 3 argümanlı olsun, ikisine de uyum sağla."""
    try:
        # 3 argümanlı sürüm varsa bunu çalıştırır
        return _normalize_os(name, os_field, brand_guess)
    except TypeError:
        # Tek argümanlı (sadece os_field alan) sürüm varsa buraya düşer
        return _normalize_os(os_field)

def _normalize_gpu(val):
    if val is None:
        return "integrated"
    s = str(val).lower().strip()
    mapping = {
        "apple integrated": "apple integrated",
        "integrated": "integrated",
        "dahili": "integrated",
        "paylaşımlı": "integrated",
        "intel uhd": "intel uhd",
        "intel hd": "intel uhd",
        "iris xe": "iris xe",
        "iris plus": "iris plus",
        "intel arc": "intel arc",
        "amd vega": "amd vega",
        "amd radeon": "amd radeon",
    }
    for k, v in mapping.items():
        if k in s:
            return v
    # RTX, GTX, MX modellerini normalize et
    m = re.search(r"(rtx|gtx|mx)\s*\d{3,4}", s)
    if m:
        return m.group(0).lower().replace(" ", "")
    return "integrated"


def _normalize_cpu(val):
    if val is None:
        return "i5"
    s = str(val).upper().strip()
    return s.replace("CORE ", "")


def _normalize_os(val):
    if val is None:
        return "FreeDOS"
    s = str(val).lower()
    if "windows 11" in s or "win11" in s or "w11" in s:
        return "Windows 11"
    if "windows 10" in s or "win10" in s or "w10" in s:
        return "Windows 10"
    if "mac" in s:
        return "macOS"
    if "linux" in s or "ubuntu" in s or "debian" in s:
        return "Linux"
    if "chrome" in s:
        return "ChromeOS"
    if "free" in s or "dos" in s:
        return "FreeDOS"
    return "FreeDOS"

# === END: main_recommender uyumluluk yardımcıları ===

class AmazonLaptopScraper:
    def __init__(self):
        # Birkaç gerçekçi UA ve Accept-Language rotasyonu
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        ]
        self.accept_langs = ["tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6", "tr,en-US;q=0.7,en;q=0.5"]
        self.base_url = "https://www.amazon.com.tr"
        self.session = requests.Session()
        self.session.headers.update(self._make_headers())
        self.session.verify = True  # TLS doğrulama açık

        # Opsiyonel proxy desteği (örn. HTTP(S)_PROXY env)
        # export HTTPS_PROXY=http://user:pass@ip:port
        # Windows PowerShell: $env:HTTPS_PROXY="http://..."
        if os.getenv("HTTPS_PROXY"):
            self.session.proxies.update({"https": os.getenv("HTTPS_PROXY")})
        if os.getenv("HTTP_PROXY"):
            self.session.proxies.update({"http": os.getenv("HTTP_PROXY")})

        self.laptops_data = []
        self.consecutive_failures = 0

    def _make_headers(self):
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": random.choice(self.accept_langs),
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def _refresh_headers(self, referer=None):
        h = self._make_headers()
        if referer:
            h["Referer"] = referer
        self.session.headers.clear()
        self.session.headers.update(h)

    def initialize_session(self):
        print("Session başlatılıyor ve cookies alınıyor...")
        try:
            self._refresh_headers()
            r = self.session.get(self.base_url, timeout=20)
            if r.status_code == 200 and not self.check_captcha_or_bot_detection(r.text):
                print(f"✓ Ana sayfa ziyaret edildi. Cookies: {list(self.session.cookies.keys())}")
                time.sleep(random.uniform(1.5, 3.0))
                return True
            print(f"✗ Ana sayfa ziyareti başarısız veya bot sayfası: {r.status_code}")
            return False
        except Exception as e:
            print(f"✗ Session başlatma hatası: {e}")
            return False

    @staticmethod
    def clean_price(price_text):
        if not price_text:
            return None
        # 12.345,67 → 12345.67 | 24.999 TL → 24999
        s = str(price_text)
        s = s.replace("\u00A0", " ").strip()  # non-breaking space
        s = s.replace(".", "").replace(",", "")
        nums = re.findall(r"\d+", s)
        if nums:
            try:
                return float(nums[0])
            except:
                return None
        return None

    @staticmethod
    def check_captcha_or_bot_detection(html_text):
        if not html_text:
            return True
        l = html_text.lower()
        indicators = [
            "captcha", "bot check", "automated access", "unusual traffic",
            "verify you are a human", "güvenlik kontrolü", "doğrulama",
            "/errors/validatecaptcha", "Enter the characters you see below".lower(),
        ]
        return any(x in l for x in indicators)

    def extract_laptop_info(self, title):
        """Enhanced extraction with better patterns and fallback defaults"""
        info = {'screen_size': None, 'ssd': None, 'cpu': None, 'ram': None, 'os': None, 'gpu': None}
        if not title:
            # Default values for empty titles
            info['gpu'] = 'integrated'
            info['os'] = 'FreeDOS'
            info['ram'] = '8GB'
            info['ssd'] = '256GB'
            info['screen_size'] = '15.6"'
            return info

        tl = title.lower()

        # Ekran - Enhanced patterns
        screen_patterns = [
            r'(\d+[\.,]?\d*)\s*(?:inç|inch|")',
            r'(\d+[\.,]?\d*)\s*ekran',
            r'(\d+[\.,]?\d*)["\']',
            r'(\d+[\.,]?\d*)\s*fhd',
            r'(\d+[\.,]?\d*)\s*hd'
        ]
        for pat in screen_patterns:
            m = re.search(pat, title, re.IGNORECASE)
            if m:
                size = m.group(1).replace(",", ".")
                try:
                    size_float = float(size)
                    if 10.0 <= size_float <= 20.0:
                        info['screen_size'] = f'{size}"'
                        break
                except:
                    pass

        # If no screen size found, guess based on product type
        if not info['screen_size']:
            if 'ultrabook' in tl or 'air' in tl:
                info['screen_size'] = '13.3"'
            elif 'gaming' in tl or 'oyun' in tl:
                info['screen_size'] = '15.6"'
            else:
                info['screen_size'] = '15.6"'  # Most common default

        # SSD - Enhanced with more patterns
        ssd_patterns = [
            r'(\d+)\s*(gb|tb)\s*(ssd|m\.2|nvme|pcie)',
            r'(\d+)\s*(gb|tb)\s*ssd',
            r'ssd\s*(\d+)\s*(gb|tb)',
            r'(\d+)(gb|tb)ssd',
            r'(\d+)\s*(gb|tb)\s*(?:depolama|storage)',
            r'(\d+)\s*(?:gb|tb)'  # Fallback - any GB/TB mention
        ]
        for pat in ssd_patterns:
            m = re.search(pat, title, re.IGNORECASE)
            if m:
                size, unit = m.group(1), (m.group(2).upper() if len(m.groups()) > 1 else 'GB')
                info['ssd'] = f"{size}{unit}"
                break

        if not info['ssd']:
            info['ssd'] = '512GB'  # Common default

        # CPU - Enhanced detection with full model names where possible
        cpu_patterns = [
            # Intel patterns with generation detection
            (r'i9[\s-]?(\d+)', lambda m: f"i9-{m.group(1)}" if m.group(1) else "i9"),
            (r'core i9[\s-]?(\d+)?', lambda m: f"i9-{m.group(1)}" if m.group(1) else "i9"),
            (r'i7[\s-]?(\d+)', lambda m: f"i7-{m.group(1)}" if m.group(1) else "i7"),
            (r'core i7[\s-]?(\d+)?', lambda m: f"i7-{m.group(1)}" if m.group(1) else "i7"),
            (r'i5[\s-]?(\d+)', lambda m: f"i5-{m.group(1)}" if m.group(1) else "i5"),
            (r'core i5[\s-]?(\d+)?', lambda m: f"i5-{m.group(1)}" if m.group(1) else "i5"),
            (r'i3[\s-]?(\d+)', lambda m: f"i3-{m.group(1)}" if m.group(1) else "i3"),
            (r'core i3[\s-]?(\d+)?', lambda m: f"i3-{m.group(1)}" if m.group(1) else "i3"),
            # AMD patterns
            (r'ryzen 9[\s-]?(\d+)?', lambda m: f"Ryzen 9 {m.group(1)}" if m.group(1) else "Ryzen 9"),
            (r'ryzen 7[\s-]?(\d+)?', lambda m: f"Ryzen 7 {m.group(1)}" if m.group(1) else "Ryzen 7"),
            (r'ryzen 5[\s-]?(\d+)?', lambda m: f"Ryzen 5 {m.group(1)}" if m.group(1) else "Ryzen 5"),
            (r'ryzen 3[\s-]?(\d+)?', lambda m: f"Ryzen 3 {m.group(1)}" if m.group(1) else "Ryzen 3"),
            # Apple Silicon
            (r'm4', lambda m: "M4"),
            (r'm3', lambda m: "M3"),
            (r'm2', lambda m: "M2"),
            (r'm1', lambda m: "M1"),
            # Intel low-power
            (r'n100', lambda m: "Celeron N100"),
            (r'n4500', lambda m: "Celeron N4500"),
            (r'n4020', lambda m: "Celeron N4020"),
            (r'celeron[\s-]?(\w+)?', lambda m: f"Celeron {m.group(1)}" if m.group(1) else "Celeron"),
            (r'pentium[\s-]?(\w+)?', lambda m: f"Pentium {m.group(1)}" if m.group(1) else "Pentium"),
            # Intel Ultra
            (r'ultra[\s-]?([579])', lambda m: f"Ultra {m.group(1)}"),
        ]

        for pattern, formatter in cpu_patterns:
            m = re.search(pattern, tl, re.IGNORECASE)
            if m:
                info['cpu'] = formatter(m)
                break

        if not info['cpu']:
            # Try to guess from brand
            if 'apple' in tl or 'macbook' in tl:
                info['cpu'] = 'M2'  # Common Apple CPU
            elif 'amd' in tl:
                info['cpu'] = 'Ryzen 5'
            else:
                info['cpu'] = 'i5'  # Most common default

        # RAM - Enhanced extraction
        ram_patterns = [
            r'(\d+)\s*gb\s*(?:ram|ddr|sdram|bellek|memory)',
            r'(\d+)gb\s*ram',
            r'ram\s*(\d+)\s*gb',
            r'(\d+)\s*gb.*bellek',
            r'bellek.*(\d+)\s*gb',
            r'(\d+)\s*gb\s*ddr\d',
            r'(\d+)\s*gb'  # Fallback - any GB mention that's not SSD
        ]
        for pat in ram_patterns:
            m = re.search(pat, title, re.IGNORECASE)
            if m:
                ram_val = m.group(1)
                # Check if this is actually SSD/storage
                if not re.search(rf'{ram_val}\s*(?:gb|tb)\s*(?:ssd|storage|depolama)', tl, re.IGNORECASE):
                    info['ram'] = f"{ram_val}GB"
                    break

        if not info['ram']:
            # Default based on CPU tier
            if info['cpu'] and any(
                    x in str(info['cpu']).lower() for x in ['i7', 'i9', 'ryzen 7', 'ryzen 9', 'm2', 'm3']):
                info['ram'] = '16GB'
            else:
                info['ram'] = '8GB'

        # OS - Enhanced detection
        os_patterns = [
            ("freedos", "FreeDOS"), ("free dos", "FreeDOS"), (" dos ", "FreeDOS"),
            ("windows 11", "Windows 11"), ("win11", "Windows 11"), ("w11", "Windows 11"),
            ("windows 10", "Windows 10"), ("win10", "Windows 10"), ("w10", "Windows 10"),
            ("ubuntu", "Ubuntu"), ("linux", "Linux"),
            ("macos", "macOS"), ("mac os", "macOS"),
            ("chrome os", "ChromeOS"), ("chromeos", "ChromeOS"),
        ]
        for key, val in os_patterns:
            if key in tl:
                info['os'] = val
                break

        if not info['os']:
            # Default based on brand/CPU
            if info['cpu'] and any(x in str(info['cpu']) for x in ['M1', 'M2', 'M3', 'M4']):
                info['os'] = 'macOS'
            elif 'chromebook' in tl:
                info['os'] = 'ChromeOS'
            else:
                info['os'] = 'FreeDOS'  # Common default in TR market

        # GPU - Enhanced detection with RTX 50 series
        gpu_patterns = [
            # RTX 50 series
            ("rtx 5090", "rtx 5090"), ("rtx5090", "rtx 5090"),
            ("rtx 5080", "rtx 5080"), ("rtx5080", "rtx 5080"),
            ("rtx 5070", "rtx 5070"), ("rtx5070", "rtx 5070"),
            ("rtx 5060", "rtx 5060"), ("rtx5060", "rtx 5060"),
            ("rtx 5050", "rtx 5050"), ("rtx5050", "rtx 5050"),
            # RTX 40 series
            ("rtx 4090", "rtx 4090"), ("rtx4090", "rtx 4090"),
            ("rtx 4080", "rtx 4080"), ("rtx4080", "rtx 4080"),
            ("rtx 4070", "rtx 4070"), ("rtx4070", "rtx 4070"),
            ("rtx 4060", "rtx 4060"), ("rtx4060", "rtx 4060"),
            ("rtx 4050", "rtx 4050"), ("rtx4050", "rtx 4050"),
            # RTX 30 series
            ("rtx 3080", "rtx 3080"), ("rtx3080", "rtx 3080"),
            ("rtx 3070", "rtx 3070"), ("rtx3070", "rtx 3070"),
            ("rtx 3060", "rtx 3060"), ("rtx3060", "rtx 3060"),
            ("rtx 3050", "rtx 3050"), ("rtx3050", "rtx 3050"),
            # GTX series
            ("gtx 1660", "gtx 1660"), ("gtx1660", "gtx 1660"),
            ("gtx 1650", "gtx 1650"), ("gtx1650", "gtx 1650"),
            # MX series
            ("mx550", "mx550"), ("mx450", "mx450"), ("mx350", "mx350"),
            # Intel
            ("intel uhd", "intel uhd"), ("intel hd", "intel uhd"),
            ("iris xe", "iris xe"), ("iris plus", "iris plus"),
            ("arc a", "intel arc"),
            # AMD
            ("vega", "amd vega"), ("radeon", "amd radeon"),
            # Generic
            ("uma", "integrated"), ("paylaşımlı", "integrated"),
            ("integrated", "integrated"), ("dahili", "integrated"),
        ]

        gpu_found = False
        for key, val in gpu_patterns:
            if key in tl:
                info['gpu'] = val
                gpu_found = True
                break

        if not gpu_found:
            # Check for gaming indicators
            if any(x in tl for x in ['gaming', 'oyun', 'gamer', 'rog', 'tuf', 'legion', 'predator', 'nitro']):
                # Gaming laptop without specified GPU likely has at least RTX 3050
                info['gpu'] = 'rtx 3050'
            elif any(k in tl for k in ["apple", "macbook", "imac", "m1", "m2", "m3", "m4"]):
                info['gpu'] = "apple integrated"
            else:
                info['gpu'] = "integrated"

        return info

    # ---------- HTTP motoru ----------
    def _http_fetch(self, url, retries=3, backoff=2.0, referer=None):
        last_exc = None
        for i in range(retries):
            try:
                self._refresh_headers(referer=referer)
                r = self.session.get(url, timeout=25)
                if r.status_code in (200, 203):
                    return r
                elif r.status_code in (302, 301, 303):
                    # bazen captcha yönlendirmesi oluyor
                    time.sleep(backoff * (i + 1))
                else:
                    time.sleep(backoff * (i + 1))
            except Exception as e:
                last_exc = e
                time.sleep(backoff * (i + 1))
        if last_exc:
            raise last_exc
        return None

    def scrape_search_page_http(self, page_num=1, search_term="laptop"):
        params = {"k": search_term, "page": page_num}
        url = f"{self.base_url}/s?{urlencode(params)}"
        print(f"\n[HTTP] Sayfa {page_num} istek: {url}")
        try:
            r = self._http_fetch(url)
            if not r:
                print("  ✗ HTTP yanıt alınamadı")
                return None, "error"
            if self.check_captcha_or_bot_detection(r.text):
                print("  ⚠ HTTP -> Bot/CAPTCHA sayfası algılandı.")
                return None, "captcha"

            soup = BeautifulSoup(r.content, "html.parser")
            cards = soup.find_all("div", {"data-component-type": "s-search-result"})
            print(f"  {len(cards)} ürün bulundu (HTTP)")
            data = []
            for idx, card in enumerate(cards, 1):
                # sponsorlu blok atla
                badge = card.select_one("span.s-label-popover-default")
                if badge and "sponsored" in badge.get_text(strip=True).lower():
                    continue

                title_el = card.select_one("h2 a span") or card.select_one("h2 span")
                if not title_el:
                    continue
                name = title_el.get_text(strip=True)

                link_el = card.select_one("h2 a.a-link-normal")
                url = None
                if link_el and link_el.get("href"):
                    url = urljoin(self.base_url, link_el["href"])
                else:
                    asin = card.get("data-asin")
                    if asin:
                        url = f"{self.base_url}/dp/{asin}"
                if not url:
                    continue

                price = None
                price_el = card.select_one("span.a-price > span.a-offscreen")
                if not price_el:
                    price_el = card.select_one("span.a-price-whole")
                if price_el:
                    price = price_el.get_text(strip=True)

                item = {"url": url, "name": name, "price": price}
                item.update(self.extract_laptop_info(name))
                data.append(item)

                if idx == 1:
                    print(f"    ✓ İlk ürün: {name[:60]}...")

            return data, "ok" if data else "empty"
        except Exception as e:
            print(f"  ✗ HTTP hata: {e}")
            return None, "error"

    # ---------- Playwright motoru ----------
    def scrape_search_page_browser(self, page_num=1, search_term="laptop"):
        if not PLAYWRIGHT_AVAILABLE:
            print("  ✗ Playwright mevcut değil (pip install playwright; playwright install).")
            return None, "unavailable"

        params = {"k": search_term, "page": page_num}
        url = f"{self.base_url}/s?{urlencode(params)}"
        print(f"\n[Browser] Sayfa {page_num} istek: {url}")

        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            context = browser.new_context(
                user_agent=random.choice(self.user_agents),
                locale="tr-TR",
                extra_http_headers={"Accept-Language": random.choice(self.accept_langs)},
            )
            if os.getenv("HTTPS_PROXY"):
                # Playwright proxy desteği gerekiyorsa: context kapatıp proxy ile tekrar açılabilir.
                pass

            page = context.new_page()
            try:
                page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(1.5, 3.0))
                page.goto(url, wait_until="domcontentloaded", timeout=45000)

                # İnsan davranışı taklidi – scroll ve random beklemeler
                for _ in range(random.randint(2, 4)):
                    page.mouse.wheel(0, random.randint(800, 1400))
                    time.sleep(random.uniform(0.8, 1.6))

                html = page.content()
                if self.check_captcha_or_bot_detection(html):
                    print("  ⚠ Browser -> Bot/CAPTCHA sayfası algılandı.")
                    context.close();
                    browser.close()
                    return None, "captcha"

                soup = BeautifulSoup(r.content, "html.parser")

                # Güncel selector
                cards = soup.select('div[data-component-type="s-search-result"]')
                if not cards:
                    # Alternatif selector
                    cards = soup.select('div[data-asin][data-index]')

                print(f"  {len(cards)} ürün bulundu (HTTP)")
                data = []
                for idx, card in enumerate(cards, 1):
                    badge = card.select_one("span.s-label-popover-default")
                    if badge and "sponsored" in badge.get_text(strip=True).lower():
                        continue

                    title_el = card.select_one("h2 a span") or card.select_one("h2 span")
                    if not title_el:
                        continue
                    name = title_el.get_text(strip=True)

                    link_el = card.select_one("h2 a.a-link-normal")
                    url = None
                    if link_el and link_el.get("href"):
                        url = urljoin(self.base_url, link_el["href"])
                    else:
                        asin = card.get("data-asin")
                        if asin:
                            url = f"{self.base_url}/dp/{asin}"
                    if not url:
                        continue

                    price = None
                    price_el = card.select_one("span.a-price > span.a-offscreen")
                    if not price_el:
                        price_el = card.select_one("span.a-price-whole")
                    if price_el:
                        price = price_el.get_text(strip=True)

                    item = {"url": url, "name": name, "price": price}
                    item.update(self.extract_laptop_info(name))
                    data.append(item)

                    if idx == 1:
                        print(f"    ✓ İlk ürün: {name[:60]}...")

                context.close();
                browser.close()
                return data, "ok" if data else "empty"

            except Exception as e:
                print(f"  ✗ Browser hata: {e}")
                try:
                    context.close();
                    browser.close()
                except:
                    pass
                return None, "error"

    def scrape_search_page(self, page_num=1, search_term="laptop"):
        # 1) HTTP dene
        data, status = self.scrape_search_page_http(page_num, search_term)
        if status == "ok":
            self.laptops_data.extend(data)
            self.consecutive_failures = 0
            return True
        if status in ("captcha", "empty", "error"):
            # 2) Browser fallback
            print("  → Browser fallback deneniyor...")
            data2, status2 = self.scrape_search_page_browser(page_num, search_term)
            if status2 == "ok":
                self.laptops_data.extend(data2)
                self.consecutive_failures = 0
                return True

            # başarısız
            self.consecutive_failures += 1
            return False

        # Beklenmeyen durum
        self.consecutive_failures += 1
        return False

    def scrape_multiple_pages(self, max_pages=10, search_term="laptop", max_products=None):
        successful_pages = 0
        for page in range(1, max_pages + 1):
            print(f"\n{'=' * 50}\nSayfa {page} taranıyor...")
            if self.consecutive_failures >= 2:
                print(f"\n⚠ Üst üste {self.consecutive_failures} başarısız sayfa. Durduruluyor.")
                break
            if max_products and len(self.laptops_data) >= max_products:
                print(f"\n✓ Maksimum ürün sayısına ({max_products}) ulaşıldı.")
                break

            ok = self.scrape_search_page(page, search_term)
            if ok:
                successful_pages += 1
                print(f"✓ Sayfa {page} başarıyla tarandı")
            else:
                print(f"✗ Sayfa {page} taranamadı")

            wait_time = random.uniform(2.2, 5.5)
            print(f"  ⏰ {wait_time:.1f} sn bekleniyor...")
            time.sleep(wait_time)

        print(f"\n{'=' * 50}\nTarama tamamlandı: {successful_pages} sayfa başarılı")

    def save_to_csv(self, filename='amazon_laptops.csv'):
        """CSV'ye kaydet"""
        import numpy as np
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(script_dir, filename)
        required = ['url', 'name', 'price', 'screen_size', 'ssd', 'cpu', 'ram', 'os', 'gpu']

        if self.laptops_data:
            df = pd.DataFrame(self.laptops_data)
        else:
            df = pd.DataFrame(columns=required)

        # Gerekli kolonlar garanti
        for c in required:
            if c not in df.columns:
                df[c] = None

        # --- NORMALİZASYONLAR TAM OLARAK BURAYA ---
        df['price'] = df['price'].apply(_price_to_int_tl)
        df['gpu'] = df['gpu'].apply(_normalize_gpu)
        df['cpu'] = df['cpu'].apply(_normalize_cpu)

        # Not: kodunda zaten 3 parametreli _normalize_os(name, os_field, brand_guess) var.
        # Onu kullanmak için:
        df['os'] = df.apply(
            lambda r: _normalize_os_compat(r['name'], r['os'], _brand_from_name(r['name'])),
            axis=1
        )
        # -------------------------------------------

        df = df[required]
        df.to_csv(full_path, index=False, encoding="utf-8")
        print(f"✓ {len(df)} satır {full_path} dosyasına kaydedildi")
        return df


def main():
    """Ana çalıştırma fonksiyonu"""
    import argparse

    parser = argparse.ArgumentParser(description="Amazon.com.tr Laptop Scraper")
    parser.add_argument('--search', default='laptop', help='Arama terimi')
    parser.add_argument('--max-pages', type=int, default=10, help='Max sayfa')
    parser.add_argument('--max-products', type=int, help='Max ürün')
    parser.add_argument('--output', default='amazon_laptops.csv', help='Çıktı')
    parser.add_argument('--dry-run', action='store_true', help='Test modu')

    args = parser.parse_args()

    print("🚀 Amazon.com.tr Scraper Başlıyor...")
    print("=" * 60)

    scraper = AmazonLaptopScraper()

    if args.dry_run:
        print("🧪 DRY-RUN modu")
        scraper.laptops_data = [
            {'url': 'test1', 'name': 'Test Laptop', 'price': '10000',
             'screen_size': '15.6"', 'ssd': '512GB', 'cpu': 'i5',
             'ram': '16GB', 'os': 'FreeDOS', 'gpu': 'integrated'}
        ]
    else:
        if not scraper.initialize_session():
            print("⚠ Session başlatılamadı")

        scraper.scrape_multiple_pages(args.max_pages, args.search, args.max_products)

    scraper.save_to_csv(args.output)
    print("\n✅ Tamamlandı!")
# Dosyanın sonunda, sıfır girinti ile:
if __name__ == "__main__":
    main()  # 4 boşluk girinti