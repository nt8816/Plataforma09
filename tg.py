# auto_seduc_forum_quiz_v3.py
"""
Automação Moodle Seduc
- Login em loop até conseguir
- Seleção de semana e atividades
- Quiz: responde de forma aleatória e confirma envio
- Fórum: responde com "Concordo total"
"""

import os
import time
import random
import logging
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, StaleElementReferenceException,
    ElementClickInterceptedException
)
from webdriver_manager.chrome import ChromeDriverManager

# ============== CONFIG =================
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
LOGIN_URL = "https://seductec.seduc.pi.gov.br/login/index.php"
USERNAME = "64848986800"
PASSWORD = "64848986800"
COURSE_URL = "https://seductec.seduc.pi.gov.br/course/view.php?id=41213"
TARGET_WEEK_TEXT = "S1-AULA 01"
HEADLESS = False
WAIT = 14
DELAY_MIN, DELAY_MAX = 0.8, 1.8
OUTDIR = "auto_screenshots_logs"
LIMIT = None
# ========================================

os.makedirs(OUTDIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ----------------- Utilities -----------------
def human_sleep(a=DELAY_MIN, b=DELAY_MAX):
    time.sleep(random.uniform(a, b))

def start_driver():
    opts = webdriver.ChromeOptions()
    opts.binary_location = CHROME_PATH
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--log-level=3")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.set_page_load_timeout(60)
    driver.maximize_window()
    return driver

def take_screenshot(driver, name):
    try:
        fname = os.path.join(OUTDIR, f"{int(time.time())}_{name}.png")
        driver.save_screenshot(fname)
        logging.info("Screenshot saved: %s", fname)
    except Exception as e:
        logging.warning("Screenshot failed: %s", e)

def retry_find(driver, by, value, wait_time=WAIT, clickable=False, retries=4, poll=0.4):
    last = None
    for _ in range(retries):
        try:
            wait = WebDriverWait(driver, wait_time, poll)
            if clickable:
                return wait.until(EC.element_to_be_clickable((by, value)))
            return wait.until(EC.presence_of_element_located((by, value)))
        except Exception as e:
            last = e
            time.sleep(0.25)
    raise last

def safe_click(driver, el_or_locator):
    for _ in range(4):
        try:
            if isinstance(el_or_locator, tuple):
                el = retry_find(driver, el_or_locator[0], el_or_locator[1], clickable=True)
            else:
                el = el_or_locator
            ActionChains(driver).move_to_element(el).pause(0.1).click(el).perform()
            return True
        except Exception:
            time.sleep(0.25)
    return False

def text_in_element(el):
    try:
        return (el.text or "").strip()
    except:
        try:
            return el.get_attribute("innerText") or ""
        except:
            return ""

# ---------------- Login ----------------
def is_on_login_page(driver):
    url = driver.current_url.lower()
    if "login" in url or "auth" in url:
        try:
            driver.find_element(By.NAME, "username")
            return True
        except Exception:
            pass
    return False

def login(driver):
    logging.info("Opening login page...")
    driver.get(LOGIN_URL)
    human_sleep(0.8, 1.4)
    try:
        if not is_on_login_page(driver):
            logging.info("Not on login page; assuming already logged in.")
            return True
        u = retry_find(driver, By.NAME, "username", retries=5)
        u.clear(); u.send_keys(USERNAME)
        p = retry_find(driver, By.NAME, "password", retries=5)
        p.clear(); p.send_keys(PASSWORD + Keys.ENTER)
        human_sleep(1.2, 2.0)
        retry_find(driver, By.CSS_SELECTOR, "div.usermenu, img.avatar, span.usertext", wait_time=18)
        logging.info("Login confirmed.")
        return True
    except Exception as e:
        logging.exception("Login error: %s", e)
        take_screenshot(driver, "login_error")
        return False

def ensure_logged_in(driver):
    if is_on_login_page(driver):
        logging.warning("Sessão perdida! Refazendo login...")
        return login(driver)
    return True

# ----------------- Select Week -----------------
def select_week_and_expand(driver, week_text):
    logging.info("Selecting week: %s", week_text)
    driver.get(COURSE_URL)
    human_sleep(0.6, 1.2)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/4);")
    target = (week_text or "").strip().lower()
    try:
        candidates = driver.find_elements(By.XPATH, "//h2 | //h3 | //span | //div[contains(@class,'sectionname')]")
        for c in candidates:
            if target in (c.text or "").strip().lower():
                driver.execute_script("arguments[0].scrollIntoView(true);", c)
                safe_click(driver, c)
                human_sleep(0.6, 1.2)
                logging.info("Selected week: %s", c.text)
                return True
    except Exception:
        pass
    logging.warning("Could not find week '%s'.", week_text)
    return False

# ----------------- Collect Activity Links -----------------
def collect_activity_links_in_week(driver, week_text=None):
    driver.get(COURSE_URL)
    human_sleep(0.6, 1.2)
    try:
        hrefs = driver.execute_script("""
            let anchors = Array.from(document.querySelectorAll('a'));
            let hrefs = anchors.map(a => a.href).filter(h => h && h.includes('/mod/'));
            return [...new Set(hrefs)];
        """)
        hrefs = [h for h in hrefs if urlparse(h).netloc == urlparse(COURSE_URL).netloc]
        logging.info("Collected %d activity links.", len(hrefs))
        return hrefs
    except Exception as e:
        logging.exception("collect_activity_links error: %s", e)
        return []

# ----------------- Quiz Handling -----------------
def process_quiz(driver):
    try:
        human_sleep(0.5, 1.2)

        start_buttons = [
            "//button[contains(text(),'Não Terminou, Continue AQUI')]",
            "//button[contains(text(),'Tentativa do questionário')]",
            "//button[contains(text(),'Fazer uma outra tentativa')]"
        ]
        for btn_xpath in start_buttons:
            try:
                btn = driver.find_element(By.XPATH, btn_xpath)
                safe_click(driver, btn)
                logging.info(f"Clicou no botão de início: {btn.text}")
                human_sleep(1.0, 2.0)
                break
            except:
                continue

        while True:
            human_sleep(0.5, 1.0)

            questions = driver.find_elements(By.CSS_SELECTOR, ".que, .question, .qitem")
            logging.info("Detectadas %d perguntas nesta página", len(questions))
            for q in questions:
                try:
                    opts = q.find_elements(By.CSS_SELECTOR, ".answer label, .answer div, label")
                    if opts:
                        chosen = random.choice(opts)
                        safe_click(driver, chosen)
                    else:
                        ta = q.find_elements(By.CSS_SELECTOR, "textarea, input[type='text']")
                        for t in ta:
                            t.clear()
                            t.send_keys("Resposta automática")
                    human_sleep(0.2, 0.6)
                except:
                    continue

            try:
                next_btn = driver.find_element(By.XPATH, "//input[@name='next' and contains(@value,'Próxima página')]")
                safe_click(driver, next_btn)
                logging.info("Clicou em Próxima página")
                human_sleep(0.7, 1.5)
                continue
            except:
                pass

            try:
                fin = driver.find_element(By.ID, "mod_quiz-next-nav")
                safe_click(driver, fin)
                logging.info("Clicou em Finalizar tentativa")
                human_sleep(0.7, 1.5)
            except:
                logging.debug("Finalizar tentativa não encontrado")

            try:
                send_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Enviar tudo e terminar')] | //input[@type='submit' and contains(@value,'Enviar tudo e terminar')]")
                safe_click(driver, send_btn)
                logging.info("Clicou em Enviar tudo e terminar")
                human_sleep(0.8, 1.5)
            except:
                logging.debug("Enviar tudo e terminar não encontrado")

            try:
                confirm_btn = driver.find_element(By.CSS_SELECTOR, "button[data-action='save']")
                safe_click(driver, confirm_btn)
                logging.info("Clicou em Confirmar envio")
                human_sleep(1.0, 2.0)
            except:
                logging.debug("Confirmar envio não encontrado")

            break

        return True
    except Exception as e:
        logging.exception("Erro ao processar quiz: %s", e)
        take_screenshot(driver, "quiz_error")
        return False

# ----------------- Forum Handling -----------------
def process_forum(driver):
    try:
        human_sleep(0.6, 1.2)
        responder_btn = driver.find_element(By.CSS_SELECTOR, "a[title='Responder']")
        safe_click(driver, responder_btn)
        logging.info("Clicou em Responder")

        campo_texto = retry_find(driver, By.NAME, "post")
        campo_texto.clear()
        campo_texto.send_keys("Concordo total")
        logging.info("Mensagem escrita")
        human_sleep(0.8, 1.4)

        enviar_btn = driver.find_element(By.CSS_SELECTOR, "span[data-region='submit-text']")
        safe_click(driver, enviar_btn)
        logging.info("Mensagem enviada ao fórum")
        human_sleep(1.2, 2.0)
        return True
    except Exception as e:
        logging.exception("Erro no fórum: %s", e)
        take_screenshot(driver, "forum_error")
        return False

# ----------------- Main -----------------
def main():
    driver = start_driver()
    try:
        if not login(driver):
            logging.error("Login failed.")
            return

        select_week_and_expand(driver, TARGET_WEEK_TEXT)
        links = collect_activity_links_in_week(driver, TARGET_WEEK_TEXT)

        logging.info("Processing %d activities...", len(links))
        for i, lnk in enumerate(links):
            if LIMIT and i >= LIMIT:
                break
            try:
                if not ensure_logged_in(driver):
                    logging.error("Não foi possível relogar. Encerrando.")
                    break

                logging.info("Activity %d/%d: %s", i+1, len(links), lnk)
                driver.get(lnk)
                human_sleep(1.0, 2.0)

                if is_on_login_page(driver):
                    logging.warning("Redirecionado ao login ao abrir %s. Tentando relogar.", lnk)
                    if not login(driver):
                        break
                    driver.get(lnk)
                    human_sleep(1.0, 2.0)

                cur_url = driver.current_url.lower()
                if "/mod/quiz/" in cur_url:
                    process_quiz(driver)
                elif "/mod/forum/" in cur_url:
                    process_forum(driver)
                else:
                    human_sleep(0.6, 1.2)

            except Exception as e:
                logging.warning("Erro atividade %s: %s", lnk, e)
                take_screenshot(driver, f"activity_{i+1}_error")
                continue
    finally:
        logging.info("Script finished. Closing browser.")
        driver.quit()

if __name__ == "__main__":
    main()
