import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
url_edit = "https://ava.catolica.edu.br/d2l/lms/quizzing/admin/modify/quiz_newedit_properties.d2l?qi=254965&ou=155388"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    print("Acessando pagina de edicao da prova...")
    page.goto(url_edit, wait_until="domcontentloaded", timeout=35000)
    time.sleep(6)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)

    # Clicar no elemento de questao dissertativa
    print("Clicando no container da Questão Dissertativa...")
    click_res = page.evaluate(r"""() => {
        function findElements(root) {
            let list = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                list.push(el);
                if (el.shadowRoot) list = list.concat(findElements(el.shadowRoot));
            }
            return list;
        }
        const all = findElements(document.body);
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
            if (txt.includes('questão dissertativa') || txt.includes('questao dissertativa') || txt.includes('resposta dissertativa')) {
                const btn = el.querySelector ? el.querySelector('button, a, d2l-button') : null;
                const target = btn || (el.closest('button') || el.closest('a') || el);
                if (typeof target.click === 'function') {
                    target.scrollIntoView();
                    target.click();
                    return { clicked: true, tag: target.tagName, txt: (el.innerText || '').slice(0, 100) };
                }
            }
        }
        return { clicked: false };
    }""")
    print("Click resultado:", click_res)
    time.sleep(6)

    # Inspecionar dentro do d2l-dialog-fullscreen e em toda a árvore (com Shadow DOM)
    dados = page.evaluate(r"""() => {
        function findElements(root) {
            let list = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                list.push(el);
                if (el.shadowRoot) list = list.concat(findElements(el.shadowRoot));
            }
            return list;
        }
        const all = findElements(document.body);

        // Listar diálogos
        const dialogs = all.filter(el => el.tagName.toLowerCase().includes('dialog'));
        const dialogInfo = dialogs.map(d => ({
            tag: d.tagName,
            opened: d.hasAttribute('opened'),
            title: d.getAttribute('title') || d.getAttribute('title-text')
        }));

        // Procurar inputs de pontos
        const inputs = all.filter(el => ['input', 'd2l-input-number'].includes(el.tagName.toLowerCase()));
        const pontuacoes = [];
        for (let inp of inputs) {
            const aria = (inp.getAttribute('aria-label') || '').toLowerCase();
            const id = (inp.id || '').toLowerCase();
            const val = inp.value;
            if (aria.includes('ponto') || aria.includes('pergunta') || id.includes('point') || id.includes('score')) {
                pontuacoes.push({ tag: inp.tagName, aria, id, val });
            }
        }

        // Procurar links ou códigos de questões
        const linksQuestoes = [];
        for (let el of all) {
            const tag = el.tagName.toLowerCase();
            if (['a', 'button', 'd2l-link'].includes(tag)) {
                const txt = (el.innerText || '').trim();
                const aria = (el.getAttribute('aria-label') || '').trim();
                // Questões no Brightspace costumam ter códigos como Q1, 1, 8, ou códigos alfanuméricos
                if (txt.length >= 2 && txt.length <= 50) {
                    linksQuestoes.push({ tag, txt, aria, href: el.getAttribute('href') });
                }
            }
        }

        return {
            totalElements: all.length,
            dialogInfo,
            pontuacoes,
            linksQuestoes: linksQuestoes.slice(0, 30)
        };
    }""")

    print("\nDados da árvore:")
    print("Diálogos:", dados['dialogInfo'])
    print("Pontuações:", dados['pontuacoes'])
    print(f"Total links/botões encontrados: {len(dados['linksQuestoes'])}")
    for l in dados['linksQuestoes'][:20]:
        print("  -", l)

    # Tirar screenshot para ver exatamente a tela aberta
    page.screenshot(path=str(BASE_DIR / "quiz_dialog_screen.png"), full_page=True)
    print("Screenshot salva: quiz_dialog_screen.png")

    browser.close()
