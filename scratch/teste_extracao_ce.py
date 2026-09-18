import time
from pathlib import Path
from playwright.sync_api import sync_playwright

auth_file = Path("auth_state_04083941.json")
ou = "155399"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(storage_state=str(auth_file), viewport={"width": 1400, "height": 900}).new_page()
    
    url_qe = f"https://ava.catolica.edu.br/d2l/lms/quickeval/quickeval.d2l?ou={ou}"
    print(f"1. Acessando Quick Eval: {url_qe}")
    page.goto(url_qe, wait_until="domcontentloaded", timeout=35000)
    time.sleep(3)

    # Clicar na aba Atividades
    print("2. Selecionando aba Atividades...")
    page.evaluate(r"""() => {
        function findDeep(root, fn) {
            let res = [];
            const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (w.nextNode()) {
                if (fn(w.currentNode)) res.push(w.currentNode);
                if (w.currentNode.shadowRoot) res = res.concat(findDeep(w.currentNode.shadowRoot, fn));
            }
            return res;
        }
        const tabs = findDeep(document.body, el => (el.innerText || '').trim() === 'Atividades');
        if (tabs.length > 0) tabs[0].click();
    }""")
    time.sleep(3)

    # Localizar link da Prova Presencial
    link_prova = page.evaluate(r"""() => {
        function findDeep(root, fn) {
            let res = [];
            const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (w.nextNode()) {
                if (fn(w.currentNode)) res.push(w.currentNode);
                if (w.currentNode.shadowRoot) res = res.concat(findDeep(w.currentNode.shadowRoot, fn));
            }
            return res;
        }
        const links = findDeep(document.body, el => el.tagName.toLowerCase() === 'a' && (el.getAttribute('href') || '').includes('evaluation/activity'));
        for (let a of links) {
            let p = a;
            let full = '';
            for (let s = 0; s < 8; s++) {
                if (!p) break;
                const inners = findDeep(p, el => true);
                for (let inEl of inners) {
                    const t = (inEl.innerText || inEl.textContent || '').trim();
                    if (t) full += ' ' + t;
                }
                p = p.parentElement || (p.getRootNode ? p.getRootNode().host : null);
            }
            if (full.toLowerCase().includes('prova presencial') || (full.toLowerCase().includes('prova') && !full.toLowerCase().includes('substitutiva'))) {
                return a.href || a.getAttribute('href');
            }
        }
        return links.length > 0 ? links[0].href : null;
    }""")
    print("3. Link da Prova Presencial:", link_prova)

    if link_prova:
        url_eval = link_prova.replace("iteratorRange=new", "iteratorRange=all")
        if "iteratorRange=" not in url_eval:
            url_eval += ("&" if "?" in url_eval else "?") + "iteratorRange=all"
        print("4. Acessando tela de avaliação:", url_eval)
        page.goto(url_eval, wait_until="domcontentloaded", timeout=40000)
        time.sleep(6)

        # Rolar painel para carregar as questões
        page.evaluate(r"""() => {
            const all = [];
            const w = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, null, false);
            while (w.nextNode()) {
                all.push(w.currentNode);
                if (w.currentNode.shadowRoot) {
                    const w2 = document.createTreeWalker(w.currentNode.shadowRoot, NodeFilter.SHOW_ELEMENT, null, false);
                    while (w2.nextNode()) all.push(w2.currentNode);
                }
            }
            for (let el of all) {
                const ov = window.getComputedStyle(el).overflowY;
                if ((ov === 'auto' || ov === 'scroll') && el.scrollHeight > el.clientHeight) {
                    el.scrollTop = el.scrollHeight;
                }
            }
            window.scrollTo(0, document.body.scrollHeight);
        }""")
        time.sleep(2)

        # Extrair dados da questão discursiva
        dados = page.evaluate(r"""() => {
            function findDeep(root, fn) {
                let res = [];
                const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                while (w.nextNode()) {
                    if (fn(w.currentNode)) res.push(w.currentNode);
                    if (w.currentNode.shadowRoot) res = res.concat(findDeep(w.currentNode.shadowRoot, fn));
                }
                return res;
            }

            // Enunciado da discursiva
            let enunciado = '';
            const wrapQuestion = findDeep(document.body, el => (el.className || '').toString().includes('d2l-questions-question-wrapper'));
            if (wrapQuestion.length > 0) {
                const qTarget = wrapQuestion[wrapQuestion.length - 1];
                const rendered = findDeep(qTarget, el => (el.className || '').toString().includes('d2l-html-block-rendered'));
                enunciado = rendered.length > 0 ? (rendered[0].innerText || '').trim() : (qTarget.innerText || '').trim();
            }

            // Pontuação máxima da questão discursiva
            let pontosMax = 2.0;
            const inputs = findDeep(document.body, el => {
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                return aria.includes('pontuação da pergunta de') || aria.includes('pontuacao da pergunta de');
            });
            if (inputs.length > 0) {
                const aria = inputs[inputs.length - 1].getAttribute('aria-label') || '';
                const m = aria.match(/de\s+(\d+[\.,]?\d*)/i);
                if (m) pontosMax = parseFloat(m[1].replace(',', '.'));
            }

            // Código da questão (EAD_...)
            let codigo = '';
            const allTextEls = findDeep(document.body, el => (el.innerText || '').trim().startsWith('EAD_'));
            for (let el of allTextEls) {
                const t = (el.innerText || '').trim();
                if (t.startsWith('EAD_') && t.length >= 8 && t.length <= 50) {
                    codigo = t;
                    break;
                }
            }

            return { enunciado, pontosMax, codigo };
        }""")

        print("\n" + "=" * 60)
        print("RESULTADO DA EXTRAÇÃO UNIVERSAL VIA CONSISTENT EVALUATION:")
        print("=" * 60)
        print(f"Código da Questão: {dados['codigo']}")
        print(f"Pontuação Máxima: {dados['pontosMax']} pts")
        print(f"Tamanho do Enunciado: {len(dados['enunciado'])} caracteres")
        print(f"Enunciado Completo:\n{dados['enunciado']}")
        print("=" * 60)

    browser.close()
