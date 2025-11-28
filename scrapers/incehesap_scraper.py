# incehesap_scraper.py
# İncehesap notebook kategorisini tarar:
#   URL: https://www.incehesap.com/notebook-fiyatlari/
#
# Özellikler:
# - Sayfalama (1..N) – N tahmini için hem pagination okuması hem de "ürün kalmadı" fallback'i var
# - Dayanıklı seçiciler (site sınıfları değişirse alternatif yollar)
# - Ürün detay sayfasına gidip temel teknik özellikleri toparlama (başlık + özellikler tablosu/ listesi)
# - Fiyat parsing (₺, ., , varyantları), stok bilgisi çıkarımı, marka/model ayrıştırma
# - Çıktı: pandas DataFrame ve/veya CSV (incehesap_laptops.csv)
#
# Not: Site HTML yapıları değişebilir. Kod, birden fazla olası seçiciyi dener ve mümkün olduğunca
#     kırılmadan veri toplamaya çalışır.

import re
import time
import math
import random
import logging
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

# ------------------------------------------------------------------------------
# AYARLAR
# ------------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.absolute()
START_URL = "https://www.incehesap.com/notebook-fiyatlari/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
        "Gecko/20100101 Firefox/121.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr,en-US;q=0.7,en;q=0.3",
    "Connection": "keep-alive",
}

# Varsayılan bekleme aralıkları
DELAY_SEC_RANGE = (1.0, 2.2)

CSV_PATH = BASE_DIR / "incehesap_laptops.csv"

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("InceHesapScraper")


# ------------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR (PARSE/ NORMALIZE)
# ------------------------------------------------------------------------------
def _normalize_turkish(text: str) -> str:
    """Türkçe karakter normalizasyonu: İ→I, i̇→i"""
    if not text:
        return ""
    # Türkçe İ ve ı karakterlerini düzelt
    text = text.replace("İ", "I").replace("ı", "i").replace("i̇", "i")
    return text


# ===================== CPU/GPU NORMALİZASYON =====================

def normalize_cpu_family(cpu: str) -> str:
    """
    Tam modelden aile etiketine indirger:
    'Intel Core i5-13500H' -> 'i5', 'i7-1360P' -> 'i7', 'Ryzen 7 7840HS' -> 'ryzen7',
    'Apple M3' -> 'm3', 'Core Ultra 7' -> 'ultra7', 'Core 7 240H' -> 'core7'
    """
    if not cpu:
        return ""
    s = _normalize_turkish(cpu.lower())

    # Apple M1..M5
    m = re.search(r"\bm([1-5])\b", s)
    if m:
        return f"m{m.group(1)}"

    # Intel i3/i5/i7/i9
    m = re.search(r"\bi([3579])\b|\bi([3579])-\d", s)
    if m:
        g = m.group(1) or m.group(2)
        return f"i{g}"

    # Intel Core Ultra
    m = re.search(r"core\s*ultra\s*(\d+)", s)
    if m:
        return f"ultra{m.group(1)}"

    # Intel Core (yeni adlandırma): Core 7 240H, Core 5 520H
    m = re.search(r"core\s*([357])\s", s)
    if m:
        return f"core{m.group(1)}"

    # Ryzen 3/5/7/9
    m = re.search(r"ryzen\s*(3|5|7|9)", s)
    if m:
        return f"ryzen{m.group(1)}"

    return s.strip()


def normalize_gpu_tag(gpu: str, title_or_specs: str = "") -> str:
    """
    GPU normalizasyonu - NaN yerine daima geçerli değer döner
    """
    if not gpu or str(gpu).lower() in ['nan', 'none', '']:
        # Apple ürünü kontrolü
        if re.search(r"\b(apple|macbook|mac\s|m[1-5])\b", title_or_specs, re.I):
            return "apple integrated"
        # Gaming laptop ipuçları
        if re.search(r"\b(gaming|oyun|rog|tuf|legion|predator|nitro)\b", title_or_specs, re.I):
            return "integrated"  # Detay bulunamadıysa genel integrated
        return "integrated"

    s = _normalize_turkish(str(gpu).lower())

    # Apple öncelik
    if re.search(r"\b(apple|macbook|m[1-5])\b", title_or_specs, re.I) or "apple" in s:
        return "apple integrated"

    # RTX - boşluksuz format
    m = re.search(r"rtx\s*([0-9]{4})", s)
    if m:
        return f"rtx{m.group(1)}"

    # GTX
    m = re.search(r"gtx\s*([0-9]{4})", s)
    if m:
        return f"gtx{m.group(1)}"

    # Radeon RX
    m = re.search(r"rx\s*([0-9]{4}\w*)", s)
    if m:
        return f"rx{m.group(1)}"

    # AMD Radeon genel
    if "radeon" in s:
        m = re.search(r"radeon\s*([0-9]{3,4}\w*)", s)
        if m:
            return f"rx{m.group(1)}"
        return "integrated"

    # Intel Arc
    if "arc" in s:
        return "intel arc"

    # Intel iGPU
    if any(k in s for k in ["iris", "xe", "uhd", "integrated", "paylaşımlı"]):
        return "integrated"

    # Hiçbir pattern uymadıysa
    return "integrated"


def _clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _parse_price(txt: Optional[str]) -> Optional[float]:
    """
    Geliştirilmiş fiyat parse'ı - daha toleranslı pattern'lar
    """
    if not txt:
        return None

    # Temizlik
    t = txt.replace("\xa0", " ").replace("TL", "").replace("₺", "")
    t = t.replace("TL.", "").replace("₺.", "").strip()

    # Türk formatı: 12.345,67 veya 12.345
    # 1) Hem nokta hem virgül varsa: nokta binlik, virgül ondalık
    if "." in t and "," in t:
        t = t.replace(".", "").replace(",", ".")
    # 2) Sadece virgül varsa ve 2 hane: ondalık (18,99)
    elif "," in t:
        parts = t.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            t = t.replace(",", ".")
        else:
            t = t.replace(",", "")
    # 3) Sadece nokta varsa: binlik ayırıcı (12.345)
    else:
        t = t.replace(".", "")

    # Rakam çıkar
    m = re.search(r"(\d+(?:\.\d{1,2})?)", t)
    if not m:
        return None

    try:
        price = float(m.group(1))
        # Mantıklı aralık: 5.000 - 500.000 TL
        if 5000 <= price <= 500000:
            return price
        # Küçük sayılar bin ile çarp (örn: "35" → 35000)
        elif 10 <= price < 1000:
            price_scaled = price * 1000
            if 5000 <= price_scaled <= 500000:
                return price_scaled
        return None
    except:
        return None


def _extract_brand_model(title: str) -> Tuple[str, str]:
    """Markayı basitçe ilk kelimeden çıkarır; Apple/Msi/MSI/HP/ASUS vb. normalize eder."""
    title_clean = _clean_text(title)
    if not title_clean:
        return "", ""
    parts = title_clean.split()
    brand = parts[0].strip("()[]{}").upper()
    # Bazı marka düzeltmeleri
    brand_map = {
        "MSI": "MSI",
        "ASUS": "ASUS",
        "ACER": "Acer",
        "LENOVO": "Lenovo",
        "HP": "HP",
        "HUAWEI": "Huawei",
        "APPLE": "Apple",
        "DELL": "Dell",
        "MONSTER": "Monster",
        "CASPER": "Casper",
        "HONOR": "Honor",
    }
    brand_norm = brand_map.get(brand, brand.title())
    model = title_clean[len(parts[0]):].strip()
    return brand_norm, model


def _parse_gb(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(\d+)\s*GB", text, re.I)
    if m:
        try:
            return int(m.group(1))
        except:
            return None
    return None


def _parse_screen_inches(text: str) -> Optional[float]:
    """
    Düzeltilmiş ekran boyutu parse'ı:
    - Sadece ondalıklı sayıları (15.6, 16.0) veya açık birim içerenleri kabul et
    - 10-19.5 aralığı dışındakileri None yap
    """
    if not text:
        return None

    # Önce açık birim olanları ara: "15.6''", '15.6"', "15.6 inç", "15.6 inch"
    m = re.search(r"(\d{2}(?:[.,]\d)?)\s*(?:\"|''|inç|inch)", text, re.I)

    # Açık birim yoksa, sadece ondalıklı sayıları kabul et (15.6, 16.0 gibi)
    if not m:
        m = re.search(r"(\d{2}[.,]\d)", text)

    if m:
        v = m.group(1).replace(",", ".")
        try:
            screen_size = float(v)
            # Makul ekran boyutu aralığı: 10-19.5 inç
            if 10.0 <= screen_size <= 19.5:
                return screen_size
            else:
                return None
        except:
            return None
    return None


def _parse_cpu(text: str) -> str:
    if not text:
        return ""

    # Türkçe karakter normalizasyonu
    text_norm = _normalize_turkish(text)

    # Basit kalıplar: i3/i5/i7/i9, Ryzen 5/7/9, M1/M2/M3/M4, Core 7/5
    patterns = [
        r"(i[3579]-?\s?\d{3,5}\w*)",  # i7-1360P vb
        r"(Ryzen\s?\d(?:\s?\d)?)\s?[\w\-]*",  # Ryzen 5 5600H vb (basit)
        r"(Apple\s?M[1-5]\w*)",  # Apple M1/M2/M3/M4
        r"(Core\s?Ultra\s?\d+\w*)",  # Intel Core Ultra
        r"(Core\s?[357]\s?\d{3}\w*)",  # Core 7 240H, Core 5 520H
    ]
    for p in patterns:
        m = re.search(p, text_norm, re.I)
        if m:
            return _clean_text(m.group(0))
    return ""


def _parse_gpu(text: str) -> str:
    if not text:
        return ""

    text_norm = _normalize_turkish(text)

    # RTX/GTX, Radeon, Arc, Apple integrated
    patterns = [
        r"(RTX\s?\d{3,4}\w*\s?(?:Ti|Max-Q|SUPER)?)",
        r"(GTX\s?\d{3,4}\w*)",
        r"(Radeon\s?\w+(?:\s?\d{3,4})?)",
        r"(Arc\s?Graphics?)",  # Intel Arc
        r"(Iris\s?Xe)",
        r"(Apple\s?Integrated)",  # Apple integrated ifadesi
        r"(Apple\s?M[1-5]\w*\s?GPU)",
    ]
    for p in patterns:
        m = re.search(p, text_norm, re.I)
        if m:
            g = _clean_text(m.group(0))
            # Apple cihazlarında "Integrated" yerine Apple Integrated standardı:
            if re.search(r"\b(Apple|MacBook|M[1-5])\b", text_norm, re.I) and ("Integrated" in g or "GPU" in g):
                return "Apple Integrated"
            return g
    # Apple başlıklarında GPU belirtilmiyorsa:
    if re.search(r"\b(Apple|MacBook|Mac)\b", text_norm, re.I):
        return "Apple Integrated"
    return ""


def _parse_storage(text: str) -> Optional[int]:
    """
    Düzeltilmiş depolama parse'ı:
    - Makul aralık kontrolü: 64-12288 GB
    """
    if not text:
        return None
    m = re.search(r"(\d+)\s*TB", text, re.I)
    if m:
        try:
            storage_gb = int(m.group(1)) * 1024
            # Makul depolama aralığı kontrolü
            if 64 <= storage_gb <= 12288:
                return storage_gb
            else:
                return None
        except:
            pass
    m = re.search(r"(\d{3,4})\s*GB", text, re.I)
    if m:
        try:
            storage_gb = int(m.group(1))
            # Makul depolama aralığı kontrolü
            if 64 <= storage_gb <= 12288:
                return storage_gb
            else:
                return None
        except:
            pass
    return None


def _parse_os(text: str) -> str:
    """
    Düzeltilmiş işletim sistemi parse'ı:
    - W11, W11P, W11 Pro varyantlarını yakala
    """
    if not text:
        return ""

    text_norm = _normalize_turkish(text)

    if re.search(r"Free\s?DOS|Freedos", text_norm, re.I):
        return "FreeDOS"
    elif re.search(r"Windows\s?11|Win11|\bW11(?:P|Pro)?\b", text_norm, re.I):
        return "Windows 11"
    elif re.search(r"Windows\s?10|Win10|\bW10\b", text_norm, re.I):
        return "Windows 10"
    elif re.search(r"Mac\s?OS|macOS|Sonoma|Ventura|Monterey", text_norm, re.I):
        return "macOS"
    elif re.search(r"Ubuntu|Linux", text_norm, re.I):
        return "Linux"

    return ""


def _guess_stock(texts: List[str]) -> str:
    """Basit stok çıkarımı: 'Tükendi', 'Stokta var', 'Aynı gün kargo' vb."""
    blob = " ".join(_clean_text(t) for t in texts if t)
    if re.search(r"tükendi|stokta yok", blob, re.I):
        return "out_of_stock"
    if re.search(r"stokta|aynı gün|hızlı kargo|kargoya verilir", blob, re.I):
        return "in_stock"
    return "unknown"


# ------------------------------------------------------------------------------
# SCRAPER SINIFI
# ------------------------------------------------------------------------------

class InceHesapLaptopScraper:
    def __init__(
            self,
            start_url: str = START_URL,
            headers: Dict[str, str] = None,
            delay_range: Tuple[float, float] = DELAY_SEC_RANGE,
            session: Optional[requests.Session] = None,
            max_pages: Optional[int] = None,
    ):
        self.start_url = start_url
        self.headers = headers or HEADERS
        self.delay_range = delay_range
        self.session = session or requests.Session()
        self.max_pages = max_pages
        self._page_pattern = None

        # Anahtar alanlar
        self.results: List[Dict[str, Any]] = []

    # ----------------------- HTTP -----------------------

    def _sleep(self):
        time.sleep(random.uniform(*self.delay_range))

    def _get(self, url: str) -> Optional[requests.Response]:
        try:
            resp = self.session.get(url, headers=self.headers, timeout=20)
            if resp.status_code == 200:
                return resp
            log.warning(f"GET {url} -> {resp.status_code}")
        except requests.RequestException as e:
            log.warning(f"Request error {url}: {e}")
        return None

    # ----------------------- SAYFALAMA -----------------------

    def _detect_total_pages(self, soup: BeautifulSoup) -> int:
        """
        Pagination yapısından toplam sayfa sayısını bulmaya çalışır.
        Bulamazsa 1 döner; ayrıca döngü 'ürün yok' durumunda kendini durdurur.
        """
        # Yaygın pagination varyantları
        candidates = [
            ("ul", {"class": re.compile(r"(pagination|pager)")}),
            ("nav", {"class": re.compile(r"pagination")}),
            ("div", {"class": re.compile(r"pagination")}),
        ]
        pages = []
        for tag, attrs in candidates:
            pag = soup.find(tag, attrs=attrs)
            if not pag:
                continue
            for a in pag.find_all("a", href=True):
                txt = _clean_text(a.get_text(" "))
                if txt.isdigit():
                    pages.append(int(txt))
        if pages:
            return max(pages)
        return 1

    def _page_url(self, page: int) -> str:
        if page <= 1:
            return self.start_url
        # İncehesap genelde /?page=2 veya /s=2 gibi query kullanır; güvenli yaklaşım:
        sep = "&" if "?" in self.start_url else "?"
        return f"{self.start_url}{sep}page={page}"

    # ----------------------- SAYFALAMA YARDIMCILARI (YENİ) -----------------------

    def _find_next_link(self, soup: BeautifulSoup) -> Optional[str]:
        # rel="next"
        a = soup.find("a", rel=lambda v: v and "next" in v.lower())
        if a and a.get("href"):
            return urljoin(self.start_url, a["href"])
        # "Sonraki", "İleri", "Next", "›", ">"
        for txt in ["Sonraki", "İleri", "Next", "›", ">"]:
            a = soup.find("a", string=re.compile(rf"^\s*{re.escape(txt)}\s*$", re.I))
            if a and a.get("href"):
                return urljoin(self.start_url, a["href"])
        # pagination içinden aktifin yanındaki
        pag = soup.find(["ul", "nav", "div"], class_=re.compile(r"pagination|pager", re.I))
        if pag:
            current = pag.find(["li", "a"], class_=re.compile(r"active|current", re.I))
            if current:
                nxt = current.find_next("a", href=True)
                if nxt:
                    return urljoin(self.start_url, nxt["href"])
            # sayı linkleri
            nums = []
            for a in pag.find_all("a", href=True):
                t = (a.get_text(" ") or "").strip()
                if t.isdigit():
                    nums.append((int(t), urljoin(self.start_url, a["href"])))
            if nums:
                nums.sort()
                return nums[-1][1]
        return None

    def _discover_pagination_pattern(self, first_soup: BeautifulSoup) -> None:
        # 1) explicit next link varsa
        nxt = self._find_next_link(first_soup)
        if nxt:
            self._page_pattern = ("absolute", nxt)  # tam URL'yi takip et
            return

        # 2) deneme-yanılma kalıpları
        base = self.start_url.rstrip("/")
        candidates = [
            f"{base}?page={{p}}",
            f"{base}?s={{p}}",
            f"{base}?p={{p}}",
            f"{base}&page={{p}}" if "?" in base else None,
            f"{base}/page-{{p}}/",
            f"{base}/sayfa/{{p}}/",
        ]
        candidates = [c for c in candidates if c]

        for cand in candidates:
            test_url = cand.format(p=2)
            resp = self._get(test_url)
            if not resp or resp.status_code != 200:
                continue
            soup2 = BeautifulSoup(resp.text, "html.parser")
            cards = self._select_product_cards(soup2)
            if cards:
                self._page_pattern = ("pattern", cand)
                return

        self._page_pattern = None

    def _build_page_url(self, page: int, first_soup: Optional[BeautifulSoup] = None) -> str:
        if page <= 1:
            return self.start_url
        if not self._page_pattern and first_soup is not None:
            self._discover_pagination_pattern(first_soup)
        if not self._page_pattern:
            sep = "&" if "?" in self.start_url else "?"
            return f"{self.start_url}{sep}page={page}"

        mode, val = self._page_pattern
        if mode == "pattern":
            return val.format(p=page)
        # mode == "absolute" durumunda URL üretmiyoruz; scrape içinde next takip edilir
        return self.start_url

    # ----------------------- LİSTE SAYFASI -----------------------

    def _select_product_cards(self, soup: BeautifulSoup) -> List[BeautifulSoup]:
        """
        Farklı tema/sınıf değişimlerine dayanıklı şekilde kartları yakalamaya çalış.
        """
        selectors = [
            ("div", {"class": re.compile(r"(product-card|productItem|product|prd-card)")}),
            ("li", {"class": re.compile(r"(product|prd)")}),
            ("div", {"data-product-id": True}),
        ]
        cards = []
        for tag, attrs in selectors:
            found = soup.find_all(tag, attrs=attrs)
            cards.extend(found)
        # fallback: kategori içindeki tüm ürün linkleri
        if not cards:
            # çok geniş fallback (href içinde /notebook- veya /urun/ geçen anchorlar)
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r"/urun/|/notebook-|/laptop-", href):
                    cards.append(a)
        # uniq
        seen = set()
        uniq_cards = []
        for c in cards:
            key = id(c)
            if key in seen:
                continue
            seen.add(key)
            uniq_cards.append(c)
        return uniq_cards

    def _extract_card_link_price_title(self, card: BeautifulSoup, base_url: str) -> Tuple[str, Optional[float], str]:
        # Link
        a = None
        # yaygın
        for sel in [
            ("a", {"class": re.compile(r"(product-link|prd-link|title|name)")}),
            ("a", {"href": True}),
        ]:
            a = card.find(*sel)
            if a and a.get("href"):
                break
        href = a["href"] if (a and a.get("href")) else None
        if href and not href.startswith("http"):
            href = urljoin(base_url, href)

        # Başlık
        title = ""
        # başlık sınıfları
        for sel in [
            ("h3", {"class": re.compile(r"(product|prd).*title", re.I)}),
            ("h2", {"class": re.compile(r"(product|prd).*title", re.I)}),
            ("a", {"class": re.compile(r"(title|name)", re.I)}),
            ("div", {"class": re.compile(r"(title|name)", re.I)}),
        ]:
            t = card.find(*sel)
            if t:
                title = _clean_text(t.get_text(" "))
                break
        # fallback: anchor text
        if not title and a:
            title = _clean_text(a.get_text(" "))

        # Fiyat
        price_txt = ""
        for sel in [
            ("div", {"class": re.compile(r"(price|fiyat)", re.I)}),
            ("span", {"class": re.compile(r"(price|fiyat)", re.I)}),
        ]:
            p = card.find(*sel)
            if p:
                price_txt = _clean_text(p.get_text(" "))
                break
        price = _parse_price(price_txt)

        return href or "", price, title

    # ----------------------- ÜRÜN DETAY -----------------------

    def _parse_product_detail(self, url: str) -> Dict[str, Any]:
        """Ürün detay sayfası - geliştirilmiş fiyat extraction"""
        resp = self._get(url)
        if not resp:
            return {}
        soup = BeautifulSoup(resp.text, "html.parser")

        # Ana başlık
        title = ""
        for sel in [
            ("h1", {}),
            ("h2", {"class": re.compile(r"title", re.I)}),
            ("div", {"class": re.compile(r"product.*title|name", re.I)}),
        ]:
            t = soup.find(*sel)
            if t:
                title = _clean_text(t.get_text(" "))
                break

        # Fiyat - çoklu selector
        price = None
        price_selectors = [
            ("div", {"class": re.compile(r"(price|fiyat)", re.I)}),
            ("span", {"class": re.compile(r"(price|fiyat)", re.I)}),
            ("strong", {"class": re.compile(r"(price|fiyat)", re.I)}),
            ("p", {"class": re.compile(r"(price|fiyat)", re.I)}),
        ]

        for sel in price_selectors:
            price_els = soup.find_all(*sel)
            for p in price_els:
                txt = _clean_text(p.get_text(" "))
                parsed = _parse_price(txt)
                if parsed:
                    price = parsed
                    break
            if price:
                break

        # Stok/teslimat
        stock_hints = []
        for sel in [
            ("div", {"class": re.compile(r"(stock|stok)", re.I)}),
            ("div", {"class": re.compile(r"(cargo|kargo|teslim|delivery)", re.I)}),
            ("span", {"class": re.compile(r"(stock|stok|kargo|teslim)", re.I)}),
        ]:
            for el in soup.find_all(*sel):
                stock_hints.append(_clean_text(el.get_text(" ")))
        stock = _guess_stock(stock_hints)

        # Özellikler
        spec_texts = []
        for table in soup.find_all("table"):
            spec_texts.append(_clean_text(table.get_text(" ")))
        for dl in soup.find_all("dl"):
            spec_texts.append(_clean_text(dl.get_text(" ")))
        for ul in soup.find_all("ul", {"class": re.compile(r"(spec|ozellik|özellik|tech|teknik)", re.I)}):
            spec_texts.append(_clean_text(ul.get_text(" ")))
        for div in soup.find_all("div", {"class": re.compile(r"(spec|ozellik|product.*detail|teknik|tech)", re.I)}):
            spec_texts.append(_clean_text(div.get_text(" ")))

        spec_blob = " | ".join([s for s in spec_texts if s])

        # Çıkarımlar
        title_or_specs = f"{title} | {spec_blob}"
        brand, model = _extract_brand_model(title or url)

        cpu = _parse_cpu(title_or_specs)
        gpu = _parse_gpu(title_or_specs)
        ram_gb = _parse_gb(title_or_specs)
        storage_gb = _parse_storage(title_or_specs)
        screen_inch = _parse_screen_inches(title_or_specs)
        os_val = _parse_os(title_or_specs)

        return {
            "product_url": url,
            "title": title,
            "price_try": price,
            "stock_status": stock,
            "brand": brand,
            "model": model,
            "cpu": cpu,
            "gpu": gpu,
            "ram_gb": ram_gb,
            "storage_gb": storage_gb,
            "screen_inch": screen_inch,
            "os": os_val,
        }

    # ----------------------- AKIŞ -----------------------

    # --- class InceHesapLaptopScraper içinde ---

    def _parse_list_page(self, url: str) -> List[Dict[str, Any]]:
        """
        Liste sayfasını çözümler; her karttan ürün linkini alır ve detay
        sayfasına giderek zengin alanları toplar.
        """
        resp = self._get(url)
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = self._select_product_cards(soup)
        if not cards:
            log.info("Kart bulunamadı (liste sayfası boş ya da seçiciler güncellenmeli).")
            return []

        items: List[Dict[str, Any]] = []
        for idx, c in enumerate(cards, 1):
            try:
                link, price, title = self._extract_card_link_price_title(c, base_url=url)
                if not link:
                    continue

                # Detay sayfasına gidip zengin veri çek
                self._sleep()
                detail = self._parse_product_detail(link) or {}

                if not detail:
                    # en azından karttaki başlık/fiyatı kaydet
                    brand, model = _extract_brand_model(title)
                    detail = {
                        "product_url": link,
                        "title": title,
                        "price_try": price,
                        "stock_status": "unknown",
                        "brand": brand,
                        "model": model,
                        "cpu": "",
                        "gpu": "",
                        "ram_gb": None,
                        "storage_gb": None,
                        "screen_inch": None,
                        "os": "",
                    }
                else:
                    # kart fiyatı daha netse, detay boşsa kullan
                    if detail.get("price_try") is None and price is not None:
                        detail["price_try"] = price
                    if not detail.get("title") and title:
                        detail["title"] = title

                items.append(detail)

            except Exception as e:
                log.warning(f"Liste kartı çözümlerken hata (#{idx}): {e}")

        return items

    def scrape(self) -> pd.DataFrame:
        """
        Tüm sayfaları mümkün olduğunca dolaşır ve şu şemayı döndürür:
        url,name,price,screen_size,ssd,cpu,ram,os,gpu
        """
        log.info("İlk sayfa alınıyor...")
        first_url = self._build_page_url(1)
        resp = self._get(first_url)
        if not resp:
            log.error("İlk sayfa alınamadı.")
            return pd.DataFrame(columns=[
                "url", "name", "price", "screen_size", "ssd", "cpu", "ram", "os", "gpu"
            ])
        first_soup = BeautifulSoup(resp.text, "html.parser")

        # 1. sayfa
        page = 1
        seen_urls = set()
        items = self._parse_list_page(first_url)
        for it in items:
            u = it.get("product_url")
            if u and u not in seen_urls:
                self.results.append(it)
                seen_urls.add(u)

        # sayfalama kalıbını keşfet
        self._discover_pagination_pattern(first_soup)

        # absolute next modu
        absolute_next_url = None
        if self._page_pattern and self._page_pattern[0] == "absolute":
            absolute_next_url = self._page_pattern[1]

        # 2..N
        while True:
            if self.max_pages and page >= self.max_pages:
                break
            page += 1

            if absolute_next_url:
                next_url = absolute_next_url
            else:
                next_url = self._build_page_url(page, first_soup=first_soup)

            log.info(f"Sayfa {page} -> {next_url}")
            self._sleep()
            resp = self._get(next_url)
            if not resp or resp.status_code != 200:
                log.info("Sonraki sayfa alınamadı, duruyorum.")
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # absolute modda yeni next'i bul
            if absolute_next_url:
                new_next = self._find_next_link(soup)
                absolute_next_url = new_next  # None olursa bir sonraki turda kırılır

            page_items = self._parse_list_page(next_url)
            if not page_items:
                log.info("Ürün bulunamadı; sayfalama sonlandı.")
                break

            new_count = 0
            for it in page_items:
                u = it.get("product_url")
                if u and u not in seen_urls:
                    self.results.append(it)
                    seen_urls.add(u)
                    new_count += 1

            if new_count == 0:
                log.info("Yeni ürün gelmedi; muhtemelen son sayfa.")
                break

            if absolute_next_url is None and self._page_pattern and self._page_pattern[0] == "absolute":
                log.info("Sonraki link yok; bitti.")
                break

        # --- normalize & şema ---
        raw = pd.DataFrame(self.results)
        if raw.empty:
            return pd.DataFrame(columns=[
                "url", "name", "price", "screen_size", "ssd", "cpu", "ram", "os", "gpu"
            ])

        raw = raw.drop_duplicates(subset=["product_url"]).reset_index(drop=True)

        # Gürültülü satırları filtrele
        raw = raw[~raw["title"].str.contains("ÜRÜN SİLİNECEK", case=False, na=False)].reset_index(drop=True)

        def _title_plus_specs(row):
            parts = [str(row.get("title") or "")]
            for col in ("cpu", "gpu", "os", "model", "brand"):
                v = row.get(col)
                if v:
                    parts.append(str(v))
            return " | ".join(parts)

        blob = raw.apply(_title_plus_specs, axis=1)

        price = pd.to_numeric(raw.get("price_try"), errors="coerce")
        screen_inch = pd.to_numeric(raw.get("screen_inch"), errors="coerce")
        storage_gb = pd.to_numeric(raw.get("storage_gb"), errors="coerce")
        ram_gb = pd.to_numeric(raw.get("ram_gb"), errors="coerce")

        out = pd.DataFrame({
            "url": raw.get("product_url", ""),
            "name": raw.get("title", ""),
            "price": price,
            "screen_size": screen_inch,
            "ssd": storage_gb,
            "cpu": (raw.get("cpu", "")).apply(normalize_cpu_family),
            "ram": ram_gb,
            "os": raw.get("os", ""),
            "gpu": [
                normalize_gpu_tag(str(g or ""), str(b))
                for g, b in zip(raw.get("gpu", "").fillna(""), blob)
            ],
        })

        return out.replace({pd.NA: "", None: ""})


# ------------------------------------------------------------------------------
# DIŞ ARAYÜZ
# ------------------------------------------------------------------------------

def scrape_incehesap(max_pages: Optional[int] = 11, save_csv: bool = True) -> pd.DataFrame:
    """
    Programatik kullanım için yardımcı fonksiyon.
    """
    scraper = InceHesapLaptopScraper(max_pages=max_pages)
    df = scraper.scrape()
    if save_csv and not df.empty:
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
        log.info(f"CSV kaydedildi: {CSV_PATH} (n={len(df)})")
    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="İncehesap Notebook Scraper")
    parser.add_argument("--max-pages", type=int, default=None, help="Opsiyonel: maksimum sayfa sayısı")
    parser.add_argument("--no-save", action="store_true", help="CSV kaydetme")
    parser.add_argument("--min-delay", type=float, default=DELAY_SEC_RANGE[0],
                        help="İstekler arası minimum bekleme (sn)")
    parser.add_argument("--max-delay", type=float, default=DELAY_SEC_RANGE[1],
                        help="İstekler arası maksimum bekleme (sn)")
    args = parser.parse_args()

    # Delay güncelle
    DELAY_SEC_RANGE = (args.min_delay, args.max_delay)

    df = scrape_incehesap(max_pages=args.max_pages, save_csv=not args.no_save)
    if df.empty:
        log.warning("Herhangi bir veri çekilemedi.")
    else:
        log.info(f"Toplam ürün: {len(df)}")