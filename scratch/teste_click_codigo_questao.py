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

    # 2. Obter pontos por pergunta
    pontos = page.evaluate(r"""() => {
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
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            const id = (el.id || '').toLowerCase();
            if (aria.includes('pontos por pergunta') || id.includes('points-per-question') || id.includes('points')) {
                return el.value || el.getAttribute('value');
            }
        }
        // Tentar pegar do input próximo ao label
        for (let el of all) {
            const txt = (el.innerText || '').toLowerCase();
            if (txt === 'pontos por pergunta *' || txt.includes('pontos por pergunta')) {
                const parent = el.parentElement || el;
                const inp = parent.querySelector('input, d2l-input-number');
                if (inp) return inp.value || inp.getAttribute('value');
            }
        }
        return '2';
    }""")
    print(f"Pontos por pergunta detectado: {pontos}")

    # 3. Clicar no código da questão (ex: EAD_ES_2026_3_PROV_DIS)
    print("Clicando no código da questão...")
    clique_codigo = page.evaluate(r"""() => {
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
            // Código da questão: geralmente tem formato alfanumérico com underscores, sem espaços
            if (/^[A-Z0-9_-]{8,35}$/i.test(txt)) {
                // Verificar se está visível
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    el.scrollIntoView();
                    el.click();
                    return { clicked: true, code: txt, tag: el.tagName };
                }
            }
        }
        return { clicked: false };
    }""")
    print("Resultado clique no código da questão:", clique_codigo)
    time.sleep(5)

    page.screenshot(path=str(BASE_DIR / "quiz_question_authoring_opened.png"), full_page=True)

    # 4. Inspecionar o editor da questão aberta para extrair o enunciado completo
    enunciado_info = page.evaluate(r"""() => {
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

        // 1. Procurar d2l-htmleditor
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'd2l-htmleditor') {
                const val = el.html || el.innerText || '';
                if (val.length > 20) return { source: 'd2l-htmleditor', text: val };
            }
        }

        // 2. Procurar d2l-html-block
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'd2l-html-block') {
                const val = el.html || el.innerHTML || el.innerText || '';
                if (val.length > 50 && !val.includes('Sua sessão')) return { source: 'd2l-html-block', text: val };
            }
        }

        // 3. Procurar textarea com texto da pergunta
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'textarea') {
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                if (aria.includes('pergunta') || aria.includes('question') || aria.includes('texto')) {
                    return { source: 'textarea', text: el.value };
                }
            }
        }

        // 4. Buscar elemento com maior texto no diálogo superior
        let maior = '';
        for (let el of all) {
            const tag = el.tagName.toLowerCase();
            if (['script', 'style', 'noscript'].includes(tag)) continue;
            const txt = (el.innerText || '').trim();
            if (txt.includes('D2L.LP') || txt.includes('Salvar') || txt.includes('Cancelar')) continue;
            if (txt.length > 80 && txt.length > maior.length) {
                maior = txt;
            }
        }
        return { source: 'largest-text', text: maior };
    }""")

    print("\nInformações do Enunciado:")
    print(f"Fonte: {enunciado_info['source']} | Comprimento: {len(enunciado_info['text'])}")
    print("Prévia:")
    print(enunciado_info['text'][:500])

    browser.close()
