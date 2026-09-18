import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
url_ativ = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sOHlNREF3WHpFMk9UZzVPQS4xNTUzODg?ou=155388&iteratorRange=all&cft=qe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    reqs = []
    page.on("request", lambda r: reqs.append(f"{r.method} {r.url}"))

    page.goto(url_ativ, wait_until="domcontentloaded", timeout=30000)
    time.sleep(6)

    # 1. Testar seletores do Playwright
    for sel in [
        "d2l-button#consistent-evaluation-footer-save-draft",
        "#consistent-evaluation-footer-save-draft",
        "d2l-button:has-text('Salvar Rascunho')",
        "button:has-text('Salvar Rascunho')",
        "[text*='Salvar Rascunho']"
    ]:
        loc = page.locator(sel)
        print(f"Locator '{sel}': count={loc.count()}, visible={loc.first.is_visible() if loc.count() > 0 else False}")

    # 2. Localizar o elemento exato no Shadow DOM e seu caminho hierárquico
    hierarquia = page.evaluate(r"""() => {
        function findEl(root, id) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                if (el.id === id) return el;
                if (el.shadowRoot) {
                    const found = findEl(el.shadowRoot, id);
                    if (found) return found;
                }
            }
            return null;
        }

        const el = findEl(document.body, 'consistent-evaluation-footer-save-draft');
        if (!el) return { found: false };

        // Subir árvore de pais (incluindo host de shadow DOM)
        const path = [];
        let curr = el;
        while (curr) {
            let desc = (curr.tagName ? curr.tagName.toLowerCase() : 'shadow') + (curr.id ? '#' + curr.id : '') + (curr.className ? '.' + curr.className : '');
            path.push(desc);
            if (curr.parentNode) {
                curr = curr.parentNode;
            } else if (curr.host) {
                curr = curr.host;
            } else {
                break;
            }
        }
        
        // Obter inner button dentro do d2l-button
        const innerBtn = el.shadowRoot ? el.shadowRoot.querySelector('button') : null;
        return {
            found: true,
            path: path.reverse(),
            hasShadow: !!el.shadowRoot,
            innerBtnTag: innerBtn ? innerBtn.tagName : null,
            innerBtnText: innerBtn ? innerBtn.innerText : null
        };
    }""")
    print("\nHierarquia do elemento:", hierarquia)

    # 3. Agora vamos alterar a nota e o feedback primeiro, e depois clicar em Salvar Rascunho
    print("\nPreenchendo nota e feedback...")
    fill_res = page.evaluate(r"""() => {
        function findElementDeep(root, matchFn) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                if (matchFn(el)) return el;
                if (el.shadowRoot) {
                    const found = findElementDeep(el.shadowRoot, matchFn);
                    if (found) return found;
                }
            }
            return null;
        }

        // 1. Achar d2l-input-number e seu input interno
        const inputNum = findElementDeep(document.body, el => el.tagName.toLowerCase() === 'd2l-input-number');
        let notaPreenchida = false;
        if (inputNum) {
            inputNum.value = 1.25;
            inputNum.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
            inputNum.dispatchEvent(new CustomEvent('input', { bubbles: true, composed: true }));
            
            // Input interno
            const innerInput = inputNum.shadowRoot ? inputNum.shadowRoot.querySelector('input') : null;
            if (innerInput) {
                innerInput.value = "1,25";
                innerInput.dispatchEvent(new Event('input', { bubbles: true }));
                innerInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
            notaPreenchida = true;
        }

        // 2. Feedback
        const htmleditor = findElementDeep(document.body, el => el.tagName.toLowerCase() === 'd2l-htmleditor');
        let fbPreenchido = false;
        if (htmleditor) {
            try {
                htmleditor.html = "<p>Olá, {FirstName}!</p><p>Excelente entrega com diagramas completos.</p>";
                htmleditor.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
                htmleditor.dispatchEvent(new CustomEvent('input', { bubbles: true, composed: true }));
                fbPreenchido = true;
            } catch(e) {}
        }

        return { notaPreenchida, fbPreenchido };
    }""")
    print("Preenchimento resultado:", fill_res)
    time.sleep(1.5)

    reqs.clear()
    print("\nClicando em Salvar Rascunho...")
    click_exec = page.evaluate(r"""() => {
        function findEl(root, id) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                if (el.id === id) return el;
                if (el.shadowRoot) {
                    const found = findEl(el.shadowRoot, id);
                    if (found) return found;
                }
            }
            return null;
        }

        const el = findEl(document.body, 'consistent-evaluation-footer-save-draft');
        if (!el) return { success: false, reason: 'not found' };

        const innerBtn = el.shadowRoot ? el.shadowRoot.querySelector('button') : null;
        if (innerBtn) {
            innerBtn.click();
            return { success: true, method: 'innerBtn.click()', disabled: innerBtn.disabled };
        } else {
            el.click();
            return { success: true, method: 'el.click()', disabled: el.disabled };
        }
    }""")
    print("Resultado clique:", click_exec)
    time.sleep(4)

    print(f"\nTotal requisições de rede após clique: {len(reqs)}")
    for r in reqs:
        if any(k in r.lower() for k in ["save", "draft", "evaluation", "grade", "feedback", "activity", "item", "d2l"]):
            print("  ->", r)

    browser.close()
