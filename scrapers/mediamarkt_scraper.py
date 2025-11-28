import re
import time
from datetime import datetime

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from typing import Optional

LOAD_MORE_LOCATORS = [
    (By.CSS_SELECTOR, "button[data-test*='load-more']"),
    (By.CSS_SELECTOR, "button[data-test*='loadMore']"),
    (By.CSS_SELECTOR, "button[data-test*='show-more']"),
    (
        By.XPATH,
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'urun daha')]",
    ),
    (
        By.XPATH,
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'daha fazla urun')]",
    ),
]


PRODUCT_CARD_LOCATORS = [
    (By.CSS_SELECTOR, "article[data-test='product-tile']"),
    (By.CSS_SELECTOR, "[data-test='product-tile']"),
    (By.TAG_NAME, "article"),
]


def setup_driver():
    """Configure and return a Chrome WebDriver instance."""
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors=yes")
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # Headless icin acmak isterseniz: options.add_argument("--headless")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def close_cookies(driver):
    """Dismiss cookie banner using multiple fallbacks."""
    cookie_locators = [
        (By.ID, "privacy-layer-accept-all-button"),
        (By.CSS_SELECTOR, "button[data-test*='privacy'][data-test*='accept']"),
        (By.CSS_SELECTOR, "button[id*='privacy'][id*='accept']"),
        (
            By.XPATH,
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'kabul et')]",
        ),
        (
            By.XPATH,
            "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reddet')]",
        ),
    ]

    for locator in cookie_locators:
        try:
            btn = WebDriverWait(driver, 8).until(EC.element_to_be_clickable(locator))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.2)
            btn.click()
            time.sleep(0.5)
            return True
        except TimeoutException:
            continue
        except Exception:
            continue

    return False


def find_product_cards(driver):
    """Return product card elements using the first locator that matches."""
    for locator in PRODUCT_CARD_LOCATORS:
        elements = driver.find_elements(*locator)
        if elements:
            return elements
    return []


def wait_for_new_products(driver, previous_count, timeout=15):
    """Wait until the number of product cards increases."""

    def _has_new_cards(active_driver):
        cards = find_product_cards(active_driver)
        if len(cards) > previous_count:
            return cards
        return False

    try:
        return WebDriverWait(driver, timeout).until(_has_new_cards)
    except TimeoutException:
        return None


def _extract_after_label(text: str, label_keywords) -> Optional[str]:
    """Return the substring after a given label (case-insensitive)."""
    text_lower = text.lower()
    for key in label_keywords:
        idx = text_lower.find(key.lower())
        if idx != -1:
            remainder = text[idx + len(key) :].strip(" :-\n\t")
            if remainder:
                return remainder.split("\n")[0].strip()
    return None


def parse_cpu(name: str, specs_text: Optional[str] = None) -> Optional[str]:
    """
    Parse CPU information from product name or specs.
    Returns lower-case normalized string, or None if uncertain.
    """
    blob = f"{name} {specs_text or ''}".lower()

    # Apple M series
    if "macbook" in blob or re.search(r"\bapple m\d", blob):
        m_match = re.search(r"m(\d)(?:\s*(pro|max|ultra))?", blob)
        if m_match:
            base = f"m{m_match.group(1)}"
            suffix = m_match.group(2)
            return f"{base} {suffix}".strip() if suffix else base

    # Snapdragon / ARM PC class
    if "snapdragon" in blob or "x elite" in blob or "x plus" in blob or "x1e" in blob:
        elite = re.search(r"snapdragon\s*x\s*(elite|plus|1e[\w\-]*)", blob)
        if elite:
            return f"snapdragon x {elite.group(1)}".strip()
        snap_full = re.search(r"snapdragon\s*([\w\-]+)", blob)
        if snap_full:
            return f"snapdragon {snap_full.group(1)}".strip()
        return "snapdragon"

    # AMD Ryzen (includes AI variants)
    if "amd" in blob or "ryzen" in blob:
        ai_match = re.search(r"ryzen\s*ai\s*(\d)\s*([\d]{2,4}[a-z]*)?", blob)
        if ai_match:
            series = ai_match.group(1)
            rest = ai_match.group(2) or ""
            return f"ryzen ai {series} {rest}".strip()
        ryzen_match = re.search(r"ryzen\s*([3579])\s*([\d]{3,5}[a-z]*)?", blob)
        if ryzen_match:
            tier = ryzen_match.group(1)
            code = ryzen_match.group(2) or ""
            return f"ryzen {tier} {code}".strip()
        return "ryzen"

    # Intel Ultra
    ultra_match = re.search(r"ultra\s*(\d)\s*([\d]{3}[a-z]*)?", blob)
    if ultra_match:
        family = ultra_match.group(1)
        code = ultra_match.group(2) or ""
        return f"ultra {family} {code}".strip()

    # Intel Core i3/i5/i7/i9
    core_match = re.search(r"(i[3579])[-\s]*([\d]{4,5}[a-z]*)", blob)
    if core_match:
        return f"{core_match.group(1)}-{core_match.group(2)}".lower()

    # Last resort: if we saw Intel keywords but no match
    if "intel" in blob or "core" in blob:
        return "intel"

    return None


def parse_os(name: str, specs_text: Optional[str] = None) -> Optional[str]:
    """Derive OS from specs first, then name heuristics."""
    def normalize_os(os_str: str) -> Optional[str]:
        os_low = os_str.lower()
        if any(x in os_low for x in ["windows 11", "win11", "w11"]):
            return "Windows 11"
        if any(x in os_low for x in ["windows 10", "win10", "w10"]):
            return "Windows 10"
        if "freedos" in os_low or "free dos" in os_low:
            return "FreeDOS"
        if "chrome" in os_low:
            return "ChromeOS"
        if "linux" in os_low or "ubuntu" in os_low:
            return "Linux"
        if "macos" in os_low or "mac os" in os_low or "macbook" in os_low or re.search(r"m\d", os_low):
            return "macOS"
        return None

    if specs_text:
        hint = _extract_after_label(specs_text, ["isletim sistemi", "operating system"])
        if hint:
            parsed = normalize_os(hint)
            if parsed:
                return parsed

    os_from_name = normalize_os(name)
    if os_from_name:
        return os_from_name

    return None


def normalize_gpu(name: str, gpu_raw: str) -> str:
    """Standardize GPU labels, especially for Apple devices."""
    name_low = name.lower()
    if "macbook" in name_low or re.search(r"m[12345]", name_low):
        return "apple integrated"
    return gpu_raw.lower()


def _run_parsing_smoke_tests():
    """Lightweight sanity checks for parser helpers."""
    assert parse_cpu("Apple Macbook Pro Apple M5 islemci") == "m5"
    assert parse_cpu("Lenovo Legion AMD Ryzen 7 8840HS Gaming Laptop") == "ryzen 7 8840hs"
    assert parse_cpu("HP Snapdragon X Elite 80-100") == "snapdragon x elite"
    assert parse_cpu("ASUS Intel Core i7-13620H 16GB") == "i7-13620h"

    assert parse_os("Apple Macbook Air M4") == "macOS"
    assert parse_os("ASUS Gaming W11") == "Windows 11"
    assert normalize_gpu("Apple Macbook Air M4", "integrated") == "apple integrated"


def find_load_more_button(driver, timeout=12):
    """Return a clickable load-more button using several strategies."""
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(0.5)

    for locator in LOAD_MORE_LOCATORS:
        try:
            return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(locator))
        except TimeoutException:
            continue

    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            text = (btn.text or "").strip().lower()
            if any(
                phrase in text
                for phrase in ["ürün daha", "daha fazla ürün", "urun daha", "daha fazla urun", "load more"]
            ):
                return btn
    except Exception:
        pass

    return None


def click_load_more(driver, timeout=12):
    """Try to click the load-more button if it exists."""
    button = find_load_more_button(driver, timeout=timeout)
    if not button:
        return False

    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        time.sleep(0.4)
        button.click()
    except ElementClickInterceptedException:
        try:
            driver.execute_script("arguments[0].click();", button)
        except Exception:
            return False
    except StaleElementReferenceException:
        return False
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", button)
        except Exception:
            return False

    return True


def load_all_products(driver, max_rounds=60, wait_timeout=15):
    """Click the load-more button until no new products arrive."""
    previous_count = len(find_product_cards(driver))
    stagnation_rounds = 0

    for _ in range(max_rounds):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.6)

        clicked = click_load_more(driver, timeout=wait_timeout)
        if not clicked:
            stagnation_rounds += 1
            if stagnation_rounds >= 2:
                print("-> Yuklenecek baska urun bulunamadi (buton gorunmuyor).")
                break
            time.sleep(2)
            continue

        new_cards = wait_for_new_products(driver, previous_count, timeout=wait_timeout)
        if new_cards:
            previous_count = len(new_cards)
            stagnation_rounds = 0
            print(f"-> Su ana kadar {previous_count} urun yüklendi.")
        else:
            stagnation_rounds += 1
            if stagnation_rounds >= 2:
                print("-> Yeni urun gelmedi, yukleme dongusu sonlandiriliyor.")
                break

    return find_product_cards(driver)


def clean_price(price_text):
    """Clean price string and convert it to float."""
    if not price_text:
        return None
    price_text = str(price_text).replace("TL", "").replace(".", "").replace(",", ".")
    price = re.sub(r"[^\d.]", "", price_text)
    try:
        price_float = float(price)
        if 10000 <= price_float <= 500000:
            return price_float
        return None
    except Exception:
        return None


def extract_cpu(name):
    """Backward-compatible CPU extractor; delegates to parse_cpu."""
    return parse_cpu(name)


def extract_gpu(name):
    """Extract GPU information in Amazon-compatible format."""
    name_lower = name.lower()

    if "rtx" in name_lower:
        match = re.search(r"rtx\s*(\d{4})", name_lower)
        if match:
            return normalize_gpu(name, f"rtx{match.group(1)}")
        return normalize_gpu(name, "rtx3050")

    if "gtx" in name_lower:
        match = re.search(r"gtx\s*(\d{4})", name_lower)
        if match:
            return normalize_gpu(name, f"gtx{match.group(1)}")
        return normalize_gpu(name, "integrated")

    if "iris xe" in name_lower:
        return normalize_gpu(name, "iris xe")
    if "intel uhd" in name_lower or "uhd" in name_lower:
        return normalize_gpu(name, "intel uhd")

    if "radeon" in name_lower:
        return normalize_gpu(name, "amd radeon")

    if any(x in name_lower for x in ["m1", "m2", "m3", "m4"]):
        return normalize_gpu(name, "apple integrated")

    return normalize_gpu(name, "integrated")


def extract_ram(name):
    """Extract RAM information."""
    name_lower = name.lower()
    match = re.search(r"(\d+)\s*gb\s*(?:ram|ddr)", name_lower)
    if not match:
        match = re.search(r"(\d+)gb", name_lower)
    if match:
        return f"{match.group(1)}GB"
    return "8GB"


def extract_ssd(name):
    """Extract SSD size information."""
    name_lower = name.lower()

    tb_match = re.search(r"(\d+)\s*tb", name_lower)
    if tb_match:
        return f"{int(tb_match.group(1)) * 1024}GB"

    gb_match = re.search(r"(\d{3,4})\s*gb", name_lower)
    if gb_match:
        size = int(gb_match.group(1))
        if size >= 128:
            return f"{size}GB"

    return "512GB"


def extract_screen_size(name):
    """Extract screen size."""
    name_lower = name.lower()
    patterns = [
        r'(\d{2}[\.,]\d)"',
        r'(\d{2})"',
        r"(\d{2}[\.,]\d)\s*(?:inch|inç)",
    ]

    for pattern in patterns:
        match = re.search(pattern, name_lower)
        if match:
            size = match.group(1).replace(",", ".")
            return f'{size}"'

    return '15.6"'


def extract_os(name):
    """Backward-compatible OS extractor; delegates to parse_os."""
    return parse_os(name)


def scrape_mediamarkt():
    """MediaMarkt laptop scraper that produces Amazon compatible CSV."""
    _run_parsing_smoke_tests()
    print("=" * 60)
    print("MEDIAMARKT LAPTOP SCRAPER")
    print("=" * 60)
    print(f"Baslangic: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)

    driver = setup_driver()
    all_products = []

    try:
        url = "https://www.mediamarkt.com.tr/tr/category/laptop-504926.html"
        print(f"-> URL: {url}")

        driver.get(url)
        time.sleep(3)

        if close_cookies(driver):
            print("-> Cookie bildirimi kapatildi.")
        else:
            print("-> Cookie bildirimi bulunmadi veya kapatilamadi.")

        WebDriverWait(driver, 20).until(lambda d: bool(find_product_cards(d)))

        initial_cards = find_product_cards(driver)
        print(f"-> Ilk yuklemede {len(initial_cards)} urun gorundu.")
        close_cookies(driver)

        articles = load_all_products(driver, max_rounds=80, wait_timeout=18)
        print(f"-> Yukleme tamamlandi, toplam {len(articles)} urun islenecek.")

        for index, article in enumerate(articles, 1):
            try:
                product_data = {}

                article_text = article.text.strip()
                if not article_text:
                    continue

                lines = [line.strip() for line in article_text.split("\n") if line.strip()]
                specs_text = article_text  # lightweight fallback for parsing helpers

                name = ""
                for line in lines:
                    if len(line) > 20 and any(
                        brand in line.lower()
                        for brand in [
                            "asus",
                            "lenovo",
                            "hp",
                            "dell",
                            "acer",
                            "msi",
                            "apple",
                            "macbook",
                            "monster",
                            "casper",
                            "huawei",
                            "samsung",
                            "laptop",
                            "notebook",
                        ]
                    ):
                        name = line
                        break

                if not name:
                    continue

                product_data["name"] = name

                price = None
                for line in lines:
                    if "TL" in line or re.search(r"\d{2}\.\d{3}", line):
                        price = clean_price(line)
                        if price:
                            break

                product_data["price"] = price

                try:
                    link = article.find_element(By.CSS_SELECTOR, "a[href*='/tr/product/']")
                    product_data["url"] = link.get_attribute("href")
                except Exception:
                    product_data["url"] = ""

                product_data["screen_size"] = extract_screen_size(name)
                product_data["ssd"] = extract_ssd(name)
                product_data["cpu"] = parse_cpu(name, specs_text)
                product_data["ram"] = extract_ram(name)
                product_data["os"] = parse_os(name, specs_text)
                product_data["gpu"] = extract_gpu(name)

                if product_data.get("name") and product_data.get("price"):
                    all_products.append(product_data)
                    if len(all_products) % 10 == 0:
                        print(f"  -> {len(all_products)} urun islendi.")

            except Exception:
                continue

        print(f"\n-> Toplam {len(all_products)} gecerli laptop bulundu.")

    except Exception as exc:
        print(f"\n!! Ana hata: {exc}")

    finally:
        driver.quit()

    if all_products:
        df = pd.DataFrame(all_products)

        column_order = ["url", "name", "price", "screen_size", "ssd", "cpu", "ram", "os", "gpu"]
        for col in column_order:
            if col not in df.columns:
                df[col] = ""

        df = df[column_order]
        df = df[df["price"].notna()]
        df = df[df["price"] > 10000]
        df = df.drop_duplicates(subset=["name"], keep="first")

        output_file = "mediamarkt_laptops.csv"
        df.to_csv(output_file, index=False, encoding="utf-8-sig")

        print("\n" + "=" * 60)
        print("ISLEM TAMAMLANDI!")
        print(f"{len(df)} laptop kaydedildi.")
        print(f"Kayit dosyasi: {output_file}")
        print("=" * 60)

        print("\nIlk 5 kayit:")
        print(df.head().to_string())
    else:
        print("\n!! Hic gecerli urun bulunamadi!")


if __name__ == "__main__":
    scrape_mediamarkt()
