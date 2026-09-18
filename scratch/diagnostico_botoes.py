import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155388"
url_ativ = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sOHlNREF3WHpFMk9UZzVPQS4xNTUzODg?ou=155388&iteratorRange=all&cft=qe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()
    print(f"Navegando para: {url_ativ}")
    page.goto(url_ativ, wait_until="domcontentloaded", timeout=30000)
    time.sleep(6)

    # Inspecionar todos os botões e d2l-button em toda a página e shadow roots
    botoes = page.evaluate(r"""() => {
        function getAllElements(root) {
            let elements = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                elements.push(el);
                if (el.shadowRoot) elements = elements.concat(getAllElements(el.shadowRoot));
            }
            return elements;
        }
        const all = getAllElements(document.body);
        const btns = [];
        for (let el of all) {
            const tag = el.tagName.toLowerCase();
            if (tag === 'button' || tag.startsWith('d2l-button')) {
                const txt = (el.innerText || el.textContent || '').trim();
                const aria = (el.getAttribute('aria-label') || '').trim();
                const id = el.id || '';
                const cls = el.className || '';
                const primary = el.hasAttribute('primary');
                const textAttr = el.getAttribute('text') || '';
                if (txt || aria || textAttr || id) {
                    btns.push({
                        tag,
                        id,
                        txt: txt.slice(0, 50),
                        aria: aria.slice(0, 50),
                        textAttr,
                        cls: typeof cls === 'string' ? cls.slice(0, 40) : '',
                        primary,
                        disabled: el.disabled || el.hasAttribute('disabled')
                    });
                }
            }
        }
        return btns;
    }""")

    print(f"\nBotões encontrados ({len(botoes)}):")
    for b in botoes:
        if any(k in (b['txt'] + b['aria'] + b['textAttr'] + b['id']).lower() for k in ['salvar', 'save', 'rascunho', 'draft', 'publicar', 'publish']):
            print("  ==> ", b)
        else:
            # Imprimir também outros botões do rodapé
            if any(k in (b['txt'] + b['aria'] + b['textAttr'] + b['id']).lower() for k in ['footer', 'avaliar', 'nota', 'feedback']):
                print("  [footer/outro] ", b)

    # Inspecionar campo de nota
    inputs_nota = page.evaluate(r"""() => {
        function getAllElements(root) {
            let elements = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                elements.push(el);
                if (el.shadowRoot) elements = elements.concat(getAllElements(el.shadowRoot));
            }
            return elements;
        }
        const all = getAllElements(document.body);
        const inputs = [];
        for (let el of all) {
            const tag = el.tagName.toLowerCase();
            if (tag === 'input' || tag.includes('input-number')) {
                const val = el.value !== undefined ? el.value : '';
                const aria = el.getAttribute('aria-label') || '';
                const id = el.id || '';
                inputs.push({ tag, id, aria, val, disabled: el.disabled });
            }
        }
        return inputs;
    }""")
    print(f"\nInputs de nota encontrados ({len(inputs_nota)}):")
    for inp in inputs_nota:
        print("  Input:", inp)

    browser.close()
