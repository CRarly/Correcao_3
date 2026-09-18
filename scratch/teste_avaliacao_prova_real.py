import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
url_prova_eval = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sODFNVEF3TUY4eU5UUTVPRE0uMTU1Mzk5?ou=155399&iteratorRange=new&cfi=sort%7EeyJTb3J0cyI6W3siU29ydCI6eyJJZCI6IjE3YTFhOWE0LTcyOWYtNGJhMy05ZjdmLWRmZTJmOWQzZWVkMiJ9LCJEaXJlY3Rpb24iOjB9XX0&cft=qe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 1000})
    page = context.new_page()

    print(f"1. Acessando Consistent Evaluation: {url_prova_eval}")
    page.goto(url_prova_eval, wait_until="domcontentloaded", timeout=35000)
    time.sleep(10)

    # 2. Rolar a página para carregar a questão 8
    print("2. Rolando painel até a Questão 8...")
    page.evaluate(r"""() => {
        const scrollables = Array.from(document.querySelectorAll('*')).filter(el => {
            const ov = window.getComputedStyle(el).overflowY;
            return (ov === 'auto' || ov === 'scroll') && el.scrollHeight > el.clientHeight;
        });
        for (let s of scrollables) {
            s.scrollTop = s.scrollHeight;
        }
        window.scrollTo(0, document.body.scrollHeight);
    }""")
    time.sleep(3)

    # 3. Extrair nome do aluno e resposta
    dados_aluno = page.evaluate(r"""() => {
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

        // Nome do aluno
        let aluno = '';
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt.includes('Avaliação de') && txt.includes('em Avaliação: Prova presencial')) {
                const m = txt.match(/Avaliação de\s+(.*?)\s+em Avaliação:/i);
                if (m) aluno = m[1].trim();
                break;
            }
        }

        // Resposta da questão 8 (indentada após o enunciado)
        let resposta = '';
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt.includes('Os sistemas de informação são muito importantes') || (txt.includes('SIG') && txt.includes('ERP'))) {
                if (txt.length < 1500) {
                    resposta = txt;
                    break;
                }
            }
        }

        return { aluno, resposta };
    }""")

    print(f"Aluno detectado: {dados_aluno['aluno']}")
    print(f"Resposta detectada ({len(dados_aluno['resposta'])} chars): {dados_aluno['resposta'][:150]}...")

    # 4. Inserir Nota (2.0) no campo da questão 8
    print("\n4. Inserindo nota 2,0 no campo da Questão 8...")
    set_score_res = page.evaluate(r"""(nota) => {
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
        let inp = null;
        for (let el of all) {
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (aria.includes('pontuação da pergunta de 2') || aria.includes('pontuacao da pergunta de 2')) {
                inp = el;
                break;
            }
        }
        if (inp) {
            inp.focus();
            inp.value = nota;
            inp.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
            inp.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
            return { ok: true, id: inp.id, val: inp.value };
        }
        return { ok: false };
    }""", "2")
    print("Resultado inserção da nota:", set_score_res)

    # 5. Inserir Feedback no editor da Questão 8
    feedback_html = (
        "<p>Olá, {FirstName}!</p>"
        "<p>Sua resposta atendeu perfeitamente ao enunciado da questão discursiva. "
        "Você demonstrou compreensão clara do papel estratégico e operacional dos Sistemas de Informação, "
        "apresentando de forma correta e contextualizada os exemplos do SIG (Sistemas de Informações Gerenciais) "
        "e do ERP (Enterprise Resource Planning).</p>"
        "<p><strong>Pontuação atribuída:</strong> 2,0 / 2,0 pontos.</p>"
        "<p>Parabéns pelo excelente desempenho!</p>"
    )

    print("\n5. Inserindo feedback no d2l-htmleditor da Questão 8...")
    set_fb_res = page.evaluate(r"""(fbHtml) => {
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
        const editors = all.filter(el => el.tagName.toLowerCase() === 'd2l-htmleditor' && el.className.includes('d2l-consistent-eval-quiz-question-feedback'));
        if (editors.length > 0) {
            // O último editor corresponde à questão dissertativa
            const target = editors[editors.length - 1];
            target.html = fbHtml;
            target.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
            target.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
            return { ok: true, count: editors.length };
        }
        return { ok: false };
    }""", feedback_html)
    print("Resultado inserção do feedback:", set_fb_res)
    time.sleep(2)

    # 6. Salvar em Rascunho DUAS VEZES (sem publicar!)
    print("\n6. Salvando rascunho 1ª vez...")
    save_draft_1 = page.evaluate(r"""() => {
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
        const btn = all.find(el => el.id === 'consistent-evaluation-footer-save-draft');
        if (btn) {
            const innerBtn = btn.shadowRoot ? btn.shadowRoot.querySelector('button') : null;
            const target = innerBtn || btn;
            target.click();
            return true;
        }
        return false;
    }""")
    print("Salvar rascunho 1:", save_draft_1)
    time.sleep(3)

    print("Salvando rascunho 2ª vez...")
    save_draft_2 = page.evaluate(r"""() => {
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
        const btn = all.find(el => el.id === 'consistent-evaluation-footer-save-draft');
        if (btn) {
            const innerBtn = btn.shadowRoot ? btn.shadowRoot.querySelector('button') : null;
            const target = innerBtn || btn;
            target.click();
            return true;
        }
        return false;
    }""")
    print("Salvar rascunho 2:", save_draft_2)
    time.sleep(3)

    page.screenshot(path=str(BASE_DIR / "qe_prova_155399_evaluated.png"), full_page=True)
    print("Screenshot salva: qe_prova_155399_evaluated.png")

    browser.close()
