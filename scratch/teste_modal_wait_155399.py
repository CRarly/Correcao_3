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

    page.goto(url_edit, wait_until="domcontentloaded", timeout=35000)
    time.sleep(4)

    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)

    print("Clicando no pool da Questão dissertativa...")
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

    # Aguardar até que o modal carregue os campos internos (até 15s)
    print("Aguardando carregamento interno do modal...")
    loaded = False
    for i in range(15):
        time.sleep(1)
        res = page.evaluate(r"""() => {
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
                if (txt.includes('EAD_') || txt.includes('Pontos por pergunta') || txt.includes('Procurar na biblioteca')) {
                    return true;
                }
            }
            return false;
        }""")
        if res:
            print(f"Modal carregado após {i+1} segundos!")
            loaded = True
            break

    page.screenshot(path=str(BASE_DIR / "quiz_155399_modal_loaded.png"), full_page=True)

    # Extrair os dados do modal
    dados = page.evaluate(r"""() => {
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

        let pontos = '';
        const inputs = all.filter(el => ['input', 'd2l-input-number'].includes(el.tagName.toLowerCase()));
        for (let inp of inputs) {
            const aria = (inp.getAttribute('aria-label') || '').toLowerCase();
            const id = (inp.id || '').toLowerCase();
            if (aria.includes('pontos') || id.includes('point')) {
                pontos = inp.value || inp.getAttribute('value');
            }
        }

        const codigos = [];
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt.startsWith('EAD_') && (txt.includes('DIS') || txt.includes('PROV'))) {
                codigos.push({
                    tag: el.tagName,
                    txt: txt,
                    id: el.id,
                    className: el.className
                });
            }
        }

        return { pontos, codigos };
    }""")

    print("\nResultado da extração:")
    print("Pontos:", dados['pontos'])
    print("Códigos:", dados['codigos'])

    # Clicar no código da questão (ex: EAD_SdInO_2026_3_PROV_QDIS)
    if dados['codigos']:
        codigo_alvo = dados['codigos'][0]['txt']
        print(f"\nClicando no código da questão: {codigo_alvo}...")
        page.evaluate(r"""(alvo) => {
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
                if (txt === alvo) {
                    const target = el.closest('button') || el.closest('a') || el;
                    target.scrollIntoView();
                    target.click();
                    return true;
                }
            }
            return false;
        }""", codigo_alvo)

        time.sleep(5)
        page.screenshot(path=str(BASE_DIR / "quiz_155399_question_opened.png"), full_page=True)

        # Extrair o enunciado
        enunciado = page.evaluate(r"""() => {
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
            
            // Procurar em d2l-htmleditor
            for (let el of all) {
                if (el.tagName.toLowerCase() === 'd2l-htmleditor') {
                    const html = el.html || el.innerText || '';
                    if (html.length > 30) return html;
                }
            }

            // Procurar em textarea
            for (let el of all) {
                if (el.tagName.toLowerCase() === 'textarea') {
                    const val = el.value || '';
                    if (val.length > 30 && !val.includes('VICTOR')) return val;
                }
            }

            // Procurar em d2l-html-block
            for (let el of all) {
                if (el.tagName.toLowerCase() === 'd2l-html-block') {
                    const val = el.html || el.innerText || '';
                    if (val.length > 50 && !val.includes('VICTOR') && !val.includes('Sua sessão')) return val;
                }
            }

            return '';
        }""")

        print(f"\nENUNCIADO OBTIDO ({len(enunciado)} chars):")
        print(enunciado)

    browser.close()
