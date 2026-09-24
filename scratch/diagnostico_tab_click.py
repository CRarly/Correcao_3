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

    # Testar clique na aba Fixado
    print("\n--- TESTANDO CLIQUE NA ABA FIXADO ---")
    info_fixado = page.evaluate("""async () => {
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

        const tabFixado = querySelectorAllDeep('#search-my-pinned-enrollments')[0] || 
                          querySelectorAllDeep('d2l-tab').find(t => (t.getAttribute('title') || '').includes('Fixad'));
        
        if (!tabFixado) return { error: "Tab fixado não encontrado" };

        tabFixado.click();
        await new Promise(r => setTimeout(r, 2000));

        // Pegar cards após clique
        const cards = querySelectorAllDeep('d2l-enrollment-card, d2l-card');
        const cardTexts = cards.map(c => {
            const h = c.shadowRoot ? Array.from(c.shadowRoot.querySelectorAll('a[href*="/d2l/home/"]')) : [];
            const lightA = Array.from(c.querySelectorAll('a[href*="/d2l/home/"]'));
            const allLinks = [...h, ...lightA].map(a => a.href);
            return {
                text: (c.innerText || '').split('\\n')[0].trim(),
                links: allLinks,
                isPinned: c.getAttribute('pinned') || (c.shadowRoot && c.shadowRoot.innerHTML.includes('unpin') || c.shadowRoot && c.shadowRoot.innerHTML.includes('pin')),
                outer: c.outerHTML.substring(0, 150)
            };
        });

        // Procurar botão exibir todas as disciplinas dentro do painel ou página
        const buttons = querySelectorAllDeep('d2l-button-subtle, button, a').filter(b => {
            const t = (b.innerText || b.getAttribute('text') || '').toLowerCase();
            return t.includes('todas') || t.includes('exibir') || t.includes('mais') || t.includes('ver');
        }).map(b => ({
            tag: b.tagName,
            text: b.innerText || b.getAttribute('text'),
            outer: b.outerHTML.substring(0, 150)
        }));

        return {
            tabId: tabFixado.id,
            selected: tabFixado.getAttribute('aria-selected') || tabFixado.hasAttribute('selected'),
            cardsCount: cards.length,
            cardTexts: cardTexts.slice(0, 10),
            buttons: buttons
        };
    }""")
    print("Resultado Fixado:", json.dumps(info_fixado, indent=2, ensure_ascii=False))

    # Testar clique na aba 2026/1
    print("\n--- TESTANDO CLIQUE NA ABA 2026/1 ---")
    info_2026_1 = page.evaluate("""async () => {
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

        const tab = querySelectorAllDeep('d2l-tab').find(t => (t.getAttribute('title') || '').trim() === '2026/1');
        if (!tab) return { error: "Tab 2026/1 não encontrado" };

        tab.click();
        await new Promise(r => setTimeout(r, 2000));

        const cards = querySelectorAllDeep('d2l-enrollment-card, d2l-card');
        const cardTexts = cards.map(c => {
            const h = c.shadowRoot ? Array.from(c.shadowRoot.querySelectorAll('a[href*="/d2l/home/"]')) : [];
            const lightA = Array.from(c.querySelectorAll('a[href*="/d2l/home/"]'));
            const allLinks = [...h, ...lightA].map(a => a.href);
            return {
                text: (c.innerText || '').split('\\n')[0].trim(),
                links: allLinks
            };
        });

        const buttons = querySelectorAllDeep('d2l-button-subtle, button, a').filter(b => {
            const t = (b.innerText || b.getAttribute('text') || '').toLowerCase();
            return t.includes('todas') || t.includes('exibir') || t.includes('mais') || t.includes('ver');
        }).map(b => ({
            tag: b.tagName,
            text: b.innerText || b.getAttribute('text'),
            outer: b.outerHTML.substring(0, 150)
        }));

        return {
            tabId: tab.id,
            selected: tab.getAttribute('aria-selected') || tab.hasAttribute('selected'),
            cardsCount: cards.length,
            cardTexts: cardTexts.slice(0, 10),
            buttons: buttons
        };
    }""")
    print("Resultado 2026/1:", json.dumps(info_2026_1, indent=2, ensure_ascii=False))

    browser.close()
