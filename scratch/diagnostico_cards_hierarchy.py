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

    info = page.evaluate("""() => {
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

        const cards = querySelectorAllDeep('d2l-card, d2l-enrollment-card');
        if (cards.length === 0) return { error: "Nenhum card encontrado" };

        const c = cards[0];
        const ancestors = [];
        let cur = c;
        while (cur) {
            ancestors.push({
                tag: cur.tagName,
                id: cur.id,
                classes: cur.className,
                slot: cur.getAttribute('slot'),
                role: cur.getAttribute('role')
            });
            cur = cur.parentElement || (cur.parentNode && cur.parentNode.host);
        }

        // Também checar container pai de todos os cards
        const parentContainers = new Set();
        cards.forEach(card => {
            const p = card.parentElement || (card.parentNode && card.parentNode.host);
            if (p) parentContainers.add(p.tagName + '#' + p.id + '.' + p.className);
        });

        // Verificar botão 'Exibir todas as disciplinas' no container ou página
        const allButtons = querySelectorAllDeep('d2l-button-subtle, button, a');
        const viewAllBtn = allButtons.filter(b => {
            const txt = (b.innerText || b.getAttribute('text') || b.getAttribute('aria-label') || '').toLowerCase();
            return txt.includes('exibir todas') || txt.includes('ver todas') || txt.includes('carregar mais');
        }).map(b => ({
            tag: b.tagName,
            text: b.innerText || b.getAttribute('text'),
            id: b.id,
            outerHTML: b.outerHTML.substring(0, 150)
        }));

        return {
            totalCards: cards.length,
            sampleCardAncestors: ancestors,
            parentContainers: Array.from(parentContainers),
            viewAllBtn: viewAllBtn
        };
    }""")

    import json
    print(json.dumps(info, indent=2, ensure_ascii=False))
    browser.close()

