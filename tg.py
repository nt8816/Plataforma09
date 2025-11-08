# tg.py
"""
Automação Moodle Seduc (versão Codespaces / Linux headless)
- Login com retry
- Seleção de semana (por texto)
- Coleta de links de atividades (mod/quiz, mod/forum)
- Processa quizzes (respostas aleatórias) e fóruns (responde "Concordo total")
- Salva screenshots no workspace
OBS: Use apenas com autorização da plataforma.
"""

import os
import time
import random
import logging
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ================= CONFIG =================
LOGIN_URL = os.getenv("SEDUC_LOGIN_URL", "https://seductec.seduc.pi.gov.br/login/index.php")
COURSE_URL = os.getenv("SEDUC_COURSE_URL", "https://seductec.seduc.pi.gov.br/course/view.php?id=41213")
TARGET_WEEK_TEXT = os.getenv("SEDUC_TARGET_WEEK", "S1-AULA 01")
WAIT = int(os.getenv("SEDUC_WAIT", 14))
DELAY_MIN, DELAY_MAX = float(os.getenv("DELAY_MIN", 0.8)), float(os.getenv("DELAY_MAX", 1.8))
OUTDIR = os.getenv("OUTDIR", "_auto_screenshots_logs")
LIMIT = os.getenv("LIMIT", None)
if LIMIT is not None:
    try:
        LIMIT = int(LIMIT)
    except:
        LIMIT = None

USERNAME = os.getenv("SEDUC_USER", "seu_usuario_aqui")
PASSWORD = os.getenv("SEDUC_PASS", "sua_senha_aqui")
HEADLESS = True
# =========================================

os.makedirs(OUTDIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("exec.log", encoding="utf-8")])

def human_sleep(a=DELAY_MIN, b=DELAY_MAX):
    time.sleep(random.uniform(a, b))

def start_driver():
    opts = Options()
    if HEADLESS:
        # use new headless if available; if not, fallback is okay
        try:
            opts.add_argument("--headless=new")
        except Exception:
            opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1400,1000")
    opts.add_argument("--log-level=3")
    # optional: set user-agent if sites block headless defaults
    # opts.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) ...")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.set_page_load_timeout(60)
    try:
        driver.maximize_window()
    except:
        pass
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
    try:
        url = driver.current_url.lower()
    except:
        return True
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
    human_sleep(0.6, 1.2)
    try:
        if not is_on_login_page(driver):
            logging.info("Not on login page; assuming already logged in.")
            return True
        # Try common input selectors: name or id
        try:
            u = retry_find(driver, By.NAME, "username", retries=5)
        except:
            u = retry_find(driver, By.ID, "username", retries=5)
        u.clear(); u.send_keys(USERNAME)
        try:
            p = retry_find(driver, By.NAME, "password", retries=5)
        except:
            p = retry_find(driver, By.ID, "password", retries=5)
        p.clear(); p.send_keys(PASSWORD + Keys.ENTER)
        human_sleep(1.2, 2.0)
        # wait user menu or avatar appear
        retry_find(driver, By.CSS_SELECTOR, "div.usermenu, img.avatar, span.usertext", wait_time=18)
        logging.info("Login confirmed.")
        return True
    except Exception as e:
        logging.exception("Login error: %s", e)
        take_screenshot(driver, "login_error")
        return False

def ensure_logged_in(driver):
    if is_on_login_page(driver):
        logging.warning("Session lost! Re-logging...")
        return login(driver)
    return True

# ----------------- Select Week -----------------
def select_week_and_expand(driver, week_text):
    logging.info("Selecting week: %s", week_text)
    driver.get(COURSE_URL)
    human_sleep(0.6, 1.2)
    target = (week_text or "").strip().lower()
    try:
        candidates = driver.find_elements(By.XPATH, "//h2 | //h3 | //span | //div[contains(@class,'sectionname')]")
        for c in candidates:
            try:
                txt = (c.text or "").strip().lower()
                if not txt:
                    txt = (c.get_attribute("innerText") or "").strip().lower()
                if target and target in txt:
                    driver.execute_script("arguments[0].scrollIntoView(true);", c)
                    safe_click(driver, c)
                    human_sleep(0.6, 1.2)
                    logging.info("Selected week: %s", txt)
                    return True
            except Exception:
                continue
    except Exception as e:
        logging.debug("select_week error: %s", e)
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
        # Filter to same host
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
        # try to start attempt buttons if present
        start_buttons = [
            "//button[contains(text(),'Não Terminou') or contains(text(),'Continue AQUI') or contains(text(),'Continuar')]",
            "//button[contains(text(),'Tentativa do questionário')]",
            "//button[contains(text(),'Fazer uma outra tentativa')]",
            "//a[contains(@href,'attempt.php')]",
        ]
        for btn_xpath in start_buttons:
            try:
                btn = driver.find_element(By.XPATH, btn_xpath)
                safe_click(driver, btn)
                logging.info("Clicked start button (quiz).")
                human_sleep(1.0, 2.0)
                break
            except:
                continue

        # Iterate through pages and answer questions
        while True:
            human_sleep(0.5, 1.0)
            questions = driver.find_elements(By.CSS_SELECTOR, ".que, .question, .qitem")
            logging.info("Detected %d question elements on page.", len(questions))
            for q in questions:
                try:
                    # radio/checkbox options: find labels or inputs inside .answer
                    opts = q.find_elements(By.CSS_SELECTOR, "label, .answer input[type='radio'], .answer input[type='checkbox'], .answer .form-check, .answer div")
                    # build list of clickable elements
                    clickable_opts = []
                    for o in opts:
                        try:
                            # prefer label or clickable ancestor
                            if o.tag_name.lower() == "label":
                                clickable_opts.append(o)
                            else:
                                lbl = None
                                try:
                                    lbl = o.find_element(By.XPATH, ".//label")
                                except:
                                    pass
                                if lbl:
                                    clickable_opts.append(lbl)
                        except:
                            continue
                    if clickable_opts:
                        chosen = random.choice(clickable_opts)
                        safe_click(driver, chosen)
                    else:
                        # fill textareas/inputs if present
                        ta = q.find_elements(By.CSS_SELECTOR, "textarea, input[type='text'], input[type='search']")
                        for t in ta:
                            try:
                                t.clear()
                                t.send_keys("Resposta automática")
                            except:
                                continue
                    human_sleep(0.2, 0.6)
                except Exception:
                    continue

            # Try to go to next page
            try:
                # Moodle may have buttons with name 'next' or text 'Próxima página'
                next_btn = driver.find_element(By.XPATH, "//input[@name='next' and (contains(@value,'Próxima') or contains(@value,'Next'))] | //button[contains(text(),'Próxima') or contains(text(),'Next')]")
                safe_click(driver, next_btn)
                logging.info("Clicked Next page")
                human_sleep(0.7, 1.5)
                continue
            except Exception:
                pass

            # If no next, try to finish attempt
            try:
                # finalise attempt link or button
                fin = driver.find_element(By.XPATH, "//button[contains(text(),'Finalizar tentativa')] | //a[contains(@href,'finishattempt.php')] | //button[contains(text(),'Finish attempt')]")
                safe_click(driver, fin)
                logging.info("Clicked Finish attempt")
                human_sleep(0.7, 1.5)
            except Exception:
                logging.debug("Finish attempt not found")

            # Try send all and finish
            try:
                send_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Enviar tudo e terminar')] | //input[@type='submit' and (contains(@value,'Enviar tudo') or contains(@value,'Submit'))]")
                safe_click(driver, send_btn)
                logging.info("Clicked submit all and finish")
                human_sleep(0.8, 1.5)
            except Exception:
                logging.debug("Submit all not found")

            # Confirm if a confirm dialog exists
            try:
                confirm_btn = driver.find_element(By.CSS_SELECTOR, "button[data-action='save'], button[type='submit']")
                safe_click(driver, confirm_btn)
                logging.info("Clicked confirm save")
                human_sleep(1.0, 2.0)
            except Exception:
                logging.debug("Confirm button not found")

            break

        take_screenshot(driver, "quiz_done")
        return True
    except Exception as e:
        logging.exception("Erro ao processar quiz: %s", e)
        take_screenshot(driver, "quiz_error")
        return False

# ----------------- Forum Handling -----------------
def process_forum(driver):
    try:
        human_sleep(0.6, 1.2)
        # try to click responder/new reply
        try:
            responder_btn = driver.find_element(By.CSS_SELECTOR, "a[title='Responder'], a[title='Reply'], a[href*='post.php?'] , button[data-action='reply']")
            safe_click(driver, responder_btn)
            logging.info("Clicked responder button")
            human_sleep(0.6, 1.2)
        except Exception:
            logging.debug("Responder button not found; maybe already on post page")

        # find text area for post (name attribute often 'post' or 'message')
        try:
            campo_texto = retry_find(driver, By.NAME, "post", wait_time=8)
        except Exception:
            try:
                campo_texto = retry_find(driver, By.CSS_SELECTOR, "textarea, div[contenteditable='true']", wait_time=8)
            except Exception:
                campo_texto = None

        if campo_texto:
            try:
                # if it's contenteditable div, use JS to set text
                tag = campo_texto.tag_name.lower()
                if tag == "div" and campo_texto.get_attribute("contenteditable") == "true":
                    driver.execute_script("arguments[0].innerText = arguments[1];", campo_texto, "Concordo total")
                else:
                    campo_texto.clear()
                    campo_texto.send_keys("Concordo total")
                human_sleep(0.6, 1.2)
            except Exception:
                logging.debug("Não foi possível preencher campo do fórum diretamente")

        # submit button
        try:
            enviar_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button[title='Enviar'], span[data-region='submit-text'], input[type='submit']")
            safe_click(driver, enviar_btn)
            logging.info("Mensagem enviada ao fórum")
            human_sleep(1.2, 2.0)
            take_screenshot(driver, "forum_sent")
            return True
        except Exception as e:
            logging.exception("Erro ao enviar mensagem do fórum: %s", e)
            take_screenshot(driver, "forum_error2")
            return False

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
                    logging.error("Could not re-login. Stopping.")
                    break

                logging.info("Activity %d/%d: %s", i+1, len(links), lnk)
                driver.get(lnk)
                human_sleep(1.0, 2.0)

                if is_on_login_page(driver):
                    logging.warning("Redirected to login when opening %s. Trying to login.", lnk)
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
                    logging.info("Non-quiz/forum activity; skipping interaction.")
                    human_sleep(0.6, 1.2)

            except Exception as e:
                logging.warning("Error with activity %s: %s", lnk, e)
                take_screenshot(driver, f"activity_{i+1}_error")
                continue
    finally:
        logging.info("Script finished. Closing browser.")
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    main()