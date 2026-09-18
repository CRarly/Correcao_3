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

    # Inspecionar irmãos e pais do input de pontuação da pergunta de 2
    res = page.evaluate(r"""() => {
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
        let inpScore = null;
        for (let el of all) {
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            if (aria.includes('pontuação da pergunta de 2') || aria.includes('pontuacao da pergunta de 2')) {
                inpScore = el;
                break;
            }
        }
        if (!inpScore) return { found: false };

        // Subir 3 a 5 níveis para pegar o container da pergunta
        let container = inpScore;
        for (let i = 0; i < 5; i++) {
            if (container.parentElement) container = container.parentElement;
        }

        const elements = getAll(container);
        const rel = [];
        for (let el of elements) {
            const tag = el.tagName.toLowerCase();
            const aria = el.getAttribute('aria-label') || '';
            const txt = (el.innerText || el.textContent || '').slice(0, 80);
            if (['input', 'textarea', 'button', 'd2l-button', 'd2l-htmleditor', 'd2l-input-number'].includes(tag) || aria.toLowerCase().includes('feedback')) {
                rel.push({ tag, id: el.id, aria, val: el.value, txt, outer: el.outerHTML.slice(0, 150) });
            }
        }

        return { found: true, elements: rel };
    }""")

    print("Encontrou container:", res.get('found'))
    for el in res.get('elements', []):
        print(" -", el)

    browser.close()
