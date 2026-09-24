import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import time
import json
from playwright.sync_api import sync_playwright
from config import BASE_AVA_URL

auth_file = "auth_state_04084531.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(storage_state=auth_file, viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.goto(f"{BASE_AVA_URL}/d2l/home", wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)

    res = page.evaluate("""() => {
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

        const tabs = querySelectorAllDeep('d2l-tab');
        const panels = querySelectorAllDeep('d2l-tab-panel, [role="tabpanel"], .d2l-tab-panel');

        const tabMap = tabs.map(t => {
            const controlsId = t.getAttribute('aria-controls') || '';
            const panel = controlsId ? document.getElementById(controlsId) || querySelectorAllDeep('#' + controlsId)[0] : null;
            const title = t.getAttribute('title') || (t.shadowRoot ? t.shadowRoot.textContent.trim() : '');
            
            let panelCards = [];
            let panelButtons = [];
            let isPanelHidden = true;
            if (panel) {
                isPanelHidden = panel.hasAttribute('hidden') || panel.style.display === 'none' || panel.getAttribute('aria-hidden') === 'true';
                const cards = Array.from(panel.querySelectorAll('d2l-enrollment-card, d2l-card'));
                panelCards = cards.map(c => ({
                    text: c.getAttribute('text') || c.innerText,
                    href: c.getAttribute('href') || (c.querySelector('a') ? c.querySelector('a').href : '')
                }));
                const btns = Array.from(panel.querySelectorAll('d2l-button-subtle, button, a'));
                panelButtons = btns.map(b => (b.innerText || b.getAttribute('text') || '').trim()).filter(Boolean);
            }

            return {
                id: t.id,
                title: title,
                controlsId: controlsId,
                hasPanel: !!panel,
                panelSelected: panel ? panel.getAttribute('selected') : null,
                isPanelHidden: isPanelHidden,
                panelCardsCount: panelCards.length,
                panelCardsSample: panelCards.slice(0, 3),
                panelButtons: panelButtons
            };
        });

        return {
            totalPanels: panels.length,
            panelsInfo: panels.map(p => ({
                id: p.id,
                tag: p.tagName,
                role: p.getAttribute('role'),
                selected: p.getAttribute('selected'),
                hidden: p.hasAttribute('hidden'),
                cardsCount: p.querySelectorAll('d2l-enrollment-card, d2l-card').length
            })),
            tabMap: tabMap
        };
    }""")

    with open("scratch/panels_info.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)

    print("Total panels:", res.get("totalPanels"))
    for p in res.get("panelsInfo", []):
        print("Panel:", p)

    print("\nTabs and panels:")
    for t in res.get("tabMap", []):
        print(f"Tab id={t['id']} | title='{t['title']}' | panelId={t['controlsId']} | cards={t['panelCardsCount']} | btns={t['panelButtons']}")

    browser.close()
