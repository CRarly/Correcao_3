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
    time.sleep(4)

    # Rolar ate o fim para carregar as questoes
    print("Rolando até o final da página...")
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

    # Localizar os botoes de pool
    pools = page.evaluate(r"""() => {
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
    print("Pools carregados:")
    for p_info in pools:
        print(" -", p_info)

    # Clicar no botao da Questao Dissertativa
    print("\n2. Clicando no pool da Questão dissertativa...")
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
                if (txt.includes('Questão dissertativa') && (txt.includes('editar conjunto') || txt.includes('Grupo de Questões') || txt.includes('valendo'))) {
                    el.scrollIntoView();
                    el.click();
                    return { ok: true, txt: txt.slice(0, 100) };
                }
            }
        }
        return { ok: false };
    }""")
    print("Clique:", clicado)
    time.sleep(5)

    page.screenshot(path=str(BASE_DIR / "quiz_155399_modal.png"), full_page=True)
    print("Screenshot salva: quiz_155399_modal.png")

    # Inspecionar elementos dentro do modal
    dados_modal = page.evaluate(r"""() => {
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

        // Itens de questão dentro do modal
        const itens = [];
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt.includes('EAD_') || txt.includes('_QDIS') || txt.includes('_DIS')) {
                itens.push({
                    tag: el.tagName,
                    txt: txt.slice(0, 100),
                    className: el.className
                });
            }
        }

        return { pontos, itens };
    }""")

    print("\nDados do Modal 155399:")
    print("Pontos:", dados_modal['pontos'])
    print("Itens:", dados_modal['itens'])

    browser.close()
