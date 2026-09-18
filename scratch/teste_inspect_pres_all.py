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

    res = page.evaluate(r"""() => {
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
        if (pres.length === 0) return { error: 'pres not found' };
        
        const pEl = pres[0];
        const allInside = findDeepAll(pEl.shadowRoot || pEl, el => true);
        return allInside.map(el => ({
            tag: el.tagName,
            cls: (el.className || '').toString(),
            id: el.id,
            text: (el.innerText || '').slice(0, 150).replace(/\s+/g, ' ')
        }));
    }""")

    print(f"Total elements inside pres: {len(res)}")
    for idx, el in enumerate(res):
        print(f"[{idx}] {el['tag']}.{el['cls'][:40]} -> {el['text'][:80]}")

    browser.close()
