import requests
from bs4 import BeautifulSoup
import csv
import re
import time
from urllib.parse import urljoin


class VatanLaptopScraper:
    def __init__(self):
        self.base_url = "https://www.vatanbilgisayar.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.laptops = []

    def get_page(self, url):
        """Sayfa içeriğini al"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            print(f"Sayfa alınamadı: {url} - {e}")
            return None

    def extract_price(self, text):
        """Fiyat bilgisini extract et"""
        if not text:
            return None
        s = str(text).strip().replace('\u00A0', ' ')
        # Rakam, nokta ve virgül haricindeki karakterleri çıkart
        digits = ''.join(ch for ch in s if ch.isdigit() or ch in '.,')
        if not digits:
            return None

        if '.' in digits and ',' in digits:
            normalised = digits.replace('.', '').replace(',', '.')
        elif ',' in digits:
            parts = digits.split(',')
            if len(parts[-1]) == 2:
                normalised = digits.replace('.', '').replace(',', '.')
            else:
                normalised = digits.replace(',', '')
        else:
            normalised = digits.replace('.', '')

        try:
            price = float(normalised)
        except ValueError:
            return None

        if 5_000 <= price <= 500_000:
            return price
        return None

    def extract_screen_size(self, name, specs_text):
        """Ekran boyutunu extract et - İyileştirilmiş versiyon"""
        text = f"{name} {specs_text}"

        # Önce açık "inç/inc/inch" ifadelerini ara (en güvenilir)
        match = re.search(r'(\d{2}[\.,]?\d?)\s*(?:inç|inc|inch|"|\'\')', text, re.IGNORECASE)
        if match:
            size = match.group(1).replace(',', '.')
            try:
                size_float = float(size)
                if 10.0 <= size_float <= 19.5:
                    return f'{size_float}"'
            except:
                pass

        # Fallback: Sadece rakam ama "Nesil" kelimesinden sonra gelmesin
        # "13.Nesil" veya "12.Nesil" gibi ifadeleri atla
        for match in re.finditer(r'(\d{2}[\.,]?\d?)', text):
            # Öncesinde "Nesil" varsa atla
            start = max(0, match.start() - 10)
            context = text[start:match.start()].lower()
            if 'nesil' in context or 'gen' in context:
                continue

            size = match.group(1).replace(',', '.')
            try:
                size_float = float(size)
                # 13" ve üstü kabul et (12.Nesil karışıklığını önler)
                if 13.0 <= size_float <= 19.5:
                    return f'{size_float}"'
            except:
                pass

        return '15.6"'  # Varsayılan

    def extract_ssd(self, name, specs_text):
        """SSD kapasitesini extract et - String formatında"""
        text = f"{name} {specs_text}"

        # TB kontrolü (1TB, 2TB vb.)
        tb_match = re.search(r'(\d+)\s*TB\s*(?:SSD|ssd|NVMe|nvme)?', text, re.IGNORECASE)
        if tb_match:
            size = int(tb_match.group(1)) * 1024
            if size in [1024, 2048, 4096]:
                return f"{size}GB"

        # GB kontrolü (512GB, 1024GB vb.)
        gb_match = re.search(r'(\d+)\s*GB\s*(?:SSD|ssd|NVMe|nvme)', text, re.IGNORECASE)
        if gb_match:
            size = int(gb_match.group(1))
            if size in [128, 256, 512, 1024, 2048, 4096]:
                return f"{size}GB"

        # Alternatif: "1000GB" -> "1024GB" dönüşümü
        storage_match = re.search(r'(\d+)\s*GB', text, re.IGNORECASE)
        if storage_match:
            num = int(storage_match.group(1))
            if num == 1000:
                return "1024GB"
            elif num == 500:
                return "512GB"
            elif num in [128, 256, 512, 1024, 2048, 4096]:
                return f"{num}GB"

        return "512GB"  # Varsayılan

    def extract_cpu(self, name, specs_text):
        """CPU modelini extract et - İyileştirilmiş versiyon"""
        text = f"{name} {specs_text}"

        # Intel Core i-serisi (i3, i5, i7, i9)
        intel_match = re.search(
            r'(?:Intel\s+)?Core\s+(i[3579])[-\s]?(\d{4,5})([A-Z]{0,2})\b',
            text,
            re.IGNORECASE
        )
        if intel_match:
            series = intel_match.group(1).upper()  # I5, I7, I9
            model = intel_match.group(2)
            suffix = intel_match.group(3).upper()
            return f"{series}-{model}{suffix}".strip()

        # Intel Core 5/7/9 (yeni nesil - Core 5 120U gibi)
        core_new_match = re.search(
            r'Core\s+([579])\s+(\d{3})([A-Z]{0,2})\b',
            text,
            re.IGNORECASE
        )
        if core_new_match:
            series = core_new_match.group(1)
            model = core_new_match.group(2)
            suffix = core_new_match.group(3).upper()
            return f"Intel Core {series} {model}{suffix}".strip()

        # Intel Ultra (Ultra 5, Ultra 7, Ultra 9)
        ultra_match = re.search(
            r'(?:Core\s+)?Ultra\s+([579])\s+(\d{3})([A-Z]{0,2})\b',
            text,
            re.IGNORECASE
        )
        if ultra_match:
            series = ultra_match.group(1)
            model = ultra_match.group(2)
            suffix = ultra_match.group(3).upper()
            return f"Intel Ultra {series} {model}{suffix}".strip()

        # AMD Ryzen (Ryzen 3, 5, 7, 9)
        ryzen_match = re.search(
            r'(?:AMD\s+)?Ryzen\s+([3579])\s+(\d{4})([A-Z]{0,3})\b',
            text,
            re.IGNORECASE
        )
        if ryzen_match:
            series = ryzen_match.group(1)
            model = ryzen_match.group(2)
            suffix = ryzen_match.group(3).upper()
            return f"Ryzen {series} {model}{suffix}".strip()

        # AMD Ryzen AI (yeni nesil)
        ryzen_ai_match = re.search(
            r'Ryzen\s+AI\s+([379])\s+(\d{3})\b',
            text,
            re.IGNORECASE
        )
        if ryzen_ai_match:
            return f"Ryzen AI {ryzen_ai_match.group(1)} {ryzen_ai_match.group(2)}"

        # Apple M serisi (M1, M2, M3, M4 + Pro/Max/Ultra)
        m_match = re.search(r'\b(M[1-4])(?:\s+(Pro|Max|Ultra))?\b', text, re.IGNORECASE)
        if m_match:
            base = m_match.group(1).upper()
            variant = f" {m_match.group(2).title()}" if m_match.group(2) else ""
            return f"{base}{variant}"

        # Celeron
        celeron_match = re.search(r'Celeron\s+([A-Z]?\d{4})\b', text, re.IGNORECASE)
        if celeron_match:
            return f"Celeron {celeron_match.group(1)}"

        # Pentium
        pentium_match = re.search(r'Pentium\s+([A-Z]?\d+)\b', text, re.IGNORECASE)
        if pentium_match:
            return f"Pentium {pentium_match.group(1)}"

        # Snapdragon (ARM işlemciler)
        snapdragon_match = re.search(r'Snapdragon\s+X\s+([\w\d\-]+)', text, re.IGNORECASE)
        if snapdragon_match:
            return f"Snapdragon X {snapdragon_match.group(1)}"

        # Intel N-serisi (N100, N4020 vb.)
        n_match = re.search(r'\b(N\d{3,4})\b', text, re.IGNORECASE)
        if n_match:
            return f"Intel {n_match.group(1)}"

        return "Intel Core i5"  # Varsayılan

    def extract_ram(self, name, specs_text):
        """RAM kapasitesini GB cinsinden döndür (GPU VRAM hariç)."""
        text = f"{name} {specs_text}"
        text_lower = text.lower()

        # GPU VRAM ifadelerini temizle (ör: "rtx4050 6gb", "gddr6 8gb", "8gb vram")
        cleaned = re.sub(
            r'(?:rtx|gtx|rx|arc|mx)[\w\s\-]*?\b\d+\s*gb',
            ' ',
            text_lower,
            flags=re.IGNORECASE
        )
        cleaned = re.sub(r'gddr\d?\s*\d+\s*gb', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b\d+\s*gb\s*vram\b', ' ', cleaned, flags=re.IGNORECASE)

        candidates = []
        for match in re.finditer(r'(\d+)\s*gb', cleaned, re.IGNORECASE):
            try:
                value = int(match.group(1))
            except ValueError:
                continue

            if not (4 <= value <= 192):
                continue

            start, end = match.span()
            remainder = cleaned[end:]
            if re.match(r'\s*(?:ssd|emmc|ufs|nvme|hdd|storage)', remainder):
                continue
            prefix = cleaned[max(0, start - 10):start]
            if re.search(r'(?:ssd|emmc|ufs|nvme|hdd|storage)\s*$', prefix):
                continue

            candidates.append(value)

        if candidates:
            return f"{max(candidates)}GB"

        return "8GB"  # Varsayılan

    def extract_os(self, name, specs_text):
        """İşletim sistemini extract et"""
        text = f"{name} {specs_text}".lower()

        # Windows versiyonları
        if 'windows 11' in text or 'win11' in text or 'w11' in text:
            return "Windows 11"
        elif 'windows 10' in text or 'win10' in text or 'w10' in text:
            return "Windows 10"
        elif 'windows' in text:
            return "windows"

        # FreeDOS
        elif any(x in text for x in ['freedos', 'free dos', 'dos', 'fdos']):
            return "FreeDOS"

        # macOS
        elif any(x in text for x in ['macbook', 'macos', 'mac os']):
            return "macOS"

        # Linux
        elif 'linux' in text or 'ubuntu' in text:
            return "linux"

        # Apple ürünü kontrolü (marka bazlı)
        if 'apple' in text or 'macbook' in text or 'mac pro' in text:
            return "macOS"

        return "FreeDOS"  # Varsayılan

    def extract_gpu(self, name, specs_text):
        """GPU modelini extract et - Standart format"""
        text = f"{name} {specs_text}"

        # NVIDIA RTX 50 serisi
        if match := re.search(r'rtx\s*50(90|80|70|60|50)', text, re.IGNORECASE):
            return f"RTX 50{match.group(1)}"

        # NVIDIA RTX 40 serisi
        if match := re.search(r'rtx\s*40(90|80|70|60|50)', text, re.IGNORECASE):
            return f"RTX 40{match.group(1)}"

        # NVIDIA RTX 30 serisi
        if match := re.search(r'rtx\s*30(90|80|70|60|50)', text, re.IGNORECASE):
            return f"RTX 30{match.group(1)}"

        # NVIDIA GTX 16 serisi
        if match := re.search(r'gtx\s*16(60|50)', text, re.IGNORECASE):
            return f"GTX 16{match.group(1)}"

        # NVIDIA GTX 10 serisi
        if match := re.search(r'gtx\s*10(80|70|60|50)', text, re.IGNORECASE):
            return f"GTX 10{match.group(1)}"

        # NVIDIA MX serisi
        if match := re.search(r'mx\s*(570|550|450|350|330|250)', text, re.IGNORECASE):
            return f"MX {match.group(1)}"

        # AMD Radeon RX (discrete)
        if match := re.search(r'(?:rx|radeon)\s*([67])([0-9]00)([M]?)', text, re.IGNORECASE):
            suffix = match.group(3).upper()
            return f"RX {match.group(1)}{match.group(2)}{suffix}"

        # AMD iGPU (780M, 680M, 760M vb.)
        if match := re.search(r'radeon\s*(\d{3})m', text, re.IGNORECASE):
            return f"Radeon {match.group(1)}M"

        # AMD Vega iGPU
        if match := re.search(r'vega\s*(\d{1,2})', text, re.IGNORECASE):
            return f"Radeon Vega {match.group(1)}"

        # Intel Arc
        if match := re.search(r'arc\s*([a-z]?\d{3,4}m?)', text, re.IGNORECASE):
            return f"Intel Arc {match.group(1).upper()}"

        # Intel Iris Xe
        if 'iris xe' in text.lower():
            return "Intel Iris Xe"

        if 'iris plus' in text.lower():
            return "Intel Iris Plus"

        if 'iris' in text.lower():
            return "Intel Iris"

        # Intel UHD
        if 'uhd' in text.lower() or 'hd graphics' in text.lower():
            return "Intel UHD"

        # Apple M serisi GPU (sadece Apple cihazlarda)
        if 'macbook' in text.lower() or 'mac ' in text.lower():
            if match := re.search(r'm([1-4])', text, re.IGNORECASE):
                return f"Apple M{match.group(1)} GPU"

        # Genel integrated (son çare)
        if any(x in text.lower() for x in ['integrated', 'entegre', 'dahili', 'paylaşımlı']):
            return "Integrated"

        return "Integrated"  # Varsayılan

    def scrape_product(self, product_elem):
        """Tek bir ürünü scrape et"""
        try:
            # URL
            link_elem = product_elem.find('a', href=True)
            if not link_elem:
                return None
            url = urljoin(self.base_url, link_elem['href'])

            # Name
            name = ""
            for selector in [
                '.product-list__product-name h3',
                '.product-list__product-name',
                'h3',
            ]:
                elem = product_elem.select_one(selector)
                if elem:
                    name = elem.get_text(" ", strip=True)
                    break

            if not name:
                fallback = product_elem.find('div', class_='product-list__content')
                if fallback:
                    name = fallback.get_text(" ", strip=True)

            # Vatan bazen fiyatı ürün adının sonuna ekliyor, temizle.
            name = re.sub(r'\s*\d[\d\.,]{2,}\s*(?:tl|₺)?$', '', name, flags=re.IGNORECASE).strip()

            if len(name) < 10:
                return None

            # Price
            price_elem = product_elem.find('span', class_='product-list__price')
            if not price_elem:
                price_elem = product_elem.find('div', class_='price-box')
            if not price_elem:
                price_elem = product_elem.find('span', class_='price')

            price_text = price_elem.get_text(strip=True) if price_elem else ""
            price = self.extract_price(price_text)

            if not price:
                print(f"  ⚠️ Fiyat bulunamadı: {name[:50]}")
                return None

            # Specs text (tüm ürün bilgilerini birleştir)
            specs_text = product_elem.get_text(separator=' ', strip=True)

            # Extract all fields
            screen_size = self.extract_screen_size(name, specs_text)
            ssd = self.extract_ssd(name, specs_text)
            cpu = self.extract_cpu(name, specs_text)
            ram = self.extract_ram(name, specs_text)
            os = self.extract_os(name, specs_text)
            gpu = self.extract_gpu(name, specs_text)

            return {
                'url': url,
                'name': name,
                'price': price,
                'screen_size': screen_size,
                'ssd': ssd,
                'cpu': cpu,
                'ram': ram,
                'os': os,
                'gpu': gpu
            }

        except Exception as e:
            print(f"  ❌ Ürün işlenirken hata: {e}")
            return None

    def scrape_category_page(self, page_num=1):
        """Kategori sayfasını scrape et"""
        url = f"{self.base_url}/notebook?page={page_num}"
        print(f"\n📄 Scraping sayfa {page_num}: {url}")

        soup = self.get_page(url)
        if not soup:
            return False

        # Ürün listesini bul (Vatan'ın farklı olası yapıları)
        products = soup.find_all('div', class_='product-list')
        if not products:
            products = soup.find_all('div', class_='wrapper product')
        if not products:
            products = soup.find_all('div', class_='product-card')
        if not products:
            products = soup.find_all('div', class_='product-list__product')

        if not products:
            print(f"  ⚠️ Sayfa {page_num}'de ürün bulunamadı")
            return False

        print(f"  ✓ {len(products)} ürün bulundu")

        scraped_count = 0
        for idx, product in enumerate(products, 1):
            laptop_data = self.scrape_product(product)
            if laptop_data:
                self.laptops.append(laptop_data)
                scraped_count += 1
                print(f"  [{idx}/{len(products)}] ✓ {laptop_data['name'][:60]}... - {laptop_data['price']:,.0f} TL")
            else:
                print(f"  [{idx}/{len(products)}] ✗ Ürün atlandı")

        print(f"  → Başarılı: {scraped_count}/{len(products)} ürün")
        return scraped_count > 0

    def save_to_csv(self, filename='vatan_laptops.csv'):
        """CSV dosyasına kaydet - UTF-8-SIG encoding"""
        if not self.laptops:
            print("\n❌ Kaydedilecek veri yok!")
            return

        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'url', 'name', 'price', 'screen_size', 'ssd',
                'cpu', 'ram', 'os', 'gpu'
            ])
            writer.writeheader()
            writer.writerows(self.laptops)

        print(f"\n✅ {len(self.laptops)} laptop {filename} dosyasına kaydedildi")

        # Özet istatistikler
        print("\n" + "=" * 60)
        print("📊 SCRAPING ÖZETİ")
        print("=" * 60)

        # RAM dağılımı
        ram_counts = {}
        for laptop in self.laptops:
            ram = laptop['ram']
            ram_counts[ram] = ram_counts.get(ram, 0) + 1
        print("\n💾 RAM Dağılımı:")
        for ram, count in sorted(ram_counts.items()):
            print(f"  {ram}: {count} ürün")

        # GPU dağılımı (ilk 10)
        gpu_counts = {}
        for laptop in self.laptops:
            gpu = laptop['gpu']
            gpu_counts[gpu] = gpu_counts.get(gpu, 0) + 1
        print("\n🎮 GPU Dağılımı (İlk 10):")
        for gpu, count in sorted(gpu_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {gpu}: {count} ürün")

        # Fiyat aralığı
        prices = [l['price'] for l in self.laptops]
        print(f"\n💰 Fiyat Aralığı:")
        print(f"  Min: {min(prices):,.0f} TL")
        print(f"  Max: {max(prices):,.0f} TL")
        print(f"  Ortalama: {sum(prices) / len(prices):,.0f} TL")

        print("=" * 60)

    def run(self, max_pages=10):
        """Ana scraping fonksiyonu"""
        print("=" * 60)
        print("🚀 VATAN BİLGİSAYAR LAPTOP SCRAPER v2.0")
        print("=" * 60)
        print(f"Hedef: İlk {max_pages} sayfa")
        print(f"Zaman: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        for page in range(1, max_pages + 1):
            success = self.scrape_category_page(page)
            if not success:
                print(f"\n⚠️ Sayfa {page}'de ürün bulunamadı veya hata oluştu, durduruluyor...")
                break

            # Rate limiting (sunucuya nazik ol)
            if page < max_pages:
                print(f"\n⏳ {2} saniye bekleniyor...")
                time.sleep(2)

        self.save_to_csv()

        print(f"\n{'=' * 60}")
        print(f"✅ TAMAMLANDI!")
        print(f"📦 Toplam {len(self.laptops)} laptop başarıyla çekildi!")
        print(f"💾 Dosya: vatan_laptops.csv")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    scraper = VatanLaptopScraper()
    scraper.run(max_pages=5)  # İlk 5 sayfayı scrape et
