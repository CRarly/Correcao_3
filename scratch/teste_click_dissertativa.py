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

    page.goto(url_edit, wait_until="domcontentloaded", timeout=35000)
    time.sleep(6)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)

    # Localizar e clicar no botão do pool da QUESTÃO DISSERTATIVA especificamente!
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
        
        // Procurar o container da Questão dissertativa
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            const txtLow = txt.toLowerCase();
            if (txtLow.includes('questão dissertativa') || txtLow.includes('questao dissertativa') || txtLow.includes('resposta dissertativa')) {
                // Procurar botão ou link dentro ou próximo a este elemento
                const btn = el.querySelector ? el.querySelector('button, a, d2l-button') : null;
                const target = btn || (el.closest('button') || el.closest('a') || el);
                if (typeof target.click === 'function') {
                    target.scrollIntoView();
                    target.click();
                    return { clicked: true, tag: target.tagName, txt: txt.slice(0, 80) };
                }
            }
        }
        return { clicked: false };
    }""")
    print("Resultado clique pool dissertativa:", click_res)
    time.sleep(6)

    # Inspecionar frames
    print(f"Total de frames pós-clique: {len(page.frames)}")
    target_frame = None
    for idx, fr in enumerate(page.frames):
        print(f"  Frame [{idx}]: name='{fr.name}', url='{fr.url[:80]}'")
        if "quiz-question-authoring" in fr.url or "authoring" in fr.url:
            target_frame = fr

    ctx = target_frame if target_frame else page
    print(f"\nInspecionando contexto no {'frame ' + ctx.name if target_frame else 'page'}...")

    dados_pool = ctx.evaluate(r"""() => {
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
        let pontos = '';
        const inputs = all.filter(el => el.tagName.toLowerCase() === 'input');
        for (let inp of inputs) {
            const aria = (inp.getAttribute('aria-label') || '').toLowerCase();
            const id = (inp.id || '').toLowerCase();
            if (aria.includes('pontos') || id.includes('point') || aria.includes('pergunta')) {
                pontos = inp.value;
            }
        }

        // Links de questões no pool
        const questoes = [];
        for (let el of all) {
            const tag = el.tagName.toLowerCase();
            if (['a', 'button'].includes(tag)) {
                const txt = (el.innerText || '').trim();
                const href = el.href || '';
                if (txt.length >= 4 && txt.length <= 40 && !txt.includes(' ') && !txt.includes('D2L')) {
                    questoes.push({ tag, txt, href });
                }
            }
        }
        return { pontos, questoes };
    }""")
    print("Dados do Pool:", dados_pool)

    # Se achou questão, clicar nela
    if dados_pool.get("questoes"):
        cod_q = dados_pool["questoes"][0]["txt"]
        print(f"\nClicando no código da questão dissertativa: {cod_q}...")
        ctx.click(f"text='{cod_q}'")
        time.sleep(5)

        enunciado = ctx.evaluate(r"""() => {
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
            let maior = '';
            for (let el of all) {
                const tag = el.tagName.toLowerCase();
                if (['script', 'style', 'noscript'].includes(tag)) continue;
                const txt = (el.innerText || '').trim();
                if (txt.includes('D2L.LP') || txt.includes('D2L.O') || txt.includes('UBEC') || txt.includes('Salvar')) continue;
                if (txt.length > 50 && txt.length > maior.length) {
                    maior = txt;
                }
            }
            return maior;
        }""")
        print(f"\nENUNCIADO DA DISCURSIVA EXTRAÍDO ({len(enunciado)} caracteres):")
        print(enunciado)

    browser.close()
