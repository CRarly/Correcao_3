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

    # Clicar exatamente no botão que contém 'Questão dissertativa' e 'editar conjunto de perguntas'
    print("Localizando e clicando no botão do Grupo 'Questão dissertativa'...")
    clicado = page.evaluate(r"""() => {
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
                    return { ok: true, txt: txt.slice(0, 100) };
                }
            }
        }
        return { ok: false };
    }""")
    print("Resultado do clique no pool correto:", clicado)
    time.sleep(5)

    print(f"URL pós clique: {page.url} | Frames: {len(page.frames)}")
    page.screenshot(path=str(BASE_DIR / "quiz_pool_dissertativa_opened.png"), full_page=True)

    # Inspecionar todos os textos, inputs e links abertos no modal ou na página
    info = page.evaluate(r"""() => {
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

        // Pontos por pergunta
        let pontos = '';
        for (let el of all) {
            if (['input', 'd2l-input-number'].includes(el.tagName.toLowerCase())) {
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                const id = (el.id || '').toLowerCase();
                if (aria.includes('pontos por pergunta') || aria.includes('pontos') || id.includes('point')) {
                    pontos = el.value || el.getAttribute('value');
                }
            }
        }

        // Links de questões / códigos
        const questoes = [];
        for (let el of all) {
            const tag = el.tagName.toLowerCase();
            if (['a', 'button', 'span', 'div'].includes(tag)) {
                const txt = (el.innerText || el.textContent || '').trim();
                // Procurar links com cara de código de questão ou título de questão
                if (txt.length >= 3 && txt.length <= 60) {
                    const href = el.getAttribute('href') || '';
                    if (href.includes('question') || href.includes('authoring') || href.includes('quizzing') || tag === 'a') {
                        questoes.push({ tag, txt, href, aria: el.getAttribute('aria-label') });
                    }
                }
            }
        }

        // Todos os blocos com texto pedagógico visível
        const textos = [];
        for (let el of all) {
            if (['p', 'div', 'd2l-html-block', 'span'].includes(el.tagName.toLowerCase())) {
                const txt = (el.innerText || el.textContent || '').trim();
                if (txt.length > 50 && !txt.includes('D2L.LP') && !txt.includes('Salvar e Fechar') && !txt.includes('Orientações gerais')) {
                    if (!textos.some(t => t.includes(txt) || txt.includes(t))) {
                        textos.push(txt);
                    }
                }
            }
        }

        return { pontos, questoes: questoes.slice(0, 20), textos: textos.slice(0, 10) };
    }""")

    print("\nDados obtidos no Pool:")
    print("Pontos:", info['pontos'])
    print("Questões:", info['questoes'])
    print("\nTextos encontrados:")
    for t in info['textos']:
        print(f"--- ({len(t)} chars) ---")
        print(t[:200])

    browser.close()
