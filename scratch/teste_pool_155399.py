import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155399"
qi = "254983"
url_edit = f"https://ava.catolica.edu.br/d2l/lms/quizzing/admin/modify/quiz_newedit_properties.d2l?qi={qi}&ou={ou}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 1000})
    page = context.new_page()

    print(f"1. Acessando edicao da Prova Presencial: {url_edit}")
    page.goto(url_edit, wait_until="domcontentloaded", timeout=35000)
    time.sleep(5)

    # Inspecionar botoes de questoes na pagina principal de edicao
    botoes_questoes = page.evaluate(r"""() => {
        function getAll(root) {
            let res = [];
            const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while(w.nextNode()) {
                const el = w.currentNode;
                res.push(el);
                if (el.shadowRoot) res = res.concat(getAll(el.shadowRoot));
            }
            return res;
        }
        const all = getAll(document.body);
        const list = [];
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'button') {
                const txt = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (txt.includes('Questão dissertativa') || txt.includes('QME') || txt.includes('Grupo de Questões')) {
                    list.push({ id: el.id, txt });
                }
            }
        }
        return list;
    }""")
    print("Grupos encontrados na Prova Presencial:")
    for b in botoes_questoes:
        print(" -", b)

    # 2. Clicar no botão da Questão Dissertativa
    print("\n2. Clicando no grupo Questão dissertativa...")
    page.evaluate(r"""() => {
        function getAll(root) {
            let res = [];
            const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while(w.nextNode()) {
                const el = w.currentNode;
                res.push(el);
                if (el.shadowRoot) res = res.concat(getAll(el.shadowRoot));
            }
            return res;
        }
        const all = getAll(document.body);
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'button') {
                const txt = (el.innerText || el.textContent || '').trim();
                if (txt.includes('Questão dissertativa') && (txt.includes('editar conjunto') || txt.includes('Grupo de Questões') || txt.includes('valendo'))) {
                    el.scrollIntoView();
                    el.click();
                    return true;
                }
            }
        }
        return false;
    }""")
    time.sleep(4)

    page.screenshot(path=str(BASE_DIR / "quiz_155399_pool_opened.png"), full_page=True)
    print("Screenshot salva: quiz_155399_pool_opened.png")

    # Inspecionar elementos dentro do modal de Editar Conjunto de Perguntas
    modal_elements = page.evaluate(r"""() => {
        function getAll(root) {
            let res = [];
            const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while(w.nextNode()) {
                const el = w.currentNode;
                res.push(el);
                if (el.shadowRoot) res = res.concat(getAll(el.shadowRoot));
            }
            return res;
        }
        const all = getAll(document.body);
        
        // Elementos que contêm EAD_SdInO ou código similar
        const codigos = [];
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt.includes('EAD_') || txt.includes('PROV_') || txt.includes('QDIS')) {
                codigos.push({
                    tag: el.tagName,
                    txt: txt.slice(0, 80),
                    className: el.className,
                    id: el.id
                });
            }
        }

        // Inputs e labels
        const inputs = [];
        for (let el of all) {
            if (['input', 'd2l-input-number'].includes(el.tagName.toLowerCase())) {
                inputs.push({
                    tag: el.tagName,
                    aria: el.getAttribute('aria-label'),
                    id: el.id,
                    val: el.value || el.getAttribute('value')
                });
            }
        }

        return { codigos, inputs };
    }""")

    print("\nElementos do modal:")
    print("Códigos:", modal_elements['codigos'])
    print("Inputs:", modal_elements['inputs'])

    browser.close()
