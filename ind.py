import os
import time
import logging
import base64
import json
import re
import argparse
import pytesseract
from PIL import Image
from io import BytesIO
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import tempfile
from bs4 import BeautifulSoup
from flask import Flask, request, render_template

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('index2_downloader')

# Set Tesseract OCR path
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = Flask(__name__)

class Index2Downloader:
    def __init__(self, headless=False, downloads_path="downloads"):
        self.downloads_path = downloads_path
        self.browser = None
        self.headless = False  # Always set to False to show browser
        self.current_property_number = None
        
        # Create downloads directory if it doesn't exist
        os.makedirs(self.downloads_path, exist_ok=True)
        
        # Configure OCR options
        self.tesseract_config = '--oem 1 --psm 7'
        
        self.drive_service = self.initialize_drive()
        self.drive_folder_id = '1yT_M8b4_VTFZ0X4ggRJTxhRm5QYLp3E9'  # Replace with your folder ID
        
    def initialize(self):
        """Initialize the browser with undetected-chromedriver"""
        logger.info("Initializing browser...")
        
        try:
            # Setup Chrome options
            options = uc.ChromeOptions()
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--remote-debugging-port=9222")
            options.add_argument("--disable-blink-features=AutomationControlled")
            # Remove headless argument
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--disable-infobars")
            
            # Configure download settings
            prefs = {
                "download.default_directory": os.path.abspath(self.downloads_path),
                "download.prompt_for_download": False,
                "plugins.always_open_pdf_externally": True,
                "download.open_pdf_in_system_reader": False,
                "printing.print_preview_sticky_settings.appState": json.dumps({
                    "recentDestinations": [{
                        "id": "Save as PDF",
                        "origin": "local",
                        "account": "",
                    }],
                    "selectedDestinationId": "Save as PDF",
                    "version": 2
                })
            }
            options.add_experimental_option("prefs", prefs)
            
            # Initialize the browser with undetected-chromedriver
            logger.info("Creating undetected Chrome browser...")
            self.browser = uc.Chrome(options=options)
            
            # Set very long timeout for slow government websites (5 minutes)
            self.browser.set_page_load_timeout(300)
            
            logger.info("Browser initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing browser: {e}")
            raise Exception(f"Failed to initialize browser: {e}")
        
    def navigate_to_search_page(self):
        """Navigate to the search page with extended waiting"""
        logger.info("Navigating to search page...")
        
        url = "https://freesearchigrservice.maharashtra.gov.in/"
        
        # Add retry logic with exponential backoff
        max_retries = 3
        retry_delay = 10  # Initial delay in seconds
        max_delay = 60  # Maximum delay between retries
        
        for retry in range(max_retries):
            try:
                logger.info(f"Attempting to load {url} (Attempt {retry+1}/{max_retries})")
                
                # Set timeout for page load
                self.browser.set_page_load_timeout(120)  # 2 minutes
                
                # Use get with extended timeout
                self.browser.get(url)
                
                # Display message to user about waiting
                logger.info("Page is loading. Government websites can be slow - please wait...")
                
                # Wait with increasing intervals to allow the page to fully load
                for i in range(1, 13):  # 12 checks over 1 minute
                    time.sleep(5)  # 5-second intervals
                    logger.info(f"Still waiting for page to load... ({i*5}s)")
                    
                    # Check if page has loaded enough to proceed
                    page_ready = self.browser.execute_script("""
                        return document.readyState === 'complete' || 
                               document.readyState === 'interactive';
                    """)
                    
                    if page_ready:
                        logger.info("Page appears to be ready, checking for elements...")
                        
                    try:
                        close_button = WebDriverWait(self.browser, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btnclose.btn.btn-danger"))
                        )
                        close_button.click()
                        logger.info("Clicked Close button")
                    except Exception as close_error:
                        logger.warning(f"Could not find or click Close button: {close_error}")
                            
                    break
                
                # Take a screenshot to see current state
                self.browser.save_screenshot(os.path.join(self.downloads_path, "main_page_loaded.png"))
                
                # Check if there's any error message on the page
                if "ERR_NAME_NOT_RESOLVED" in self.browser.page_source or "can't be reached" in self.browser.page_source:
                    logger.warning("Error page detected, retrying...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_delay)  # Exponential backoff
                    continue
                
                logger.info("Checking for Rest of Maharashtra button...")
                
                # First take a screenshot of current state
                self.browser.save_screenshot(os.path.join(self.downloads_path, f"before_button_click_{retry}.png"))
                
                # Try to find and click the button
                try:
                    # Wait up to 20 seconds for the button to be clickable
                    maharashtra_button = WebDriverWait(self.browser, 20).until(
                        EC.element_to_be_clickable((By.ID, "btnOtherdistrictSearch"))
                    )
                    logger.info("Found Rest of Maharashtra button, clicking it...")
                    maharashtra_button.click()
                    
                    # Wait for the form to load after clicking
                    logger.info("Waiting for form to load after clicking button...")
                    WebDriverWait(self.browser, 30).until(
                        EC.presence_of_element_located((By.ID, "ddlFromYear1"))
                    )
                    
                    logger.info("Search form loaded successfully")
                    return True
                except Exception as button_error:
                    logger.warning(f"Error with button click: {button_error}")
                    
                    # Try JavaScript click as backup
                    try:
                        logger.info("Attempting JavaScript click...")
                        self.browser.execute_script("document.getElementById('btnOtherdistrictSearch').click()")
                        
                        # Wait for form to load
                        logger.info("Waiting for form after JavaScript click...")
                        time.sleep(10)
                        
                        # Check if form is loaded
                        form_element = self.browser.find_element(By.ID, "ddlFromYear1")
                        if form_element:
                            logger.info("Form loaded successfully after JavaScript click")
                            return True
                    except Exception as js_error:
                        logger.warning(f"JavaScript click failed: {js_error}")
                
                # First, try to find and click the Close button if it exists
                try:
                    close_button = WebDriverWait(self.browser, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btnclose.btn.btn-danger"))
                    )
                    logger.info("Found Close button, clicking it...")
                    close_button.click()
                    time.sleep(2)  # Wait for the close action to complete
                except Exception as close_error:
                    logger.info("Close button not found or not clickable, proceeding...")
            
            except TimeoutException:
                logger.warning(f"Timeout occurred on attempt {retry+1}")
                if retry < max_retries - 1:
                    logger.info(f"Waiting {retry_delay} seconds before retrying...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_delay)  # Exponential backoff
                    continue
                else:
                    logger.error("Max retries reached. The website may be down or too slow to respond.")
                    raise Exception("Could not load the website after multiple attempts")
            
            except Exception as e:
                logger.error(f"Error on attempt {retry+1}: {e}")
                if retry < max_retries - 1:
                    logger.info(f"Waiting {retry_delay} seconds before retrying...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_delay)  # Exponential backoff
                    continue
                else:
                    logger.error("Max retries reached. The website may be down or too slow to respond.")
                    raise Exception(f"Could not load the website after multiple attempts: {e}")
        
        # If we've exhausted all retries
        logger.error("Failed to load page after multiple attempts")
        self.browser.save_screenshot(os.path.join(self.downloads_path, "final_failure.png"))
        raise Exception("Could not load the website after multiple attempts. The website may be down or too slow to respond.")

    def get_available_options(self, select_element_id):
        """Get all available options in a dropdown as a dictionary of value: text"""
        try:
            select_element = self.browser.find_element(By.ID, select_element_id)
            select = Select(select_element)
            options = {}
            
            for option in select.options:
                value = option.get_attribute("value")
                text = option.text.strip()
                if value:  # Include all options with a value
                    options[value] = text
            
            return options
        except Exception as e:
            logger.warning(f"Error getting options for {select_element_id}: {e}")
            return {}
    
    def select_first_option(self, select_element_id):
        """Select the first non-empty option in a dropdown and return its value"""
        try:
            select_element = self.browser.find_element(By.ID, select_element_id)
            select = Select(select_element)
            
            # Skip the first option which is usually a placeholder
            for option in select.options[1:]:
                value = option.get_attribute("value")
                if value and value != "0" and value != "":
                    select.select_by_value(value)
                    return value
            
            return None
        except Exception as e:
            logger.warning(f"Error selecting first option in {select_element_id}: {e}")
            return None
    
    def find_captcha_element(self):
        """Find the captcha element on the page"""
        logger.info("Looking for captcha element...")
        
        # Try all possible captcha element selectors
        captcha_selectors = [
            (By.ID, "imgCaptcha_new"),
            (By.ID, "imgCaptcha"),
            (By.CSS_SELECTOR, "img[src*='Handler.ashx']"),
            (By.CSS_SELECTOR, "img[src*='captcha']"),
            (By.CSS_SELECTOR, "img[src*='Captcha']"),
            (By.CSS_SELECTOR, "img[id*='captcha']")
        ]
        
        for selector_type, selector in captcha_selectors:
            try:
                captcha_element = self.browser.find_element(selector_type, selector)
                if captcha_element.is_displayed():
                    logger.info(f"Found captcha with selector: {selector}")
                    return captcha_element
            except:
                continue
        
        # If not found with standard selectors, use JavaScript
        try:
            captcha_element = self.browser.execute_script("""
                var images = document.querySelectorAll('img');
                for(var i=0; i<images.length; i++) {
                    var src = images[i].src || '';
                    var id = images[i].id || '';
                    if(src.includes('captcha') || src.includes('Captcha') || 
                       id.includes('captcha') || id.includes('Captcha') ||
                       src.includes('Handler.ashx')) {
                        return images[i];
                    }
                }
                return null;
            """)
            
            if captcha_element:
                logger.info("Found captcha with JavaScript")
                return captcha_element
        except:
            pass
            
        # Take screenshot for debugging
        self.browser.save_screenshot(os.path.join(self.downloads_path, "captcha_debug.png"))
        
        raise Exception("Captcha element not found")
    
    def solve_captcha(self):
        """Solve the captcha using OCR"""
        logger.info("Attempting to solve captcha...")
        
        try:
            # Find captcha element
            captcha_element = self.find_captcha_element()
            
            # Get screenshot of the captcha
            captcha_screenshot = captcha_element.screenshot_as_png
            captcha_image = Image.open(BytesIO(captcha_screenshot))
            
            # Save image for debugging
            captcha_path = os.path.join(self.downloads_path, "captcha.png")
            captcha_image.save(captcha_path)
            
            # Enhance image for better OCR
            captcha_image = captcha_image.convert('L')  # Convert to grayscale
            captcha_image = captcha_image.point(lambda x: 0 if x < 140 else 255, '1')  # Increase contrast
            
            # Save enhanced image
            enhanced_path = os.path.join(self.downloads_path, "captcha_enhanced.png")
            captcha_image.save(enhanced_path)
            
            # Perform OCR
            captcha_text = pytesseract.image_to_string(
                captcha_image, 
                config=self.tesseract_config
            ).strip()
            
            # Clean the text
            captcha_text = ''.join(c for c in captcha_text if c.isalnum())
            
            logger.info(f"Captcha text detected: '{captcha_text}'")
            return captcha_text
            
        except Exception as e:
            logger.error(f"Error solving captcha: {e}")
            raise
    
    def fill_search_form(self, year, district_name, taluka_name, village_name, property_number):
        """Fill the search form with the provided parameters using names instead of codes"""
        self.current_property_number = property_number
        logger.info(f"Filling search form for property {property_number}...")
        
        try:
            # Select Year
            logger.info(f"Selecting year: {year}")
            year_dropdown = Select(self.browser.find_element(By.ID, "ddlFromYear1"))
            year_dropdown.select_by_value(str(year))
            time.sleep(3)  # Wait after year selection
            
            # Select District by name
            logger.info(f"Selecting district: {district_name}")
            district_dropdown = Select(self.browser.find_element(By.ID, "ddlDistrict1"))
            district_selected = False
            
            # Try to find the district by exact name match first
            for option in district_dropdown.options:
                if option.text.strip() == district_name:
                    district_dropdown.select_by_visible_text(district_name)
                    district_selected = True
                    logger.info(f"Selected district by exact name match: {district_name}")
                    break
            
            # If exact match not found, try partial match
            if not district_selected:
                for option in district_dropdown.options:
                    if district_name.lower() in option.text.strip().lower():
                        district_dropdown.select_by_visible_text(option.text.strip())
                        district_selected = True
                        logger.info(f"Selected district by partial match: {option.text.strip()}")
                        break
            
            # If still not found, select the first non-empty option
            if not district_selected:
                logger.warning(f"District '{district_name}' not found. Selecting first available district.")
                self.select_first_option("ddlDistrict1")
            
            time.sleep(3)  # Wait after district selection
            
            # Wait for taluka dropdown to populate
            logger.info("Waiting for taluka dropdown to populate...")
            WebDriverWait(self.browser, 30).until(
                lambda d: len(Select(d.find_element(By.ID, "ddltahsil")).options) > 1
            )
            time.sleep(3)  # Wait after taluka dropdown populates
            
            # Select Taluka by name
            logger.info(f"Selecting taluka: {taluka_name}")
            taluka_dropdown = Select(self.browser.find_element(By.ID, "ddltahsil"))
            taluka_selected = False
            
            # Try to find the taluka by exact name match first
            for option in taluka_dropdown.options:
                if option.text.strip() == taluka_name:
                    taluka_dropdown.select_by_visible_text(taluka_name)
                    taluka_selected = True
                    logger.info(f"Selected taluka by exact name match: {taluka_name}")
                    break
            
            # If exact match not found, try partial match
            if not taluka_selected:
                for option in taluka_dropdown.options:
                    if taluka_name.lower() in option.text.strip().lower():
                        taluka_dropdown.select_by_visible_text(option.text.strip())
                        taluka_selected = True
                        logger.info(f"Selected taluka by partial match: {option.text.strip()}")
                        break
            
            # If still not found, select the first non-empty option
            if not taluka_selected:
                logger.warning(f"Taluka '{taluka_name}' not found. Selecting first available taluka.")
                self.select_first_option("ddltahsil")
            
            time.sleep(3)  # Wait after taluka selection
            
            # Wait for village dropdown to populate
            logger.info("Waiting for village dropdown to populate...")
            WebDriverWait(self.browser, 30).until(
                lambda d: len(Select(d.find_element(By.ID, "ddlvillage")).options) > 1
            )
            time.sleep(3)  # Wait after village dropdown populates
            
            # Select Village by name
            logger.info(f"Selecting village: {village_name}")
            village_dropdown = Select(self.browser.find_element(By.ID, "ddlvillage"))
            village_selected = False
            
            # Try to find the village by exact name match first
            for option in village_dropdown.options:
                if option.text.strip() == village_name:
                    village_dropdown.select_by_visible_text(village_name)
                    village_selected = True
                    logger.info(f"Selected village by exact name match: {village_name}")
                    break
            
            # If exact match not found, try partial match
            if not village_selected:
                for option in village_dropdown.options:
                    if village_name.lower() in option.text.strip().lower():
                        village_dropdown.select_by_visible_text(option.text.strip())
                        village_selected = True
                        logger.info(f"Selected village by partial match: {option.text.strip()}")
                        break
            
            # If still not found, select the first non-empty option
            if not village_selected:
                logger.warning(f"Village '{village_name}' not found. Selecting first available village.")
                self.select_first_option("ddlvillage")
            
            time.sleep(10)  # Wait after village selection
            
            # Enter Property Number
            logger.info(f"Entering property number: {property_number}")
            property_input = self.browser.find_element(By.ID, "txtAttributeValue1")
            property_input.clear()
            property_input.send_keys(str(property_number))
            time.sleep(3)  # Wait after entering property number
            
            # Handle Captcha with automatic OCR
            logger.info("Handling captcha...")
            captcha_text = self.solve_captcha()
            
            captcha_input = self.browser.find_element(By.ID, "txtImg1")
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)
            time.sleep(3)  # Wait after entering captcha
            
            logger.info("Search form filled successfully")
            return True
        except Exception as e:
            logger.error(f"Error filling search form: {e}")
            self.browser.save_screenshot(os.path.join(self.downloads_path, "form_fill_error.png"))
            raise
    
    def submit_search_form(self, max_attempts=3):
        """Submit the search form and wait for results with multiple attempts"""
        logger.info("Submitting search form...")
        
        attempt = 0
        while attempt < max_attempts:
            try:
                attempt += 1
                logger.info(f"Attempt {attempt}/{max_attempts}")
                
                # Verify property number is still entered
                property_input = self.browser.find_element(By.ID, "txtAttributeValue1")
                if not property_input.get_attribute("value"):
                    logger.warning("Property number field is empty, refilling...")
                    property_input.send_keys(str(self.current_property_number))
                
                # Verify captcha is filled
                captcha_input = self.browser.find_element(By.ID, "txtImg1")
                if not captcha_input.get_attribute("value"):
                    logger.warning("Captcha field is empty, solving new captcha...")
                    captcha_text = self.solve_captcha()
                    captcha_input.clear()
                    captcha_input.send_keys(captcha_text)
                
                # Locate the search button
                try:
                    search_button = self.browser.find_element(By.ID, "btnSearch_RestMaha")
                    search_button.click()
                    logger.info("Search button clicked")
                except NoSuchElementException:
                    logger.warning("Search button not found by ID, trying alternative selectors...")
                    
                    # Try alternative selectors
                    search_button_selectors = [
                        (By.CSS_SELECTOR, "input[value='Search']"),
                        (By.CSS_SELECTOR, "input[value*='Search']"),
                        (By.CSS_SELECTOR, "input[onclick*='Search']"),
                        (By.CSS_SELECTOR, "button[onclick*='Search']"),
                        (By.XPATH, "//input[contains(@value, 'Search')]"),
                        (By.XPATH, "//button[contains(text(), 'Search')]")
                    ]
                    
                    found_button = False
                    for selector_type, selector in search_button_selectors:
                        try:
                            buttons = self.browser.find_elements(selector_type, selector)
                            if buttons:
                                buttons[0].click()
                                logger.info(f"Clicked alternate search button using selector: {selector}")
                                found_button = True
                                break
                        except Exception as button_err:
                            logger.debug(f"Failed with selector {selector}: {button_err}")
                    
                    if not found_button:
                        # Check if IndexII buttons already present (might be in results already)
                        index2_buttons = self.browser.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
                        if index2_buttons:
                            logger.info(f"IndexII buttons already present (count: {len(index2_buttons)}), proceeding")
                            return True
                        else:
                            logger.error("No search button or IndexII buttons found")
                            self.browser.save_screenshot(os.path.join(self.downloads_path, f"no_search_button_attempt_{attempt}.png"))
                            if attempt == max_attempts:
                                raise Exception("No search button found and no results displayed")
                            continue
                
                # Wait 20 seconds after clicking search button
                logger.info("Waiting 10 seconds for initial processing...")
                time.sleep(10)
                
                # Check if new captcha appears
                if self.is_new_captcha_present():
                    logger.info("New captcha detected, solving it...")
                    self.solve_and_submit_new_captcha()
                
                # Wait for loading indicator to appear
                logger.info("Waiting for loading indicator to appear...")
                try:
                    WebDriverWait(self.browser, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//img[@src='Images/ajax-loader1.gif']"))
                    )
                    logger.info("Loading indicator appeared")
                except TimeoutException:
                    logger.warning("Loading indicator did not appear within timeout")
                
                # Wait for loading indicator to disappear
                logger.info("Waiting for loading to complete...")
                try:
                    WebDriverWait(self.browser, 120).until(
                        EC.invisibility_of_element_located((By.XPATH, "//img[@src='Images/ajax-loader1.gif']"))
                    )
                    logger.info("Loading indicator disappeared")
                except TimeoutException:
                    logger.warning("Loading indicator did not disappear within timeout")
                
                # Wait for results or error message
                logger.info("Waiting for search results to load...")
                try:
                    WebDriverWait(self.browser, 30).until(
                        lambda d: (
                            d.find_elements(By.ID, "RegistrationGrid") or 
                            d.find_elements(By.CSS_SELECTOR, "span[style*='color:Red']") or
                            d.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")  # Direct check for IndexII buttons
                        )
                    )
                except TimeoutException:
                    logger.warning("Timeout waiting for results, checking page state...")
                    self.browser.save_screenshot(os.path.join(self.downloads_path, f"timeout_state_attempt_{attempt}.png"))
                    continue  # Try again if timeout occurs

                # Take a screenshot of results page
                self.browser.save_screenshot(os.path.join(self.downloads_path, f"search_results_attempt_{attempt}.png"))
                
                # Check for error messages more thoroughly
                error_elements = self.browser.find_elements(By.CSS_SELECTOR, "span[style*='color:Red']")
                if error_elements:
                    error_texts = [e.text.strip() for e in error_elements if e.text.strip()]
                    if error_texts:
                        logger.error(f"Search error: {', '.join(error_texts)}")
                        
                        # Look for IndexII buttons even with errors
                        index2_buttons = self.browser.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
                        if index2_buttons:
                            logger.info(f"Found {len(index2_buttons)} IndexII buttons despite error message")
                            return True
                        
                        # Handle specific error codes
                        if "1259" in error_texts[0]:
                            logger.info("Error 1259 detected, attempting to refresh captcha...")
                            self.handle_error_1259()
                            continue  # Try again after handling error
                        
                        # Handle error 3046 specifically
                        if "3046" in error_texts[0]:
                            logger.info("Error 3046 detected, checking for IndexII buttons anyway...")
                            # Look for IndexII buttons
                            index2_buttons = self.browser.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
                            if index2_buttons:
                                logger.info(f"Found {len(index2_buttons)} IndexII buttons despite error 3046")
                                return True
                        
                        continue  # Try again for other errors
                
                # Check if we have results
                try:
                    # First check for IndexII buttons directly
                    index2_buttons = self.browser.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
                    if index2_buttons:
                        logger.info(f"Found {len(index2_buttons)} IndexII buttons")
                        return True
                    
                    # Then check for results table
                    results_table = self.browser.find_element(By.ID, "RegistrationGrid")
                    rows = results_table.find_elements(By.TAG_NAME, "tr")
                    
                    if len(rows) <= 1:
                        logger.error("No search results found (empty table)")
                        continue  # Try again if no results
                    
                    logger.info(f"Found {len(rows)-1} search results in table")
                    return True
                    
                except Exception as e:
                    logger.error(f"Error checking search results: {e}")
                    continue  # Try again if error occurs
                
            except Exception as e:
                logger.error(f"Error in attempt {attempt}: {e}")
                self.browser.save_screenshot(os.path.join(self.downloads_path, f"search_error_attempt_{attempt}.png"))
                continue  # Try again if any other error occurs
        
        # If we've exhausted all attempts, look for IndexII buttons one last time
        index2_buttons = self.browser.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
        if index2_buttons:
            logger.info(f"Found {len(index2_buttons)} IndexII buttons on final check")
            return True
            
        # If we've exhausted all attempts and found no IndexII buttons
        logger.error(f"Failed after {max_attempts} attempts")
        raise Exception(f"Could not complete search after {max_attempts} attempts")
    
    def is_loading_complete(self):
        """Check if page loading is complete"""
        try:
            return self.browser.execute_script("""
                return document.readyState === 'complete' && 
                       !document.querySelector('.loading-indicator') &&
                       !document.querySelector('.spinner');
            """)
        except:
            return True
    
    def wait_for_loading_to_complete(self, timeout=120):
        """Wait for loading indicators to disappear"""
        logger.info("Waiting for loading to complete...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.is_loading_complete():
                return True
            time.sleep(2)
        
        logger.warning("Loading did not complete within timeout")
        return False
    
    def handle_error_1259(self):
        """Handle specific error code 1259"""
        logger.info("Handling error 1259...")
        
        try:
            # Refresh the captcha
            logger.info("Refreshing captcha...")
            refresh_button = self.browser.find_element(By.ID, "btnRefreshCaptcha")
            refresh_button.click()
            time.sleep(2)  # Wait for new captcha to load
            
            # Solve the new captcha
            captcha_text = self.solve_captcha()
            
            # Enter the new captcha
            captcha_input = self.browser.find_element(By.ID, "txtImg1")
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)
            
            # Click search again
            search_button = self.browser.find_element(By.ID, "btnSearch_RestMaha")
            search_button.click()
            
            # Wait for loading to complete
            self.wait_for_loading_to_complete()
            
            # Wait for results
            WebDriverWait(self.browser, 120).until(
                lambda d: (
                    d.find_elements(By.ID, "RegistrationGrid") or 
                    d.find_elements(By.CSS_SELECTOR, "span[style*='color:Red']")
                )
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling error 1259: {e}")
            raise
    
    def click_index2_link(self):
        """Click the Index-2 link in search results"""
        logger.info("Clicking Index-2 link...")
        
        try:
            # Find Index-2 buttons using multiple approaches
            index2_buttons = []
            
            # Approach 1: CSS selector for input elements with value='IndexII'
            buttons1 = self.browser.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
            if buttons1:
                index2_buttons.extend(buttons1)
                logger.info(f"Found {len(buttons1)} IndexII buttons using CSS selector")
            
            # Approach 2: XPath for any element containing 'IndexII'
            buttons2 = self.browser.find_elements(By.XPATH, "//*[contains(text(),'IndexII') or contains(@value,'IndexII')]")
            if buttons2:
                # Filter out duplicates
                for btn in buttons2:
                    if btn not in index2_buttons:
                        index2_buttons.append(btn)
                logger.info(f"Found {len(buttons2)} additional IndexII buttons using XPath")
            
            # Approach 3: Look for links in registration grid
            try:
                grid = self.browser.find_element(By.ID, "RegistrationGrid")
                buttons3 = grid.find_elements(By.TAG_NAME, "input")
                for btn in buttons3:
                    if btn.get_attribute("value") == "IndexII" and btn not in index2_buttons:
                        index2_buttons.append(btn)
                logger.info(f"Found {len(buttons3)} IndexII buttons within registration grid")
            except:
                pass
            
            # Approach 4: Try JavaScript to find buttons
            try:
                js_buttons = self.browser.execute_script("""
                    var buttons = [];
                    var inputs = document.querySelectorAll('input');
                    for(var i=0; i<inputs.length; i++) {
                        if(inputs[i].value === 'IndexII') {
                            buttons.push(inputs[i]);
                        }
                    }
                    return buttons;
                """)
                if js_buttons:
                    for btn in js_buttons:
                        if btn not in index2_buttons:
                            index2_buttons.append(btn)
                    logger.info(f"Found {len(js_buttons)} IndexII buttons using JavaScript")
            except:
                pass
            
            if not index2_buttons:
                logger.error("No Index-2 buttons found in results")
                self.browser.save_screenshot(os.path.join(self.downloads_path, "no_index2_buttons.png"))
                
                # Save the page source for debugging
                with open(os.path.join(self.downloads_path, "page_source.html"), "w", encoding="utf-8") as f:
                    f.write(self.browser.page_source)
                
                raise Exception("No Index-2 buttons found in results")
            
            logger.info(f"Found total of {len(index2_buttons)} Index-2 buttons")
            
            # Click the first button
            try:
                # First try a normal click
                index2_buttons[0].click()
                logger.info("Clicked first Index-2 button")
            except Exception as click_error:
                logger.warning(f"Error clicking button: {click_error}")
                
                try:
                    # Try JavaScript click as backup
                    self.browser.execute_script("arguments[0].click();", index2_buttons[0])
                    logger.info("Clicked first Index-2 button using JavaScript")
                except Exception as js_click_error:
                    logger.error(f"JavaScript click also failed: {js_click_error}")
                    raise
            
            # Wait for document page to load
            logger.info("Waiting for document page to load...")
            
            # Wait for URL to change to the isaritaHTMLReportSuchiKramank2 page
            try:
                WebDriverWait(self.browser, 60).until(
                    lambda d: "isaritaHTMLReportSuchiKramank2" in d.current_url
                )
                logger.info("Successfully navigated to IndexII page")
            except:
                logger.warning("URL didn't change to isaritaHTMLReportSuchiKramank2")
                
                # Check if a new window or tab was opened
                if len(self.browser.window_handles) > 1:
                    logger.info(f"Found {len(self.browser.window_handles)} window handles, switching to the newest one")
                    
                    # Store the original window handle
                    original_window = self.browser.current_window_handle
                    
                    # Switch to the new window
                    for handle in self.browser.window_handles:
                        if handle != original_window:
                            self.browser.switch_to.window(handle)
                            logger.info(f"Switched to window with URL: {self.browser.current_url}")
                            
                            if "isaritaHTMLReportSuchiKramank2" in self.browser.current_url:
                                logger.info("Found isaritaHTMLReportSuchiKramank2 page in new window")
                                break
                            else:
                                # Switch back if not the right page
                                self.browser.switch_to.window(original_window)
            
            # Take a screenshot of the IndexII page
            self.browser.save_screenshot(os.path.join(self.downloads_path, "indexii_page.png"))
            
            # Save the current URL
            current_url = self.browser.current_url
            logger.info(f"Current URL: {current_url}")
            
            # Save the page source
            with open(os.path.join(self.downloads_path, "indexii_page_source.html"), "w", encoding="utf-8") as f:
                f.write(self.browser.page_source)
            
            return current_url
        
        except Exception as e:
            logger.error(f"Error clicking Index-2 link: {e}")
            self.browser.save_screenshot(os.path.join(self.downloads_path, "click_index2_error.png"))
            raise

    def initialize_drive(self):
        """Initialize Google Drive API with service account"""
        SCOPES = ['https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_file(
            'service_account.json', scopes=SCOPES
        )
        return build('drive', 'v3', credentials=creds)

    def upload_to_drive(self, file_path, property_info):
        """Upload file to Google Drive with proper folder structure"""
        logger.info("Uploading file to Google Drive with folder structure...")
        
        try:
            year = str(property_info.get('year', 'Unknown_Year'))
            district = property_info.get('district_name', 'Unknown_District')
            taluka = property_info.get('taluka_name', 'Unknown_Taluka')
            village = property_info.get('village_name', 'Unknown_Village')
            property_number = property_info.get('property_number', 'Unknown_Property')
            
            # Function to create or get folder
            def create_or_get_folder(parent_id, folder_name):
                query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
                results = self.drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
                folders = results.get('files', [])
                
                if folders:
                    return folders[0]['id']
                else:
                    folder_metadata = {
                        'name': folder_name,
                        'mimeType': 'application/vnd.google-apps.folder',
                        'parents': [parent_id]
                    }
                    folder = self.drive_service.files().create(
                        body=folder_metadata,
                        fields='id'
                    ).execute()
                    return folder.get('id')
            
            # Create folder hierarchy
            year_folder_id = create_or_get_folder(self.drive_folder_id, year)
            district_folder_id = create_or_get_folder(year_folder_id, district)
            taluka_folder_id = create_or_get_folder(district_folder_id, taluka)
            village_folder_id = create_or_get_folder(taluka_folder_id, village)
            property_folder_id = create_or_get_folder(village_folder_id, property_number)
            
            # Upload file to property folder
            file_metadata = {
                'name': os.path.basename(file_path),
                'parents': [property_folder_id]
            }
            
            media = MediaFileUpload(file_path, mimetype='application/pdf')
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            logger.info(f"File uploaded successfully to folder structure: {year}/{district}/{taluka}/{village}/{property_number}")
            return file.get('id')
            
        except Exception as e:
            logger.error(f"Error uploading file to Google Drive: {e}")
            raise

    def download_indexii_document(self, url, property_info):
        """Download the IndexII document and upload to Google Drive"""
        logger.info("Downloading IndexII document...")
        
        try:
            # Ensure year is properly formatted
            if 'year' in property_info and isinstance(property_info['year'], str):
                # Try to extract year from date string (e.g., "DD/MM/YYYY")
                if '/' in property_info['year']:
                    property_info['year'] = property_info['year'].split('/')[-1]
                # Remove any non-numeric characters
                property_info['year'] = ''.join(filter(str.isdigit, property_info['year']))
            
            # Create directory structure for local storage
            dir_path = os.path.join(
                self.downloads_path,
                str(property_info.get('year', 'Unknown_Year')),
                property_info.get('district_name', 'Unknown_District'),
                property_info.get('taluka_name', 'Unknown_Taluka'),
                property_info.get('village_name', 'Unknown_Village'),
                str(property_info.get('property_number', 'Unknown_Property'))
            )
            os.makedirs(dir_path, exist_ok=True)
            
            # Generate filename
            filename = f"Index-2_{property_info.get('district_name')}_{property_info.get('village_name')}_{property_info.get('property_number')}_{property_info.get('year')}.pdf"
            file_path = os.path.join(dir_path, filename)
            
            # Navigate to the URL if not already there
            if self.browser.current_url != url and url != "":
                logger.info(f"Navigating to URL: {url}")
                self.browser.get(url)
                
                # Wait for the page to load
                WebDriverWait(self.browser, 60).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            
            # Take a screenshot of the page first
            self.browser.save_screenshot(os.path.join(self.downloads_path, "before_pdf_generation.png"))
            
            # Use browser's print to PDF capability
            logger.info("Generating PDF from document page...")
            
            try:
                # Try the first method: Chrome DevTools Protocol
                print_params = {
                    "landscape": False,
                    "printBackground": True,
                    "paperWidth": 8.27,  # A4 width in inches
                    "paperHeight": 11.69,  # A4 height in inches
                    "marginTop": 0.4,
                    "marginBottom": 0.4,
                    "marginLeft": 0.4,
                    "marginRight": 0.4,
                    "scale": 0.9,
                    "pageRanges": "",
                    "preferCSSPageSize": True
                }
                
                # Execute Chrome DevTools Protocol command to print to PDF
                pdf_data = self.browser.execute_cdp_cmd("Page.printToPDF", print_params)
                
                if pdf_data and 'data' in pdf_data:
                    # Save the PDF
                    with open(file_path, "wb") as f:
                        f.write(base64.b64decode(pdf_data['data']))
                    
                    logger.info(f"Successfully saved PDF: {file_path}")
                else:
                    raise Exception("Failed to generate PDF data")
                    
            except Exception as cdp_error:
                logger.error(f"CDP print failed: {cdp_error}")
                
                try:
                    # Try the second method: JavaScript printing
                    logger.info("Trying JavaScript printing...")
                    
                    # Look for print buttons on the page
                    print_buttons = []
                    
                    try:
                        # Try different selectors for print buttons
                        print_selectors = [
                            (By.ID, "btnPrint"),
                            (By.ID, "ContentPlaceHolder1_btnPrint"),
                            (By.XPATH, "//input[@value='Print']"),
                            (By.XPATH, "//button[contains(text(), 'Print')]"),
                            (By.CSS_SELECTOR, "input[value='Print']"),
                            (By.CSS_SELECTOR, "button.print-button"),
                            (By.CSS_SELECTOR, "a.print-button"),
                            (By.CSS_SELECTOR, "[onclick*='print']")
                        ]
                        
                        for selector_type, selector in print_selectors:
                            buttons = self.browser.find_elements(selector_type, selector)
                            if buttons:
                                print_buttons.extend(buttons)
                    except:
                        pass
                    
                    if print_buttons:
                        logger.info(f"Found {len(print_buttons)} print buttons, clicking the first one")
                        print_buttons[0].click()
                        time.sleep(5)  # Wait for print dialog
                    else:
                        logger.info("No print buttons found, using window.print()")
                        
                        # Save current page as HTML first as backup
                        html_content = self.browser.page_source
                        html_path = os.path.join(dir_path, f"Index-2_{property_info.get('district_name')}_{property_info.get('village_name')}_{property_info.get('property_number')}_{property_info.get('year')}.html")
                        with open(html_path, "w", encoding="utf-8") as f:
                            f.write(html_content)
                        logger.info(f"Saved HTML content to {html_path}")
                        
                        # Try to use window.print()
                        self.browser.execute_script("window.print();")
                        time.sleep(5)  # Wait for print dialog
                        
                        # Since we can't directly interact with the print dialog, inform the user
                        logger.warning("Print dialog opened. Please manually save as PDF and press ENTER to continue...")
                        # In a real script, you might want to use input() here or a different approach
                        
                        # Save a placeholder message since we can't automate the print dialog
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write("PDF could not be automatically generated. Please see the HTML version.")
                        
                except Exception as js_print_error:
                    logger.error(f"JavaScript printing also failed: {js_print_error}")
                    
                    # Final fallback: Save the page source
                    try:
                        logger.info("Saving page source as fallback...")
                        html_content = self.browser.page_source
                        html_path = os.path.join(dir_path, f"Index-2_{property_info.get('district_name')}_{property_info.get('village_name')}_{property_info.get('property_number')}_{property_info.get('year')}.html")
                        with open(html_path, "w", encoding="utf-8") as f:
                            f.write(html_content)
                        logger.info(f"Saved HTML content to {html_path}")
                        
                        # Create a placeholder PDF with a note
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write("PDF could not be generated. Please see the HTML version.")
                    except Exception as html_error:
                        logger.error(f"Error saving HTML: {html_error}")
                        raise
            
            # Check if file exists and has reasonable size
            if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                # Upload to Google Drive
                file_id = self.upload_to_drive(file_path, property_info)
                
                return {
                    "success": True,
                    "file_id": file_id,
                    "file_name": filename,
                    "drive_link": f"https://drive.google.com/file/d/{file_id}/view"
                }
            else:
                logger.warning(f"PDF file seems too small or missing: {file_path}")
                
                # Try to find an iframe to extract content
                try:
                    iframes = self.browser.find_elements(By.TAG_NAME, "iframe")
                    if iframes:
                        logger.info(f"Found {len(iframes)} iframes, switching to the first one")
                        self.browser.switch_to.frame(iframes[0])
                        
                        # Save the iframe content
                        iframe_content = self.browser.page_source
                        iframe_path = os.path.join(dir_path, f"Index-2_iframe_{property_info.get('district_name')}_{property_info.get('village_name')}_{property_info.get('property_number')}_{property_info.get('year')}.html")
                        with open(iframe_path, "w", encoding="utf-8") as f:
                            f.write(iframe_content)
                        logger.info(f"Saved iframe content to {iframe_path}")
                        
                        # Switch back to main content
                        self.browser.switch_to.default_content()
                except Exception as iframe_error:
                    logger.error(f"Error processing iframe: {iframe_error}")
                
                return {
                    "success": False,
                    "file_path": file_path,
                    "file_name": filename,
                    "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                    "error": "PDF generation failed or file is too small"
                }
        
        except Exception as e:
            logger.error(f"Error downloading IndexII document: {e}")
            self.browser.save_screenshot(os.path.join(self.downloads_path, "download_indexii_error.png"))
            raise

    def download_all_index2_documents(self):
        """Download all documents from the search results table, handling pagination"""
        logger.info("Downloading all documents from search results...")
        
        try:
            # First check if we're on the search results page with a table
            if not self.browser.find_elements(By.ID, "RegistrationGrid"):
                logger.error("No search results table found")
                self.browser.save_screenshot(os.path.join(self.downloads_path, "no_results_table.png"))
                raise Exception("No search results table found")
            
            all_results = []
            original_window = self.browser.current_window_handle
            current_page = 1
            
            # Process each page of results
            while True:
                logger.info(f"Processing page {current_page} of results")
                
                # Take a screenshot of the current page
                self.browser.save_screenshot(os.path.join(self.downloads_path, f"search_results_page_{current_page}.png"))
                
                # Process the current page
                try:
                    # We need to collect all data and buttons first, before processing any
                    documents_to_process = []
                    
                    try:
                        # Find the registration grid
                        grid = self.browser.find_element(By.ID, "RegistrationGrid")
                        
                        # Find all rows except the header
                        rows = grid.find_elements(By.TAG_NAME, "tr")
                        
                        # Check if the last row is pagination
                        pagination_row = None
                        if len(rows) > 2 and "Page$" in rows[-1].get_attribute("innerHTML"):
                            pagination_row = rows[-1]
                            # Remove the pagination row from processing
                            rows = rows[1:-1]  # Skip header and pagination rows
                        else:
                            # Skip just the header row
                            rows = rows[1:]
                        
                        # Process each row to extract data and button
                        for i, row in enumerate(rows):
                            try:
                                # Extract information from the row
                                columns = row.find_elements(By.TAG_NAME, "td")
                                
                                doc_number = columns[0].text.strip() if len(columns) > 0 else f"Unknown_{i+1}"
                                doc_type = columns[1].text.strip() if len(columns) > 1 else "Unknown"
                                reg_date = columns[2].text.strip() if len(columns) > 2 else "Unknown"
                                sro_name = columns[3].text.strip() if len(columns) > 3 else "Unknown"
                                
                                # Find the IndexII button in this row
                                index2_button = None
                                for column in columns:
                                    buttons = column.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
                                    if buttons:
                                        index2_button = buttons[0]
                                        break
                                
                                if not index2_button:
                                    logger.warning(f"No IndexII button found in row {i+1}")
                                    continue
                                
                                property_info = {
                                    "doc_number": doc_number,
                                    "doc_type": doc_type,
                                    "reg_date": reg_date,
                                    "sro_name": sro_name,
                                    "district_name": self.get_district_name(None),
                                    "taluka_name": self.get_taluka_name(None),
                                    "village_name": self.get_village_name(None),
                                    "property_number": f"{self.current_property_number}_{doc_number}",
                                    "year": reg_date.split('/')[-1] if '/' in reg_date else "Unknown",
                                    "page": current_page
                                }
                                
                                # Store the row info, not the button itself (to avoid stale element issues)
                                documents_to_process.append({
                                    "row_index": i,
                                    "property_info": property_info
                                })
                                
                            except Exception as row_error:
                                logger.warning(f"Error processing row {i+1}: {row_error}")
                    
                    except Exception as grid_error:
                        logger.error(f"Error processing registration grid: {grid_error}")
                        
                        # Fallback: Try to find buttons directly
                        index2_buttons = self.browser.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
                        
                        for i, button in enumerate(index2_buttons):
                            property_info = {
                                "doc_number": f"doc_{i+1}",
                                "district_name": self.get_district_name(None),
                                "taluka_name": self.get_taluka_name(None),
                                "village_name": self.get_village_name(None),
                                "property_number": f"{self.current_property_number}_{i+1}",
                                "year": "Unknown",
                                "page": current_page
                            }
                            
                            documents_to_process.append({
                                "button_index": i,
                                "property_info": property_info
                            })
                    
                    # Now process each document on the current page
                    logger.info(f"Found {len(documents_to_process)} documents to process on page {current_page}")
                    
                    for i, doc_info in enumerate(documents_to_process):
                        try:
                            logger.info(f"Processing document {i+1} of {len(documents_to_process)} on page {current_page}")
                            
                            # Take screenshot before starting
                            self.browser.save_screenshot(os.path.join(self.downloads_path, f"before_processing_page{current_page}_doc{i+1}.png"))
                            
                            # We need to find the button again to avoid stale element issues
                            index2_buttons = []
                            max_retries = 3
                            retry_count = 0
                            
                            while retry_count < max_retries and not index2_buttons:
                                try:
                                    # Try multiple ways to find the buttons
                                    index2_buttons = self.browser.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
                                    if not index2_buttons:
                                        # Try finding within the grid
                                        grid = self.browser.find_element(By.ID, "RegistrationGrid")
                                        index2_buttons = grid.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
                                except:
                                    retry_count += 1
                                    time.sleep(1)
                            
                            if not index2_buttons or len(index2_buttons) <= i:
                                logger.error(f"Button for document {i+1} not found or index out of range")
                                continue
                            
                            # Get the current button to click
                            button = index2_buttons[i]
                            property_info = doc_info["property_info"]
                            
                            # Store all current window handles before clicking
                            handles_before = set(self.browser.window_handles)
                            
                            # Wait a moment before clicking to ensure the page is ready
                            time.sleep(1)
                            
                            # Use JavaScript to click the button
                            self.browser.execute_script("arguments[0].click();", button)
                            logger.info(f"Clicked IndexII button {i+1} on page {current_page}")
                            
                            # Wait for new window/tab to open
                            wait_start = time.time()
                            max_wait = 30  # seconds
                            new_handle = None
                            
                            while time.time() - wait_start < max_wait:
                                handles_after = set(self.browser.window_handles)
                                new_handles = handles_after - handles_before
                                
                                if new_handles:
                                    new_handle = list(new_handles)[0]
                                    logger.info(f"New window opened with handle: {new_handle}")
                                    break
                                
                                time.sleep(0.5)
                            
                            # Switch to the newly opened window/tab if found
                            if new_handle:
                                self.browser.switch_to.window(new_handle)
                                logger.info(f"Switched to new window with URL: {self.browser.current_url}")
                                
                                # Wait for the page to load
                                try:
                                    WebDriverWait(self.browser, 60).until(
                                        lambda d: d.execute_script("return document.readyState") == "complete"
                                    )
                                except:
                                    logger.warning("Timeout waiting for page to load completely")
                                
                                # Take screenshot after switching
                                self.browser.save_screenshot(os.path.join(self.downloads_path, f"after_switch_page{current_page}_doc{i+1}.png"))
                                
                                # Download the document
                                try:
                                    result = self.download_indexii_document(self.browser.current_url, property_info)
                                    all_results.append(result)
                                    logger.info(f"Successfully downloaded document {i+1} from page {current_page}")
                                except Exception as download_error:
                                    logger.error(f"Error downloading document {i+1} from page {current_page}: {download_error}")
                                
                                # Close the tab and switch back to the original window
                                self.browser.close()
                                self.browser.switch_to.window(original_window)
                                logger.info(f"Closed document window and switched back to search results")
                                
                                # Wait a moment for the page to stabilize after switching back
                                time.sleep(2)
                                
                                # DO NOT refresh the page - instead wait for elements to be interactive
                                try:
                                    # Wait for the grid to be present and interactive
                                    WebDriverWait(self.browser, 30).until(
                                        EC.presence_of_element_located((By.ID, "RegistrationGrid"))
                                    )
                                    time.sleep(1)  # Short wait for stability
                                except Exception as wait_error:
                                    logger.warning(f"Error waiting for grid after switch: {wait_error}")
                                    # Continue anyway as the elements might still be usable
                        
                        except Exception as button_error:
                            logger.error(f"Processing document {i+1} on page {current_page}: {button_error}")
                            self.browser.save_screenshot(os.path.join(self.downloads_path, f"doc_error_page{current_page}_doc{i+1}.png"))
                            
                            # Try to switch back to original window
                            try:
                                self.browser.switch_to.window(original_window)
                            except:
                                pass
                    
                    # Check if we should navigate to the next page
                    has_more_pages = False
                    next_page_xpath = None
                    
                    try:
                        # Find the registration grid again
                        grid = self.browser.find_element(By.ID, "RegistrationGrid")
                        rows = grid.find_elements(By.TAG_NAME, "tr")
                        
                        # Find pagination row
                        if len(rows) > 2 and "Page$" in rows[-1].get_attribute("innerHTML"):
                            pagination_row = rows[-1]
                            
                            # Look for next page link
                            next_page_num = current_page + 1
                            next_page_xpath = f".//a[contains(@href, 'Page${next_page_num}')]"
                            next_page_links = pagination_row.find_elements(By.XPATH, next_page_xpath)
                            
                            if next_page_links:
                                has_more_pages = True
                                logger.info(f"Found link to next page: {next_page_num}")
                            else:
                                # Look for "..." link that might lead to more pages
                                dots_xpath = ".//a[text()='...']"
                                dots_links = pagination_row.find_elements(By.XPATH, dots_xpath)
                                if dots_links:
                                    has_more_pages = True
                                    next_page_xpath = dots_xpath
                                    logger.info("Found '...' link to more pages")
                                else:
                                    logger.info("No more pages found")
                    except Exception as pagination_error:
                        logger.warning(f"Error checking pagination: {pagination_error}")
                        has_more_pages = False
                        next_page_xpath = None
                    
                    if has_more_pages and next_page_xpath:
                        logger.info(f"Navigating to page {current_page + 1}")
                        
                        try:
                            # Save screenshot before clicking
                            self.browser.save_screenshot(os.path.join(self.downloads_path, f"before_page_{current_page + 1}.png"))
                            
                            # Find the next page link again to avoid stale element
                            next_page_link = self.browser.find_element(By.XPATH, next_page_xpath)
                            
                            # Try regular click first
                            try:
                                next_page_link.click()
                                logger.info("Clicked next page link")
                            except:
                                # If regular click fails, try JavaScript click
                                logger.info("Regular click failed, trying JavaScript click")
                                self.browser.execute_script("arguments[0].click();", next_page_link)
                            
                            # Wait for the current grid to become stale
                            WebDriverWait(self.browser, 30).until(
                                EC.staleness_of(grid)
                            )
                            
                            # Wait for the new grid to appear
                            WebDriverWait(self.browser, 30).until(
                                EC.presence_of_element_located((By.ID, "RegistrationGrid"))
                            )
                            
                            # Additional wait for page to stabilize
                            time.sleep(3)
                            
                            # Verify we're on the next page
                            try:
                                new_grid = self.browser.find_element(By.ID, "RegistrationGrid")
                                new_rows = new_grid.find_elements(By.TAG_NAME, "tr")
                                if len(new_rows) > 1:  # At least header row and one data row
                                    current_page += 1
                                    logger.info(f"Successfully navigated to page {current_page}")
                                else:
                                    logger.warning("New page appears to be empty")
                            except:
                                logger.warning("Could not verify new page content")
                            
                            # Save screenshot after navigation
                            self.browser.save_screenshot(os.path.join(self.downloads_path, f"after_page_{current_page}.png"))
                            
                        except Exception as navigation_error:
                            logger.error(f"Error navigating to next page: {navigation_error}")
                            self.browser.save_screenshot(os.path.join(self.downloads_path, f"navigation_error_page{current_page}.png"))
                            break
                    else:
                        logger.info(f"No more pages to process after page {current_page}")
                        break
                    
                except Exception as page_error:
                    logger.error(f"Error processing page {current_page}: {page_error}")
                    self.browser.save_screenshot(os.path.join(self.downloads_path, f"page_error_{current_page}.png"))
                    break
            
            logger.info(f"Downloaded {len(all_results)} documents successfully from {current_page} pages")
            return all_results
            
        except Exception as e:
            logger.error(f"Error downloading all documents: {e}")
            self.browser.save_screenshot(os.path.join(self.downloads_path, "download_all_error.png"))
            raise

    def test_page_navigation(self):
        """Test page navigation in search results without downloading documents"""
        logger.info("Testing page navigation in search results...")
        
        try:
            # First check if we're on the search results page with a table
            if not self.browser.find_elements(By.ID, "RegistrationGrid"):
                logger.error("No search results table found")
                self.browser.save_screenshot(os.path.join(self.downloads_path, "no_results_table.png"))
                raise Exception("No search results table found")
            
            all_results = []
            current_page = 1
            
            # Process each page of results
            while True:
                logger.info(f"Processing page {current_page} of results")
                
                # Take a screenshot of the current page
                self.browser.save_screenshot(os.path.join(self.downloads_path, f"search_results_page_{current_page}.png"))
                
                try:
                    # Find the registration grid
                    grid = self.browser.find_element(By.ID, "RegistrationGrid")
                    
                    # Find all rows except the header
                    rows = grid.find_elements(By.TAG_NAME, "tr")
                    
                    # Check if the last row is pagination
                    pagination_row = None
                    if len(rows) > 2 and "Page$" in rows[-1].get_attribute("innerHTML"):
                        pagination_row = rows[-1]
                        # Remove the pagination row from processing
                        rows = rows[1:-1]  # Skip header and pagination rows
                    else:
                        # Skip just the header row
                        rows = rows[1:]
                    
                    # Log the number of records on current page
                    logger.info(f"Found {len(rows)} records on page {current_page}")
                    
                    # Save page source for analysis
                    page_source_path = os.path.join(self.downloads_path, f"page_{current_page}_source.html")
                    with open(page_source_path, "w", encoding="utf-8") as f:
                        f.write(self.browser.page_source)
                    logger.info(f"Saved page source to {page_source_path}")
                    
                    # Process each row to extract data (without clicking buttons)
                    for i, row in enumerate(rows):
                        try:
                            # Extract information from the row
                            columns = row.find_elements(By.TAG_NAME, "td")
                            
                            doc_info = {
                                "doc_number": columns[0].text.strip() if len(columns) > 0 else f"Unknown_{i+1}",
                                "doc_type": columns[1].text.strip() if len(columns) > 1 else "Unknown",
                                "reg_date": columns[2].text.strip() if len(columns) > 2 else "Unknown",
                                "sro_name": columns[3].text.strip() if len(columns) > 3 else "Unknown",
                                "page": current_page
                            }
                            
                            all_results.append(doc_info)
                            logger.info(f"Processed record {i+1} on page {current_page}: {doc_info['doc_number']}")
                            
                        except Exception as row_error:
                            logger.warning(f"Error processing row {i+1} on page {current_page}: {row_error}")
                    
                    # Check if pagination exists and if there are more pages
                    has_more_pages = False
                    next_page_link = None
                    
                    if pagination_row:
                        try:
                            # Look for links to next pages
                            next_page_num = current_page + 1
                            next_page_links = pagination_row.find_elements(By.XPATH, f".//a[contains(@href, 'Page${next_page_num}')]")
                            
                            if next_page_links:
                                next_page_link = next_page_links[0]
                                has_more_pages = True
                                logger.info(f"Found link to next page: {next_page_num}")
                            else:
                                # Look for "..." link that might lead to more pages
                                dots_xpath = ".//a[text()='...']"
                                dots_links = pagination_row.find_elements(By.XPATH, dots_xpath)
                                if dots_links:
                                    has_more_pages = True
                                    next_page_xpath = dots_xpath
                                    logger.info("Found '...' link to more pages")
                                else:
                                    logger.info("No more pages found")
                        
                        except Exception as pagination_error:
                            logger.warning(f"Error checking pagination: {pagination_error}")
                    
                    # Navigate to next page if available
                    if has_more_pages and next_page_link:
                        logger.info(f"Attempting to navigate to page {current_page + 1}")
                        
                        try:
                            # Save screenshot before clicking
                            self.browser.save_screenshot(os.path.join(self.downloads_path, f"before_page_{current_page + 1}.png"))
                            
                            # Find the next page link again to avoid stale element
                            next_page_link = self.browser.find_element(By.XPATH, next_page_xpath)
                            
                            # Try regular click first
                            try:
                                next_page_link.click()
                                logger.info("Clicked next page link")
                            except:
                                # If regular click fails, try JavaScript click
                                logger.info("Regular click failed, trying JavaScript click")
                                self.browser.execute_script("arguments[0].click();", next_page_link)
                            
                            # Wait for the current grid to become stale
                            WebDriverWait(self.browser, 30).until(
                                EC.staleness_of(grid)
                            )
                            
                            # Wait for the new grid to appear
                            WebDriverWait(self.browser, 30).until(
                                EC.presence_of_element_located((By.ID, "RegistrationGrid"))
                            )
                            
                            # Additional wait for page to stabilize
                            time.sleep(10)
                            
                            # Verify we're on the next page
                            try:
                                new_grid = self.browser.find_element(By.ID, "RegistrationGrid")
                                new_rows = new_grid.find_elements(By.TAG_NAME, "tr")
                                if len(new_rows) > 1:  # At least header row and one data row
                                    current_page += 1
                                    logger.info(f"Successfully navigated to page {current_page}")
                                else:
                                    logger.warning("New page appears to be empty")
                            except:
                                logger.warning("Could not verify new page content")
                            
                            # Save screenshot after navigation
                            self.browser.save_screenshot(os.path.join(self.downloads_path, f"after_page_{current_page}.png"))
                            
                        except Exception as navigation_error:
                            logger.error(f"Error navigating to next page: {navigation_error}")
                            self.browser.save_screenshot(os.path.join(self.downloads_path, f"navigation_error_page{current_page}.png"))
                            break
                    else:
                        logger.info(f"No more pages to process after page {current_page}")
                        break
                    
                except Exception as page_error:
                    logger.error(f"Error processing page {current_page}: {page_error}")
                    self.browser.save_screenshot(os.path.join(self.downloads_path, f"page_error_{current_page}.png"))
                    break
            
            logger.info(f"Successfully processed {len(all_results)} records across {current_page} pages")
            
            # Save all results to a JSON file
            results_file = os.path.join(self.downloads_path, "navigation_results.json")
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved all results to {results_file}")
            
            return all_results
            
        except Exception as e:
            logger.error(f"Error in page navigation test: {e}")
            self.browser.save_screenshot(os.path.join(self.downloads_path, "navigation_test_error.png"))
            raise

    def is_new_captcha_present(self):
        """Check if a new captcha appears after search button click"""
        try:
            # Check for captcha image
            captcha_element = self.browser.find_element(By.ID, "imgCaptcha_new")
            # Check for captcha input field
            captcha_input = self.browser.find_element(By.ID, "txtImg1")
            return captcha_element.is_displayed() and captcha_input.is_displayed()
        except:
            return False

    def solve_and_submit_new_captcha(self):
        """Solve and submit new captcha that appears after search button click"""
        try:
            # Solve the new captcha
            captcha_text = self.solve_captcha()
            
            # Enter the new captcha
            captcha_input = self.browser.find_element(By.ID, "txtImg1")
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)
            
            # Click search button again
            search_button = self.browser.find_element(By.ID, "btnSearch_RestMaha")
            search_button.click()
            logger.info("Submitted new captcha and clicked search button again")
            
            # Wait 40 seconds after submitting new captcha
            logger.info("Waiting 40 seconds after submitting new captcha...")
            time.sleep(40)
            
        except Exception as e:
            logger.error(f"Error handling new captcha: {e}")
            raise
    
    def get_district_name(self, district_code):
        """Get district name from code"""
        try:
            if not district_code:
                # Try to get from current dropdown selection
                element = self.browser.find_element(By.ID, "ddlDistrict1")
                select = Select(element)
                return select.first_selected_option.text.strip()
            else:
                element = self.browser.find_element(By.ID, "ddlDistrict1")
                select = Select(element)
                for option in select.options:
                    if option.get_attribute("value") == str(district_code):
                        return option.text.strip()
        except:
            pass
        return None
    
    def get_taluka_name(self, taluka_code):
        """Get taluka name from code"""
        try:
            if not taluka_code:
                # Try to get from current dropdown selection
                element = self.browser.find_element(By.ID, "ddltahsil")
                select = Select(element)
                return select.first_selected_option.text.strip()
            else:
                element = self.browser.find_element(By.ID, "ddltahsil")
                select = Select(element)
                for option in select.options:
                    if option.get_attribute("value") == str(taluka_code):
                        return option.text.strip()
        except:
            pass
        return None
    
    def get_village_name(self, village_code):
        """Get village name from code"""
        try:
            if not village_code:
                # Try to get from current dropdown selection
                element = self.browser.find_element(By.ID, "ddlvillage")
                select = Select(element)
                return select.first_selected_option.text.strip()
            else:
                element = self.browser.find_element(By.ID, "ddlvillage")
                select = Select(element)
                for option in select.options:
                    if option.get_attribute("value") == str(village_code):
                        return option.text.strip()
        except:
            pass
        return None
    
    def close(self):
        """Close the browser"""
        if self.browser:
            logger.info("Closing browser")
            try:
                self.browser.quit()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            self.browser = None
            
    def download_document(self, params):
        """Download documents based on the provided parameters"""
        year = params['year']
        district_name = params['district_name']
        taluka_name = params['taluka_name']
        village_name = params['village_name']
        property_number = params['property_number']
        navigation_only = params.get('navigation_only', False)
        
        logger.info(f"Starting {'navigation test' if navigation_only else 'download process'} for property {property_number}...")
        
        try:
            # Navigate to search page
            self.navigate_to_search_page()
            
            # Fill search form
            self.fill_search_form(
                year, district_name, taluka_name, 
                village_name, property_number
            )
            
            # Submit form
            self.submit_search_form()
            
            # If we just want to test navigation
            if navigation_only:
                logger.info("Navigation-only mode: testing pagination without downloading documents")
                results = self.test_page_navigation()
                return {
                    "success": True,
                    "records": results,
                    "count": len(results),
                    "navigation_test": True
                }
            # If we want to download all docs in the search results
            elif params.get('download_all', False):
                results = self.download_all_index2_documents()
                return {
                    "success": True,
                    "results": results,
                    "count": len(results)
                }
            else:
                # Find all IndexII buttons first to know how many are available
                index2_buttons = self.browser.find_elements(By.CSS_SELECTOR, "input[value='IndexII']")
                if index2_buttons:
                    logger.info(f"Found {len(index2_buttons)} IndexII buttons, downloading all")
                    results = self.download_all_index2_documents()
                    return {
                        "success": True,
                        "results": results,
                        "count": len(results)
                    }
                else:
                    # If no buttons found, try the original method
                    # Click Index-2 link and get PDF content
                    logger.info("No IndexII buttons found directly, trying single document method")
                    index2_url = self.click_index2_link()
                    
                    # Create property info object
                    property_info = {
                        "district_name": district_name,
                        "taluka_name": taluka_name,
                        "village_name": village_name,
                        "property_number": property_number,
                        "year": year
                    }
                    
                    # Download the document
                    result = self.download_indexii_document(index2_url, property_info)
                    
                    return result
                
        except Exception as e:
            logger.error(f"Error downloading document: {e}")
            raise

@app.route('/', methods=['GET', 'POST'])
def index():
    # Sample data for dropdowns
    years = [str(year) for year in range(1983, 2026)]
    districts = {
        'पुणे': {
            'तालुका': ['मुळ्शी', 'हवेली', 'पुरंदर'],
            'गाव': {
                'मुळ्शी': ['हिंजवडी', 'पिंपरी', 'चिंचवड'],
                'हवेली': ['कसबा पेठ', 'शिवाजीनगर', 'भोर'],
                'पुरंदर': ['सासवड', 'जेजुरी', 'नारायणगाव']
            }
        },
        'मुंबई': {
            'तालुका': ['मुंबई सिटी', 'मुंबई उपनगर'],
            'गाव': {
                'मुंबई सिटी': ['कोलाबा', 'फोर्ट', 'मरीन ड्राइव'],
                'मुंबई उपनगर': ['अंधेरी', 'बांद्रा', 'जुहू']
            }
        }
    }

    if request.method == 'POST':
        # Get form data
        params = {
            'year': request.form['year'],
            'district_name': request.form['district_name'],
            'taluka_name': request.form['taluka_name'],
            'village_name': request.form['village_name'],
            'property_number': request.form['property_number'],
            'download_all': 'download_all' in request.form
        }

        # Initialize downloader
        downloader = Index2Downloader(headless=True, downloads_path='downloads')
        try:
            downloader.initialize()
            result = downloader.download_document(params)
            return render_template('result.html', result=result)
        except Exception as e:
            return render_template('error.html', error=str(e))
        finally:
            downloader.close()
    
    return render_template('index.html', years=years, districts=districts)

if __name__ == "__main__":
    app.run(debug=True,port=5008)