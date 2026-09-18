import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155388"
act_id = "TmpZd05sODFNVEF3TUY4eU5UUTVOalUuMTU1Mzg4"
url = f"https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/{act_id}?ou={ou}&cft=qe&iteratorRange=all"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)

    # Trocar para Tentativa 1
    page.evaluate(r"""() => {
        function findDeepAll(root, fn) {
            let res = [];
            const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (w.nextNode()) {
                const el = w.currentNode;
                if (fn(el)) res.push(el);
                if (el.shadowRoot) res = res.concat(findDeepAll(el.shadowRoot, fn));
            }
            return res;
        }
        const selects = findDeepAll(document.body, el => el.tagName.toLowerCase() === 'select' && (el.getAttribute('aria-label') || '').toLowerCase().includes('tentativa'));
        if (selects.length > 0) {
            const sel = selects[0];
            for (let opt of sel.options) {
                if ((opt.text || '').toLowerCase().includes('tentativa 1')) {
                    sel.value = opt.value;
                    sel.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                    sel.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                    break;
                }
            }
        }
    }""")
    time.sleep(4)

    resposta_extraida = page.evaluate(r"""() => {
        function findDeepAll(root, fn) {
            let res = [];
            const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (w.nextNode()) {
                const el = w.currentNode;
                if (fn(el)) res.push(el);
                if (el.shadowRoot) res = res.concat(findDeepAll(el.shadowRoot, fn));
            }
            return res;
        }

        function isFeedbackOrPrompt(txt) {
            if (!txt) return true;
            const t = txt.toLowerCase();
            return t.includes('sua resposta para a questão') ||
                   t.includes('sua resposta para a questao') ||
                   t.includes('análise detalhada dos critérios') ||
                   t.includes('analise detalhada dos criterios') ||
                   t.includes('justificativa do desconto') ||
                   t.includes('padrão de resposta') ||
                   t.includes('padrao de resposta') ||
                   t.includes('texto-motivador') ||
                   t.includes('comando da questão') ||
                   t.includes('comando da questao') ||
                   t.includes('prof. avaliador') ||
                   t.startsWith('ead_');
        }

        // 1. Procurar dentro do container de resposta da pergunta escrita
        const respContainers = findDeepAll(document.body, el => (el.className || '').toString().includes('d2l-questions-written-response-question-response'));
        for (let container of respContainers) {
            const innerRendered = findDeepAll(container, el => (el.className || '').toString().includes('d2l-html-block-rendered'));
            for (let b of innerRendered) {
                let t = (b.innerText || '').trim();
                t = t.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
                if (t.length > 5 && !isFeedbackOrPrompt(t)) {
                    return { metodo: '1. respContainer rendered', texto: t };
                }
            }
            // Tentar innerText direto do container
            let tDirect = (container.innerText || '').trim();
            tDirect = tDirect.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
            if (tDirect.length > 5 && !isFeedbackOrPrompt(tDirect)) {
                return { metodo: '1. respContainer direct', texto: tDirect };
            }
        }

        // 2. Procurar elemento imediatamente anterior à contagem de palavras
        const wordCounts = findDeepAll(document.body, el => (el.className || '').toString().includes('word-count') || /^\d+\s+palavras/i.test((el.innerText || '').trim()));
        if (wordCounts.length > 0) {
            const wc = wordCounts[wordCounts.length - 1];
            let prev = wc.previousElementSibling;
            while (prev) {
                const pTxt = (prev.innerText || '').trim();
                if (prev.tagName.toLowerCase() !== 'd2l-offscreen' && pTxt.length > 5 && !isFeedbackOrPrompt(pTxt)) {
                    return { metodo: '2. word-count prev', texto: pTxt };
                }
                prev = prev.previousElementSibling;
            }
        }

        // 3. Fallback: procurar blocos renderizados excluindo estritamente feedback, gabarito e prompt
        const rendered = findDeepAll(document.body, el => (el.className || '').toString().includes('d2l-html-block-rendered'));
        for (let i = rendered.length - 1; i >= 0; i--) {
            let rTxt = (rendered[i].innerText || '').trim();
            rTxt = rTxt.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
            if (rTxt.length > 15 && !isFeedbackOrPrompt(rTxt)) {
                return { metodo: '3. filtered rendered', texto: rTxt };
            }
        }

        return { metodo: 'nenhum', texto: '' };
    }""")

    print("RESULTADO DA EXTRAÇÃO:", resposta_extraida['metodo'])
    print("TEXTO (primeiros 150 caracteres):", resposta_extraida['texto'][:150])
    print("TOTAL PALAVRAS:", len(resposta_extraida['texto'].split()))

    browser.close()

