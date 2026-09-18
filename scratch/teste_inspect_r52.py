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

    details = page.evaluate(r"""() => {
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

        const pres = findDeepAll(document.body, el => el.tagName.toLowerCase() === 'd2l-questions-written-response-presentational');
        let presChildren = [];
        if (pres.length > 0) {
            const pEl = pres[0];
            const pRoot = pEl.shadowRoot || pEl;
            presChildren = findDeepAll(pRoot, el => true).map(el => ({
                tag: el.tagName,
                cls: el.className,
                text: (el.innerText || '').slice(0, 100),
                parent: el.parentElement ? el.parentElement.tagName : null
            }));
        }

        const rendered = findDeepAll(document.body, el => (el.className || '').toString().includes('d2l-html-block-rendered'));
        const r51 = rendered.length > 51 ? {
            tag: rendered[51].tagName,
            cls: rendered[51].className,
            text: (rendered[51].innerText || '').slice(0, 200),
            parent: rendered[51].parentElement ? rendered[51].parentElement.tagName + '.' + rendered[51].parentElement.className : ''
        } : null;

        const r52 = rendered.length > 52 ? {
            tag: rendered[52].tagName,
            cls: rendered[52].className,
            text: (rendered[52].innerText || '').slice(0, 200),
            parent: rendered[52].parentElement ? rendered[52].parentElement.tagName + '.' + rendered[52].parentElement.className : ''
        } : null;

        const r53 = rendered.length > 53 ? {
            tag: rendered[53].tagName,
            cls: rendered[53].className,
            text: (rendered[53].innerText || '').slice(0, 200),
            parent: rendered[53].parentElement ? rendered[53].parentElement.tagName + '.' + rendered[53].parentElement.className : ''
        } : null;

        return { presChildren, r51, r52, r53 };
    }""")

    print("r51 (Enunciado):", details['r51'])
    print("r52 (Aluno):", details['r52'])
    print("r53 (Feedback):", details['r53'])
    print("\nPres Children (first 10):")
    for c in details['presChildren'][:10]:
        print(" ", c)

    browser.close()
