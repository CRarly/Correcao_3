import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
import time
from playwright.sync_api import sync_playwright
from config import BASE_AVA_URL

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(storage_state='auth_state_04084531.json', viewport={'width': 1280, 'height': 900})
    page = ctx.new_page()
    page.goto(f'{BASE_AVA_URL}/d2l/home', wait_until='domcontentloaded', timeout=60000)
    time.sleep(3)
    
    user_info = page.evaluate("""() => {
        function querySelectorAllDeep(selector, root = document) {
            let results = Array.from(root.querySelectorAll(selector));
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
            let node;
            while (node = walker.nextNode()) {
                if (node.shadowRoot) {
                    results = results.concat(querySelectorAllDeep(selector, node.shadowRoot));
                }
            }
            return results;
        }

        const navPersonal = querySelectorAllDeep('.d2l-navigation-s-personal-menu, .d2l-navigation-s-personal-menu-text, d2l-labs-navigation-dropdown-button-custom, [aria-label*="usuário"], [aria-label*="usuario"], [aria-label*="conta"], [aria-label*="Perfil"]');
        return navPersonal.map(el => ({
            tag: el.tagName,
            classes: el.className,
            text: el.innerText,
            ariaLabel: el.getAttribute('aria-label'),
            title: el.getAttribute('title')
        }));
    }""")
    print('User info elements:', user_info)
    browser.close()

