import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
import time
import json
from playwright.sync_api import sync_playwright
from config import BASE_AVA_URL

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(storage_state='auth_state_04084531.json', viewport={'width': 1280, 'height': 900})
    page = ctx.new_page()
    page.goto(f'{BASE_AVA_URL}/d2l/home', wait_until='domcontentloaded', timeout=60000)
    time.sleep(4)

    # Inspecionar e clicar no link Exibir Todos os Cursos
    res = page.evaluate("""async () => {
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

        const links = querySelectorAllDeep('d2l-link, a').filter(l => {
            const txt = (l.innerText || l.getAttribute('text') || '').toLowerCase();
            return txt.includes('exibir todos') || txt.includes('exibir todas') || txt.includes('todos os cursos') || txt.includes('todas as disciplinas');
        });

        const initialCards = querySelectorAllDeep('d2l-card, d2l-enrollment-card').length;
        
        let linkClicked = null;
        if (links.length > 0) {
            const targetLink = links[0];
            linkClicked = {
                tag: targetLink.tagName,
                text: targetLink.innerText,
                href: targetLink.getAttribute('href') || targetLink.href,
                outerHTML: targetLink.outerHTML.substring(0, 200)
            };
            
            // Clicar no link
            targetLink.click();
            await new Promise(r => setTimeout(r, 3000));
        }

        // Verificar o que apareceu após o clique (dialog, novos cards, etc)
        const dialogs = querySelectorAllDeep('d2l-dialog, d2l-dialog-fullscreen, [role="dialog"]');
        const afterCards = querySelectorAllDeep('d2l-card, d2l-enrollment-card').length;

        return {
            initialCards,
            totalLinksFound: links.length,
            linkClicked,
            dialogsCount: dialogs.length,
            dialogs: dialogs.map(d => ({
                tag: d.tagName,
                title: d.getAttribute('title-text') || d.title,
                opened: d.hasAttribute('opened') || d.getAttribute('aria-hidden') !== 'true',
                cardsInside: d.querySelectorAll('d2l-card, d2l-enrollment-card, a[href*="/d2l/home/"]').length
            })),
            afterCards
        };
    }""")

    print(json.dumps(res, indent=2, ensure_ascii=False))
    page.screenshot(path="scratch/after_click_exibir_todos.png")
    print("Screenshot saved.")
    browser.close()

