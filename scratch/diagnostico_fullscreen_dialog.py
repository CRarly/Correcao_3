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

    dialog_info = page.evaluate("""async () => {
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

        // Clicar no link viewAllCourses
        const links = querySelectorAllDeep('#viewAllCourses, d2l-link');
        const link = links.find(l => (l.innerText || '').includes('Exibir Todos') || (l.id === 'viewAllCourses'));
        
        if (link) {
            link.click();
            await new Promise(r => setTimeout(r, 4000));
        }

        // Inspecionar o dialog que abriu
        const openedDialog = querySelectorAllDeep('d2l-dialog-fullscreen').find(d => d.hasAttribute('opened'));
        let res = { openedDialogFound: !!openedDialog };

        if (openedDialog) {
            const allElementsInside = querySelectorAllDeep('*', openedDialog);
            res.elementsInsideCount = allElementsInside.length;
            res.tagsInside = Array.from(new Set(allElementsInside.map(e => e.tagName)));

            // Procurar cards ou links de cursos dentro do dialog
            const cardsInside = querySelectorAllDeep('d2l-card, d2l-enrollment-card, a[href*="/d2l/home/"]', openedDialog);
            res.cardsInsideCount = cardsInside.length;
            res.sampleCards = cardsInside.slice(0, 10).map(c => ({
                tag: c.tagName,
                text: c.getAttribute('text') || c.innerText,
                href: c.getAttribute('href') || (c.querySelector('a') ? c.querySelector('a').href : '')
            }));

            // Procurar tabs ou filtros dentro do dialog (ex: abas por período dentro do diálogo ou busca)
            const tabsInside = querySelectorAllDeep('d2l-tab, [role="tab"], select, input', openedDialog);
            res.controlsInside = tabsInside.map(t => ({
                tag: t.tagName,
                id: t.id,
                text: t.innerText || t.getAttribute('text') || t.getAttribute('title') || t.placeholder
            }));
        }

        return res;
    }""")

    print(json.dumps(dialog_info, indent=2, ensure_ascii=False))
    browser.close()
