import time
from pathlib import Path
from playwright.sync_api import sync_playwright

auth_file = Path("auth_state_04083941.json")
ou = "155399"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(storage_state=str(auth_file), viewport={"width": 1400, "height": 900}).new_page()
    page.goto(f"https://ava.catolica.edu.br/d2l/lms/quickeval/quickeval.d2l?ou={ou}", wait_until="domcontentloaded")
    time.sleep(3)

    tab = page.locator("d2l-tab:has-text('Atividades'), button:has-text('Atividades')").first
    if tab.count() > 0:
        print("Clicando na aba Atividades...")
        tab.click()
        time.sleep(3)

    links = page.locator("a[href*='evaluation/activity']")
    print("Total links evaluation/activity no Quick Eval:", links.count())
    for i in range(links.count()):
        txt = links.nth(i).inner_text().replace("\n", " ")
        href = links.nth(i).get_attribute("href")
        print(f"  Link {i}: {txt} | {href}")

    browser.close()
