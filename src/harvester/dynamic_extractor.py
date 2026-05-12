"""
Extrator dinâmico com Selenium – gere um Chrome headless persistente.
"""

import time
import logging
from typing import Optional, Tuple

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

logger = logging.getLogger("roaz.dynamic_extractor")

class DynamicExtractor:
    def __init__(self):
        self.driver = None
        self._create_driver()

    def _create_driver(self):
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-sync")
        self.driver = uc.Chrome(options=options, version_main=147)

    def _ensure_driver_alive(self):
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium não disponível.")
        try:
            self.driver.title
        except Exception:
            logger.warning("Driver morto, recriando...")
            try:
                self.driver.quit()
            except:
                pass
            self._create_driver()

    def fetch(self, url: str, wait_time: int = 5, retries: int = 2) -> Tuple[Optional[str], Optional[str]]:
        for attempt in range(retries + 1):
            self._ensure_driver_alive()
            try:
                self.driver.get(url)
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "article"))
                )
                time.sleep(wait_time)
                html = self.driver.page_source
                from src.harvester.extractor import extract_content
                text = extract_content(html)
                if text and len(text) > 100:
                    return html, text
            except Exception as e:
                logger.warning(f"Tentativa {attempt+1} falhou para {url}: {e}")
                if attempt < retries:
                    time.sleep(2)
        return None, None

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
