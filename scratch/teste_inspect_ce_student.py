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

    print(f"Navegando: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(6)

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
    time.sleep(5)

    # Inspecionar todos os blocos na região da discursiva
    info = page.evaluate(r"""() => {
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

        const qWrappers = findDeepAll(document.body, el => (el.className || '').toString().includes('written-response') || el.tagName.toLowerCase().includes('written-response'));
        const rendered = findDeepAll(document.body, el => (el.className || '').toString().includes('d2l-html-block-rendered'));
        
        return {
            qWrappers: qWrappers.map(el => ({ tag: el.tagName, cls: el.className, text: (el.innerText || '').slice(0, 150) })),
            renderedCount: rendered.length,
            renderedSamples: rendered.map((el, i) => ({ idx: i, tag: el.tagName, cls: el.className, text: (el.innerText || '').slice(0, 150) }))
        };
    }""")

    print(f"Rendered count: {info['renderedCount']}")
    print("QWrappers:", info['qWrappers'])
    print("\nUltimos 10 Rendered:")
    for r in info['renderedSamples'][-10:]:
        print(f"[{r['idx']}] {r['tag']} (cls: {r['cls'][:30]}): {r['text'][:100]}...")

    browser.close()
