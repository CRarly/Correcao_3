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

        const contents = querySelectorAllDeep('d2l-my-courses-content-v2, d2l-my-courses-card-grid-v2');
        const contentDetails = contents.map(c => {
            const shadowHTML = c.shadowRoot ? c.shadowRoot.innerHTML : '';
            const allShadowElements = c.shadowRoot ? Array.from(c.shadowRoot.querySelectorAll('*')).map(e => e.tagName + (e.className ? '.' + e.className : '') + (e.innerText ? ' [' + e.innerText.trim().substring(0, 40) + ']' : '')) : [];
            return {
                tag: c.tagName,
                id: c.id,
                hasShadow: !!c.shadowRoot,
                shadowElements: allShadowElements,
                lightButtons: Array.from(c.querySelectorAll('button, a, d2l-button, d2l-button-subtle')).map(b => b.outerHTML.substring(0, 100))
            };
        });

        // Procurar em TODO o d2l-my-courses-container-v2 por botões ou links
        const container = document.querySelector('d2l-my-courses-container-v2') || querySelectorAllDeep('d2l-my-courses-container-v2')[0];
        let containerInfo = null;
        if (container) {
            const deepBtns = querySelectorAllDeep('button, a, d2l-button, d2l-button-subtle', container);
            containerInfo = deepBtns.map(b => ({
                tag: b.tagName,
                text: (b.innerText || b.getAttribute('text') || '').trim(),
                ariaLabel: b.getAttribute('aria-label'),
                classes: b.className,
                outer: b.outerHTML.substring(0, 150)
            })).filter(b => b.text || b.ariaLabel);
        }

        return {
            contentDetails,
            containerInfo
        };
    }""")

    import json
    print(json.dumps(info, indent=2, ensure_ascii=False))
    browser.close()

