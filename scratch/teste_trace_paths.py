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

    anc = page.evaluate(r"""() => {
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

        function getPath(el) {
            let p = el;
            let path = [];
            while (p && p !== document.body) {
                let s = p.tagName.toLowerCase();
                if (p.id) s += '#' + p.id;
                else if (p.className) s += '.' + (p.className || '').toString().trim().split(/\s+/).join('.');
                path.unshift(s);
                p = p.parentElement || (p.parentNode && p.parentNode.host ? p.parentNode.host : null);
            }
            return path.join(' > ');
        }

        const rendered = findDeepAll(document.body, el => (el.className || '').toString().includes('d2l-html-block-rendered'));
        
        let targetAluno = null;
        let targetFeedback = null;
        let targetEnunciado = null;

        for (let r of rendered) {
            const txt = (r.innerText || '').trim();
            if (txt.includes('EAD_ES_2026_3_PROV_DIS')) {
                targetEnunciado = { txt: txt.slice(0, 100), path: getPath(r) };
            }
            if (txt.includes('Como a equipe estava')) {
                targetAluno = { txt: txt.slice(0, 100), path: getPath(r) };
            }
            if (txt.includes('Sua resposta para a Questão Discursiva')) {
                targetFeedback = { txt: txt.slice(0, 100), path: getPath(r) };
            }
        }

        return { targetEnunciado, targetAluno, targetFeedback };
    }""")

    print("ENUNCIADO:", anc['targetEnunciado'])
    print("\nALUNO:", anc['targetAluno'])
    print("\nFEEDBACK:", anc['targetFeedback'])

    browser.close()
