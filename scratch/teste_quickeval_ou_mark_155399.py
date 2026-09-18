import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155399"
qi = "254983"
url_qe = f"https://ava.catolica.edu.br/d2l/lms/quickeval/quickeval.d2l?ou={ou}"
url_quiz_mark = f"https://ava.catolica.edu.br/d2l/lms/quizzing/admin/mark/quiz_users.d2l?ou={ou}&qi={qi}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 1000})
    page = context.new_page()

    print("=== INSPEÇÃO QUICK EVAL E NOTAS DA PROVA EM 155399 ===")
    
    # 1. Inspecionar Quick Eval
    print(f"\n1. Acessando Quick Eval: {url_qe}")
    page.goto(url_qe, wait_until="domcontentloaded", timeout=35000)
    time.sleep(5)
    page.screenshot(path=str(BASE_DIR / "qe_155399_initial.png"))

    # Clicar na aba Atividades se existir
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
            if (txt === 'Atividades' && ['d2l-tab', 'button', 'a', 'span'].includes(el.tagName.toLowerCase())) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    time.sleep(4)
    page.screenshot(path=str(BASE_DIR / "qe_155399_activities_tab.png"))

    # Inspecionar itens do Quick Eval
    qe_items = page.evaluate(r"""() => {
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
        const links = all.filter(el => el.tagName.toLowerCase() === 'a');
        return links.map(a => ({
            txt: (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim(),
            href: a.href || a.getAttribute('href')
        })).filter(a => a.txt.length > 2 && !a.txt.includes('D2L'));
    }""")
    print(f"Links no Quick Eval: {len(qe_items)}")
    for item in qe_items[:15]:
        print(" -", item)

    # 2. Inspecionar página oficial de notas do Quiz (quiz_users.d2l)
    print(f"\n2. Acessando página de Notas do Questionário: {url_quiz_mark}")
    page.goto(url_quiz_mark, wait_until="domcontentloaded", timeout=35000)
    time.sleep(5)
    page.screenshot(path=str(BASE_DIR / "quiz_users_155399.png"))

    # Inspecionar tentativas dos alunos listados
    tentativas = page.evaluate(r"""() => {
        const rows = Array.from(document.querySelectorAll('tr'));
        const list = [];
        for (let r of rows) {
            const txt = (r.innerText || '').replace(/\s+/g, ' ').trim();
            const links = Array.from(r.querySelectorAll('a'));
            const linkTentativa = links.find(a => (a.innerText || '').toLowerCase().includes('tentativa'));
            if (linkTentativa) {
                list.push({
                    aluno: txt.slice(0, 50),
                    tentativa: linkTentativa.innerText.trim(),
                    href: linkTentativa.href
                });
            }
        }
        return list;
    }""")
    print(f"\nTentativas encontradas em quiz_users: {len(tentativas)}")
    for t in tentativas[:10]:
        print(" -", t)

    # Se encontramos tentativa, abrir a primeira tentativa para ver a página de avaliação!
    if tentativas:
        primeira = tentativas[0]
        print(f"\n3. Acessando avaliação da primeira tentativa: {primeira['aluno']} -> {primeira['href']}")
        page.goto(primeira['href'], wait_until="domcontentloaded", timeout=35000)
        time.sleep(6)
        page.screenshot(path=str(BASE_DIR / "tentativa_eval_page_top.png"))

        # Rolar até a questão discursiva (Questão 8)
        print("Rolando a página até a Questão 8...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        page.screenshot(path=str(BASE_DIR / "tentativa_eval_page_bottom.png"))

        # Inspecionar estrutura da Questão 8, resposta do aluno, campo de feedback e pontuação
        detalhes_q8 = page.evaluate(r"""() => {
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
            
            // Buscar elementos com Pergunta 8 ou Questão 8
            const blocosQ8 = [];
            for (let el of all) {
                const txt = (el.innerText || el.textContent || '').trim();
                if (txt.startsWith('Pergunta 8') || txt.startsWith('Questão 8') || txt.includes('EAD_SdInO_2026_3_PROV_QDIS')) {
                    blocosQ8.push({
                        tag: el.tagName,
                        className: el.className,
                        id: el.id,
                        txt: txt.slice(0, 300)
                    });
                }
            }

            // Inputs de pontuação e feedback
            const inputs = [];
            for (let el of all) {
                if (['input', 'textarea', 'd2l-htmleditor', 'd2l-input-number'].includes(el.tagName.toLowerCase())) {
                    inputs.push({
                        tag: el.tagName,
                        id: el.id,
                        name: el.getAttribute('name'),
                        aria: el.getAttribute('aria-label'),
                        val: el.value || el.getAttribute('value')
                    });
                }
            }

            // Botões de ação (Salvar rascunho, etc)
            const botoes = [];
            for (let el of all) {
                if (el.tagName.toLowerCase() === 'button' || el.tagName.toLowerCase() === 'd2l-button') {
                    const txt = (el.innerText || el.textContent || '').trim();
                    if (txt.includes('Salvar') || txt.includes('Rascunho') || txt.includes('Publicar')) {
                        botoes.push({ tag: el.tagName, id: el.id, txt });
                    }
                }
            }

            return { blocosQ8: blocosQ8.slice(0, 5), inputs: inputs.slice(0, 20), botoes };
        }""")

        print("\nDetalhes da Questão 8 na Avaliação:")
        print("Blocos Q8:", detalhes_q8['blocosQ8'])
        print("Inputs:", detalhes_q8['inputs'])
        print("Botões:", detalhes_q8['botoes'])

    browser.close()
