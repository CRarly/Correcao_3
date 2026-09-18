import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155399"
url_prova_eval = "https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/TmpZd05sODFNVEF3TUY4eU5UUTVPRE0uMTU1Mzk5?ou=155399&iteratorRange=new&cfi=sort%7EeyJTb3J0cyI6W3siU29ydCI6eyJJZCI6IjE3YTFhOWE0LTcyOWYtNGJhMy05ZjdmLWRmZTJmOWQzZWVkMiJ9LCJEaXJlY3Rpb24iOjB9XX0&cft=qe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 1000})
    page = context.new_page()

    print(f"Acessando Consistent Evaluation da Prova: {url_prova_eval}")
    page.goto(url_prova_eval, wait_until="domcontentloaded", timeout=35000)
    
    # Aguardar até que as perguntas carreguem (sair do skeleton)
    print("Aguardando carregamento completo das perguntas do aluno...")
    time.sleep(10)

    # Inspecionar frames
    print(f"Total de frames: {len(page.frames)}")
    for i, fr in enumerate(page.frames):
        print(f"Frame {i}: url='{fr.url[:80]}' name='{fr.name}'")

    # Rolar para baixo tanto no page quanto em eventuais frames
    page.evaluate(r"""() => {
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
            if (el.scrollHeight > el.clientHeight && el.clientHeight > 200) {
                el.scrollTop = el.scrollHeight;
            }
        }
        window.scrollTo(0, document.body.scrollHeight);
    }""")
    time.sleep(3)

    page.screenshot(path=str(BASE_DIR / "qe_prova_155399_after_wait.png"), full_page=True)
    print("Screenshot salva: qe_prova_155399_after_wait.png")

    # Inspecionar textos de todos os frames e da página
    for i, fr in enumerate(page.frames):
        res = fr.evaluate(r"""() => {
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
            
            // Procurar elementos que contêm 'Pergunta 8', 'Questão 8', 'discursiv', 'dissertat', ou 'EAD_SdInO'
            const achados = [];
            for (let el of all) {
                const txt = (el.innerText || el.textContent || '').trim();
                if (txt.includes('Pergunta 8') || txt.includes('Questão 8') || txt.includes('EAD_SdInO_2026_3_PROV_QDIS') || txt.includes('Sistemas de Informação')) {
                    achados.push({
                        tag: el.tagName,
                        className: el.className,
                        id: el.id,
                        txt: txt.slice(0, 200)
                    });
                }
            }
            return achados;
        }""")
        if res:
            print(f"\nNo Frame {i} encontramos:")
            for item in res[:10]:
                print(" -", item)

    browser.close()
