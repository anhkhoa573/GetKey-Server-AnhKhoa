"""
Module vuot link4m va Gtraffic.
Can Chrome + chromedriver cai tren may.
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time


def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=options)
    return driver


def verify_bypass(service, verify_url):
    """
    Kiem tra user da vuot link thanh cong.
    """
    if not verify_url:
        return False, "Chua co URL xac minh."

    allowed_domains = ["link4m.co", "gtraffic.net", "link4m.com"]
    if not any(d in verify_url for d in allowed_domains):
        return False, "URL khong hop le."

    driver = create_driver()
    try:
        driver.get(verify_url)
        time.sleep(5)

        buttons = driver.find_elements(By.TAG_NAME, "button")
        has_continue = any(
            "continue" in b.text.lower() or "get link" in b.text.lower()
            for b in buttons
        )

        if has_continue:
            return False, "Ban chua vuot link xong."

        current = driver.current_url
        return True, current

    except Exception as e:
        return False, "Loi kiem tra: " + str(e)
    finally:
        driver.quit()
