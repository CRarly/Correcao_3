import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
url_prova = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sODFNVEF3TUY4eU5UUTVPRE0uMTU1Mzk5?ou=155399&iteratorRange=new&cft=qe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 1000})
    page = context.new_page()

    page.goto(url_prova, wait_until="domcontentloaded", timeout=35000)
    time.sleep(10)

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

    page.screenshot(path=str(BASE_DIR / "raul_screen.png"), full_page=True)

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
        
        let foundQ8 = false;
        const list = [];
        for (let el of all) {
            const txt = (el.innerText || '').trim();
            if (txt.includes('Pergunta 8') || txt.includes('EAD_SdInO')) foundQ8 = true;
            if (foundQ8 && txt.length > 5 && !txt.includes('D2L.LP')) {
                if (!list.some(l => l.txt === txt)) {
                    list.push({ tag: el.tagName, txt: txt.slice(0, 100) });
                }
            }
        }
        return list.slice(0, 20);
    }""")

    print("Elemento na tela de Raul:")
    for it in info:
        print(" -", it)

    browser.close()
