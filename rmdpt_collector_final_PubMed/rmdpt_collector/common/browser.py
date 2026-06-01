import logging
import atexit
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager

# --- WebDriver Singleton ---
_driver = None

def get_driver():
    """Initializes and returns a headless Firefox WebDriver singleton."""
    global _driver
    if _driver is None:
        logging.info("Initializing headless Firefox browser for scraping...")
        try:
            options = FirefoxOptions()
            options.add_argument("--headless")
            options.add_argument("--window-size=1920,1080")
            
            # Use webdriver-manager to automatically handle the driver
            service = FirefoxService(GeckoDriverManager().install())
            
            _driver = webdriver.Firefox(service=service, options=options)
            logging.info("Browser initialized.")
        except Exception as e:
            logging.error(f"Failed to initialize Firefox WebDriver: {e}")
            logging.error("Please ensure Firefox is installed on the system.")
            _driver = None
    return _driver

@atexit.register
def close_driver():
    """Closes the WebDriver session on script exit."""
    global _driver
    if _driver:
        logging.info("Closing browser session...")
        _driver.quit()
        _driver = None
