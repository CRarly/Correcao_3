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

    # Inspecionar elementos ao redor do Feedback da Questão 8
    info_fb = page.evaluate(r"""() => {
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

        // Encontrar elemento com texto "Final de Questão dissertativa"
        let finalElem = null;
        for (let el of all) {
            if ((el.innerText || '').includes('Final de Questão dissertativa')) {
                finalElem = el;
                break;
            }
        }

        const elementsPerto = [];
        if (finalElem) {
            // Pegar o container irmão ou pai
            const parent = finalElem.parentElement;
            const inners = getAll(parent);
            for (let el of inners) {
                elementsPerto.push({
                    tag: el.tagName,
                    id: el.id,
                    className: el.className,
                    aria: el.getAttribute('aria-label'),
                    txt: (el.innerText || el.textContent || '').slice(0, 50),
                    isContentEditable: el.isContentEditable,
                    hasShadow: !!el.shadowRoot
                });
            }
        }

        return { elementsPerto: elementsPerto.slice(0, 40) };
    }""")

    print(f"Elementos encontrados perto do final da questão ({len(info_fb['elementsPerto'])}):")
    for el in info_fb['elementsPerto']:
        print(" -", el)

    browser.close()
