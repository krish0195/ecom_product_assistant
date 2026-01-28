import csv
import time
import re
import os
import subprocess
from bs4 import BeautifulSoup

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains


# ------------------------------------------------------------------
# Helper: Detect installed Chrome major version (Windows)
# ------------------------------------------------------------------
def get_chrome_major_version():
    try:
        result = subprocess.check_output(
            r'reg query "HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon" /v version',
            shell=True
        ).decode()
        version = re.search(r'\d+\.\d+\.\d+\.\d+', result).group()
        return int(version.split('.')[0])
    except Exception:
        return None


class FlipkartScraper:
    def __init__(self, output_dir="data"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.chrome_version = get_chrome_major_version()

    # ------------------------------------------------------------------
    # Internal: Create Chrome driver safely
    # ------------------------------------------------------------------
    def _create_driver(self, headless=False):
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        if headless:
            options.add_argument("--headless=new")

        return uc.Chrome(
            options=options,
            version_main=self.chrome_version,
            use_subprocess=True
        )

    # ------------------------------------------------------------------
    # Get top reviews from a product page
    # ------------------------------------------------------------------
    def get_top_reviews(self, product_url, count=2):
        if not product_url.startswith("http"):
            return "No reviews found"

        driver = self._create_driver(headless=True)

        try:
            driver.get(product_url)
            time.sleep(4)

            # Close login popup if present
            try:
                driver.find_element(
                    By.XPATH,
                    "//button[contains(text(), '✕')] | //span[contains(text(), '✕')]"
                ).click()
                time.sleep(1)
            except Exception:
                pass

            # Scroll for reviews
            for _ in range(3):
                ActionChains(driver).send_keys(Keys.END).perform()
                time.sleep(1.5)

            soup = BeautifulSoup(driver.page_source, "html.parser")

            review_blocks = soup.select(
                "div.G4PxIA, div._27M-vq, div.col.EPCmJX"
            )

            seen = set()
            reviews = []

            for block in review_blocks:
                text = (
                    block.get_text(separator=" ", strip=True)
                    .replace("READ MORE", "")
                    .strip()
                )
                if text and text not in seen and len(text) > 20:
                    reviews.append(text)
                    seen.add(text)

                if len(reviews) >= count:
                    break

        except Exception:
            reviews = []

        finally:
            driver.quit()

        return " || ".join(reviews) if reviews else "No reviews found"

    # ------------------------------------------------------------------
    # Scrape products from Flipkart search
    # ------------------------------------------------------------------
    def scrape_flipkart_products(self, query, max_products=5, review_count=2):
        driver = self._create_driver(headless=False)

        search_url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"
        driver.get(search_url)
        time.sleep(4)

        # Close login popup
        try:
            driver.find_element(
                By.XPATH,
                "//button[contains(text(), '✕')] | //span[contains(text(), '✕')]"
            ).click()
        except Exception:
            pass

        time.sleep(2)
        products = []

        items = driver.find_elements(
            By.CSS_SELECTOR, "div.jIjQ8S, div[data-id]"
        )[:max_products]

        for item in items:
            try:
                title = item.find_element(
                    By.CSS_SELECTOR, "div.RG5Slk"
                ).text.strip()

                price = item.find_element(
                    By.CSS_SELECTOR, "div.hZ3P6w.DeU9vF"
                ).text.strip()

                rating = item.find_element(
                    By.CSS_SELECTOR, "div.MKiFS6"
                ).text.strip()

                reviews_text = item.find_element(
                    By.CSS_SELECTOR, "span.o2SIOJ"
                ).text.strip()

                clean_num = "".join(
                    re.findall(r'\d+', reviews_text.replace(',', ''))
                )
                total_reviews = int(clean_num) if clean_num else 0

                link_el = item.find_element(
                    By.CSS_SELECTOR, "a[href*='/p/']"
                )
                href = link_el.get_attribute("href")
                product_link = (
                    href if href.startswith("http")
                    else "https://www.flipkart.com" + href
                )

                pid_match = re.search(r"/p/([^/?]+)", href)
                product_id = pid_match.group(1) if pid_match else "N/A"

                print(f"Scraping: {title[:40]}... (ID: {product_id})")

                top_reviews = self.get_top_reviews(
                    product_link,
                    count=review_count
                )

                products.append([
                    product_id,
                    title,
                    rating,
                    total_reviews,
                    price,
                    top_reviews
                ])

            except Exception as e:
                print(f"❌ Error processing product: {e}")
                continue

        driver.quit()
        return products

    # ------------------------------------------------------------------
    # Save output to CSV
    # ------------------------------------------------------------------
    def save_to_csv(self, data, filename="product_reviews.csv"):
        base_name = os.path.basename(filename)
        path = os.path.join(self.output_dir, base_name)

        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "product_id",
                "product_title",
                "rating",
                "total_reviews",
                "price",
                "top_reviews"
            ])
            writer.writerows(data)

        print(f"✅ Data saved to: {path}")
