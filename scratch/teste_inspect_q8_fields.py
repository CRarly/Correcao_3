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

    page.goto(url_prova_eval, wait_until="domcontentloaded", timeout=35000)
    time.sleep(10)

    # Rolar o painel de perguntas
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
    time.sleep(2)

    # Inspecionar os elementos exatos da Questão 8
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

        // 1. Encontrar o input de Pontuação da questão
        const pontuacaoInputs = [];
        for (let el of all) {
            if (['input', 'd2l-input-number'].includes(el.tagName.toLowerCase())) {
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                const id = (el.id || '').toLowerCase();
                const name = (el.getAttribute('name') || '').toLowerCase();
                const parentText = (el.parentElement ? el.parentElement.innerText : '').toLowerCase();
                if (aria.includes('pontua') || id.includes('score') || id.includes('point') || parentText.includes('pontuação') || parentText.includes('/ 2')) {
                    pontuacaoInputs.push({
                        tag: el.tagName,
                        id: el.id,
                        name: el.getAttribute('name'),
                        aria: el.getAttribute('aria-label'),
                        className: el.className,
                        val: el.value,
                        parentText: parentText.slice(0, 100)
                    });
                }
            }
        }

        // 2. Encontrar o campo de Feedback da questão
        const feedbackInputs = [];
        for (let el of all) {
            if (['input', 'textarea', 'd2l-input-textarea', 'd2l-htmleditor'].includes(el.tagName.toLowerCase())) {
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                const id = (el.id || '').toLowerCase();
                const parentText = (el.parentElement ? el.parentElement.innerText : '').toLowerCase();
                if (id.includes('feedback') || aria.includes('feedback') || parentText.includes('feedback')) {
                    feedbackInputs.push({
                        tag: el.tagName,
                        id: el.id,
                        name: el.getAttribute('name'),
                        aria: el.getAttribute('aria-label'),
                        className: el.className,
                        parentText: parentText.slice(0, 100)
                    });
                }
            }
        }

        // 3. Resposta do aluno (indentada)
        // Procurar elementos com margem esquerda ou classe específica perto de Pergunta 8
        let respostaAluno = '';
        for (let el of all) {
            const txt = (el.innerText || '').trim();
            if (txt.includes('Os sistemas de informação são muito importantes') || (txt.includes('SIG') && txt.includes('ERP'))) {
                respostaAluno = txt;
                break;
            }
        }

        // 4. Botão Salvar Rascunho
        const botoesRascunho = [];
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt === 'Salvar Rascunho' || txt.includes('Salvar Rascunho')) {
                botoesRascunho.push({
                    tag: el.tagName,
                    id: el.id,
                    className: el.className,
                    disabled: el.hasAttribute('disabled')
                });
            }
        }

        // 5. Botão de próximo usuário (>)
        const botoesProximo = [];
        for (let el of all) {
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            const id = (el.id || '').toLowerCase();
            const txt = (el.innerText || el.textContent || '').trim();
            if (aria.includes('próximo') || aria.includes('proximo') || aria.includes('next') || id.includes('next')) {
                botoesProximo.push({ tag: el.tagName, id: el.id, aria });
            }
        }

        // 6. Contador de usuários (ex: Usuário 1 de 97)
        let contadorUsuario = '';
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (/Usuário\s+\d+\s+de\s+\d+/i.test(txt)) {
                contadorUsuario = txt;
                break;
            }
        }

        return {
            pontuacaoInputs,
            feedbackInputs,
            respostaAluno: respostaAluno.slice(0, 300),
            botoesRascunho,
            botoesProximo,
            contadorUsuario
        };
    }""")

    print("\nRESULTADOS DA INSPEÇÃO DOS ELEMENTOS DA QUESTÃO:")
    print("Contador:", info['contadorUsuario'])
    print("Pontuação Inputs:", info['pontuacaoInputs'])
    print("Feedback Inputs:", info['feedbackInputs'])
    print("Botões Rascunho:", info['botoesRascunho'])
    print("Botões Próximo:", info['botoesProximo'])
    print("\nResposta do aluno localizada:")
    print(info['respostaAluno'])

    browser.close()
