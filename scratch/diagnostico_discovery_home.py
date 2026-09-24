import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import time
from playwright.sync_api import sync_playwright
from config import BASE_AVA_URL

auth_file = "auth_state_04084531.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(storage_state=auth_file, viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.goto(f"{BASE_AVA_URL}/d2l/home", wait_until="domcontentloaded", timeout=60000)
    print("Page URL after goto:", page.url)
    print("Page Title:", page.title())
    time.sleep(5)
    print("Page URL after sleep:", page.url)
    print("Page Title after sleep:", page.title())
    print("Total frames:", len(page.frames))
    for idx, f in enumerate(page.frames):
        print(f"Frame {idx}: name='{f.name}', url='{f.url}'")
    
    # Inspecionar detalhes de d2l-tabs e d2l-tab com querySelectorAllDeep
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

        function getAttributes(el) {
            const attrs = {};
            for (let i = 0; i < el.attributes.length; i++) {
                attrs[el.attributes[i].name] = el.attributes[i].value;
            }
            return attrs;
        }

        const tabs = querySelectorAllDeep('d2l-tab');
        const tabData = tabs.map(t => {
            const shadowText = t.shadowRoot ? t.shadowRoot.textContent.trim() : '';
            return {
                id: t.id,
                textAttr: t.getAttribute('text'),
                labelAttr: t.getAttribute('label'),
                ariaLabel: t.getAttribute('aria-label'),
                innerText: t.innerText.trim(),
                shadowText: shadowText,
                selected: t.hasAttribute('selected') || t.getAttribute('aria-selected') === 'true',
                attributes: getAttributes(t),
                outerHTML: t.outerHTML.substring(0, 200)
            };
        });

        // Inspecionar d2l-tabs (o container de abas)
        const d2lTabsList = querySelectorAllDeep('d2l-tabs');
        const d2lTabsInfo = d2lTabsList.map(d2lTabs => {
            const shadowButtons = d2lTabs.shadowRoot ? Array.from(d2lTabs.shadowRoot.querySelectorAll('button, d2l-button-icon, [role="button"]')).map(b => ({
                tag: b.tagName,
                classes: b.className,
                ariaLabel: b.getAttribute('aria-label'),
                icon: b.getAttribute('icon'),
                text: b.innerText || b.getAttribute('text'),
                disabled: b.disabled || b.hasAttribute('disabled'),
                outerHTML: b.outerHTML.substring(0, 150)
            })) : [];

            return {
                id: d2lTabs.id,
                attributes: getAttributes(d2lTabs),
                hasShadowRoot: !!d2lTabs.shadowRoot,
                shadowButtons: shadowButtons
            };
        });

        // Inspecionar botões "Exibir todas as disciplinas" ou similares em deep
        const subtleButtons = querySelectorAllDeep('d2l-button-subtle, button, a').filter(b => {
            const txt = (b.innerText || b.getAttribute('text') || b.getAttribute('aria-label') || '').toLowerCase();
            return txt.includes('exibir') || txt.includes('disciplinas') || txt.includes('todas') || txt.includes('carregar') || txt.includes('ver');
        }).map(b => ({
            tag: b.tagName,
            text: b.innerText || b.getAttribute('text'),
            ariaLabel: b.getAttribute('aria-label'),
            attributes: getAttributes(b),
            outerHTML: b.outerHTML.substring(0, 200)
        }));

        // Cards visíveis atualmente
        const cards = querySelectorAllDeep('d2l-enrollment-card, d2l-card');
        const cardsInfo = cards.map(c => ({
            tag: c.tagName,
            text: (c.innerText || '').substring(0, 80),
            attributes: getAttributes(c)
        }));

        return {
            tabData,
            d2lTabsInfo,
            subtleButtons,
            cardsCount: cards.length,
            cardsInfo: cardsInfo.slice(0, 10)
        };
    }""")

    import json
    with open("scratch/tabs_detailed.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print("Total d2l-tab encontrados:", len(res.get("tabData", [])))
    for t in res.get("tabData", []):
        print(f"Tab id={t['id']} | textAttr='{t['textAttr']}' | labelAttr='{t['labelAttr']}' | innerText='{t['innerText']}' | shadowText='{t['shadowText']}' | attrs={t['attributes']}")

    print("\nd2l-tabs container info:")
    for c in res.get("d2lTabsInfo", []):
        print("d2l-tabs id:", c.get("id"), "buttons:", c.get("shadowButtons"))

    print("\nSubtle buttons count:", len(res.get("subtleButtons", [])))
    for sb in res.get("subtleButtons", []):
        print(f"Subtle button: tag={sb['tag']}, text='{sb['text']}', ariaLabel='{sb['ariaLabel']}'")

    print("\nCards count:", res.get("cardsCount", 0))

    browser.close()
