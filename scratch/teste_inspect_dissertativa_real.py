import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
url_edit = "https://ava.catolica.edu.br/d2l/lms/quizzing/admin/modify/quiz_newedit_properties.d2l?qi=254965&ou=155388"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 1000})
    page = context.new_page()

    print("Acessando pagina de edicao da prova...")
    page.goto(url_edit, wait_until="domcontentloaded", timeout=35000)
    time.sleep(6)

    # 1. Clicar no botão do Grupo Questão Dissertativa
    print("Clicando no grupo Questão dissertativa...")
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
                if (txt.includes('Questão dissertativa') && (txt.includes('editar conjunto') || txt.includes('Grupo de Questões'))) {
                    el.scrollIntoView();
                    el.click();
                    return;
                }
            }
        }
    }""")
    time.sleep(4)

    # Inspecionar especificamente o modal aberto
    modal_info = page.evaluate(r"""() => {
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
        
        // Elemento com código EAD_
        const eadElements = [];
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt.includes('EAD_') || txt.includes('_DIS') || txt.includes('PROV_DIS')) {
                eadElements.push({
                    tag: el.tagName,
                    txt: txt.slice(0, 50),
                    className: el.className,
                    id: el.id,
                    clickable: typeof el.click === 'function'
                });
            }
        }

        // Inputs dentro do modal
        const inputs = [];
        for (let el of all) {
            if (['input', 'd2l-input-number'].includes(el.tagName.toLowerCase())) {
                inputs.push({
                    tag: el.tagName,
                    aria: el.getAttribute('aria-label'),
                    id: el.id,
                    name: el.getAttribute('name'),
                    val: el.value || el.getAttribute('value')
                });
            }
        }

        return { eadElements, inputs };
    }""")

    print("\nModal Info:")
    print("Inputs:", modal_info['inputs'])
    print("EAD Elements:", modal_info['eadElements'])

    # Agora clicar no elemento específico que tem o código da questão EAD_
    print("\nClicando no elemento com código da questão...")
    clique = page.evaluate(r"""() => {
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
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt === 'EAD_ES_2026_3_PROV_DIS' || (txt.startsWith('EAD_') && txt.includes('_DIS'))) {
                const target = el.closest('button') || el.closest('a') || el;
                target.scrollIntoView();
                target.click();
                return { clicked: true, tag: target.tagName, txt: txt };
            }
        }
        return { clicked: false };
    }""")
    print("Clique:", clique)
    time.sleep(5)

    page.screenshot(path=str(BASE_DIR / "quiz_question_editor_screen.png"), full_page=True)

    # Inspecionar o editor da questão aberta
    editor_info = page.evaluate(r"""() => {
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

        // Editores HTML
        const editores = [];
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'd2l-htmleditor') {
                const html = el.html || el.innerText || '';
                if (html.length > 20) editores.push({ tag: 'd2l-htmleditor', len: html.length, preview: html.slice(0, 300) });
            }
            if (el.tagName.toLowerCase() === 'd2l-html-block') {
                const html = el.html || el.innerHTML || el.innerText || '';
                if (html.length > 30 && !html.includes('Sua sessão')) {
                    editores.push({ tag: 'd2l-html-block', len: html.length, preview: html.slice(0, 300) });
                }
            }
        }

        // Inputs e Textareas
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'textarea') {
                const v = el.value || '';
                if (v.length > 20) editores.push({ tag: 'textarea', len: v.length, preview: v.slice(0, 300) });
            }
        }

        return editores;
    }""")

    print("\nEditores encontrados na questão:")
    for ed in editor_info:
        print(f"[{ed['tag']}] len={ed['len']}: {ed['preview']}")

    browser.close()
