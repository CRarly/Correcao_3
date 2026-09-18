import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
url_edit_quiz = "https://ava.catolica.edu.br/d2l/le/activities/edit/TmpZd05sODFNVEF3TUY4eU5UUTVOalUuMTU1Mzg4?cft=quiz&launchedFromLessons=False"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    page.goto(url_edit_quiz, wait_until="domcontentloaded", timeout=35000)
    time.sleep(6)

    # Rolar até Perguntas
    page.evaluate("window.scrollTo(0, 1000);")
    time.sleep(2)

    # Clicar em "editar conjunto de perguntas" ou "Questão dissertativa"
    print("Clicando no conjunto de perguntas da Questão dissertativa...")
    clicked = page.evaluate(r"""() => {
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
        for (let el of getAll(document.body)) {
            const txt = (el.innerText || '').toLowerCase();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (txt.includes('editar conjunto de perguntas') || aria.includes('editar conjunto de perguntas') || 
                (txt.includes('questão dissertativa') && el.tagName.toLowerCase() === 'span')) {
                const target = el.closest('button') || el.closest('a') || el;
                if (typeof target.click === 'function') {
                    target.click();
                    return { ok: true, tag: target.tagName, txt: (target.innerText||'').slice(0, 50) };
                }
            }
        }
        return { ok: false };
    }""")
    print("Resultado clique pool:", clicked)
    time.sleep(6)

    print(f"\nFrames pós-clique pool ({len(page.frames)}):")
    target_frame = None
    for idx, fr in enumerate(page.frames):
        print(f"  Frame [{idx}]: name='{fr.name}', url='{fr.url[:80]}'")
        if "quiz-question-authoring" in fr.url or "authoring" in fr.url or "pool" in fr.url:
            target_frame = fr

    ctx = target_frame if target_frame else page
    print(f"\nInspecionando contexto de perguntas (usando {'frame ' + ctx.name if target_frame else 'página principal'})...")

    pool_elements = ctx.evaluate(r"""() => {
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
        const codes = [];
        let pontos = '';
        for (let el of all) {
            const txt = (el.innerText || '').trim();
            const aria = (el.getAttribute('aria-label') || '').trim();
            if (aria.includes('Pontos por pergunta') || txt.includes('Pontos por pergunta')) {
                const inp = el.querySelector ? el.querySelector('input') : null;
                if (inp) pontos = inp.value;
            }
            if (el.tagName.toLowerCase() === 'a' || el.tagName.toLowerCase() === 'button') {
                if (txt.length >= 5 && txt.length <= 40 && /^[A-Z0-9\-_]+$/.test(txt)) {
                    codes.push({ tag: el.tagName, txt, href: el.href || '' });
                }
            }
        }
        // Amostra de links e botões
        const sampleLinks = all.filter(el => ['a', 'button', 'span'].includes(el.tagName.toLowerCase()) && el.innerText && el.innerText.trim().length > 3 && el.innerText.trim().length < 50).slice(0, 20).map(e => ({ tag: e.tagName, txt: e.innerText.trim() }));

        return { pontos, codes, sampleLinks };
    }""")
    print("Pool elements:", pool_elements)

    # Se achou código da questão, clicar nele
    if pool_elements.get("codes"):
        cod = pool_elements["codes"][0]["txt"]
        print(f"\nClicando no código da questão: '{cod}'...")
        ctx.click(f"text='{cod}'")
        time.sleep(4)

        enunciado_info = ctx.evaluate(r"""() => {
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
                if (txt.length > 50 && !txt.includes('D2L.LP') && !txt.includes('UBEC') && !txt.includes('Voltar')) {
                    if (txt.length > maior.length) maior = txt;
                }
            }
            return { maiorLength: maior.length, sample: maior.slice(0, 300), full: maior };
        }""")
        print(f"Enunciado extraído ({enunciado_info['maiorLength']} caracteres):")
        print(enunciado_info['sample'])

    browser.close()
