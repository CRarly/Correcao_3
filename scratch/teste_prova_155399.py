import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155399"
url_quizzes = f"https://ava.catolica.edu.br/d2l/lms/quizzing/admin/quizzes_manage.d2l?ou={ou}"
url_qe = f"https://ava.catolica.edu.br/d2l/lms/quickeval/quickeval.d2l?ou={ou}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    print(f"=== TESTE PROVA PRESENCIAL OU {ou} ===")
    print(f"1. Acessando Gerenciar Questionários: {url_quizzes}")
    page.goto(url_quizzes, wait_until="domcontentloaded", timeout=35000)
    time.sleep(4)

    # Identificar link da Avaliação: Prova presencial
    link_prova = page.evaluate(r"""() => {
        const links = Array.from(document.querySelectorAll('a[href*="quiz_newedit_properties"], a[href*="modify/quiz"]'));
        for (let a of links) {
            const txt = (a.innerText || '').toLowerCase();
            if (txt.includes('prova presencial') || (txt.includes('prova') && !txt.includes('recupera'))) {
                return { title: a.innerText.trim(), href: a.href };
            }
        }
        return null;
    }""")
    print("Prova localizada:", link_prova)

    if link_prova:
        print(f"\n2. Acessando página de edição da prova: {link_prova['href']}")
        page.goto(link_prova['href'], wait_until="domcontentloaded", timeout=35000)
        time.sleep(6)

        # Rolar a página e listar todas as seções / pools de questões
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
            const botoes = [];
            for (let el of all) {
                if (el.tagName.toLowerCase() === 'button') {
                    const txt = (el.innerText || el.textContent || '').trim();
                    if (txt.includes('QME') || txt.includes('dissertat') || txt.includes('discursiv') || txt.includes('Grupo de Questões')) {
                        botoes.push({ id: el.id, txt: txt.replace(/\s+/g, ' ') });
                    }
                }
            }
            return botoes;
        }""")
        print("Botões de grupos/questões na edição:")
        for b in pools:
            print(" -", b)

    # 3. Agora acessar Quick Eval para ver a fila de correção da Prova Presencial em 155399
    print(f"\n3. Acessando Quick Eval: {url_qe}")
    page.goto(url_qe, wait_until="domcontentloaded", timeout=35000)
    time.sleep(4)

    # Clicar em Atividades
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
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt === 'Atividades' && ['d2l-tab', 'button', 'a'].includes(el.tagName.toLowerCase())) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    time.sleep(3)

    # Listar atividades no Quick Eval
    atividades_qe = page.evaluate(r"""() => {
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
        const links = all.filter(el => el.tagName.toLowerCase() === 'a' && (el.getAttribute('href') || '').includes('evaluation/activity'));
        return links.map(a => ({
            txt: (a.innerText || '').trim(),
            href: a.getAttribute('href')
        }));
    }""")
    print("\nAtividades encontradas no Quick Eval de 155399:")
    for a in atividades_qe:
        print(" -", a)

    browser.close()

