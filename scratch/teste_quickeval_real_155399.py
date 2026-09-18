import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155399"
url_qe = f"https://ava.catolica.edu.br/d2l/le/{ou}/quickeval/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 1000})
    page = context.new_page()

    print(f"Acessando Quick Eval correto: {url_qe}")
    page.goto(url_qe, wait_until="domcontentloaded", timeout=35000)
    time.sleep(5)
    page.screenshot(path=str(BASE_DIR / "qe_real_155399_top.png"))

    # Clicar na aba Atividades
    clicou_aba = page.evaluate(r"""() => {
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
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt === 'Atividades' && ['d2l-tab', 'button', 'a', 'span'].includes(el.tagName.toLowerCase())) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    print("Clicou aba Atividades:", clicou_aba)
    time.sleep(4)
    page.screenshot(path=str(BASE_DIR / "qe_real_155399_ativ.png"))

    # Extrair itens na aba Atividades
    itens = page.evaluate(r"""() => {
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
        const links = all.filter(el => el.tagName.toLowerCase() === 'a' && (el.getAttribute('href') || '').includes('evaluation/activity'));
        return links.map(a => {
            let p = a;
            let title = '';
            for (let s = 0; s < 8; s++) {
                if (!p) break;
                const inners = getAll(p);
                for (let inEl of inners) {
                    const txt = (inEl.innerText || inEl.textContent || '').replace(/\s+/g, ' ').trim();
                    if (txt && (txt.includes('Avaliação:') || txt.includes('Fórum') || txt.includes('Atividade') || txt.includes('Prova'))) {
                        if (!title || txt.length < title.length) title = txt;
                    }
                }
                if (title) break;
                p = p.parentElement || (p.getRootNode ? p.getRootNode().host : null);
            }
            return {
                title,
                linkText: (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim(),
                href: a.href || a.getAttribute('href')
            };
        });
    }""")

    print(f"\nAtividades no Quick Eval ({len(itens)}):")
    for it in itens:
        print(" -", it)

    # Se encontramos a Prova Presencial no Quick Eval, abrir o link!
    link_prova = None
    for it in itens:
        t = (it['title'] + " " + it['linkText']).lower()
        if "prova presencial" in t or "prova" in t:
            link_prova = it['href']
            break

    if link_prova:
        print(f"\nAcessando página de correção da Prova no Quick Eval: {link_prova}")
        page.goto(link_prova, wait_until="domcontentloaded", timeout=35000)
        time.sleep(6)
        page.screenshot(path=str(BASE_DIR / "qe_prova_155399_eval_screen.png"))
        print("Screenshot salva: qe_prova_155399_eval_screen.png")

    browser.close()
