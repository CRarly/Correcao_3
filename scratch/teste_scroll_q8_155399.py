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
    time.sleep(6)

    # Rolar o container da esquerda até o fim
    print("Rolando o painel de perguntas até o final...")
    page.evaluate(r"""() => {
        // Encontrar containers de rolagem
        const scrollables = Array.from(document.querySelectorAll('*')).filter(el => {
            const ov = window.getComputedStyle(el).overflowY;
            return (ov === 'auto' || ov === 'scroll') && el.scrollHeight > el.clientHeight;
        });
        for (let s of scrollables) {
            s.scrollTop = s.scrollHeight;
        }
        window.scrollTo(0, document.body.scrollHeight);
    }""")
    time.sleep(3)

    # Tirar screenshot após rolar
    page.screenshot(path=str(BASE_DIR / "qe_prova_155399_scrolled_q8.png"), full_page=True)
    print("Screenshot salva: qe_prova_155399_scrolled_q8.png")

    # Inspecionar especificamente a Questão 8 / Discursiva
    q8_info = page.evaluate(r"""() => {
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

        // Localizar elemento com "Pergunta 8" ou o código EAD_SdInO_2026_3_PROV_QDIS
        let containerQ8 = null;
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt.includes('Pergunta 8') || txt.includes('EAD_SdInO_2026_3_PROV_QDIS')) {
                // Subir até o container da pergunta
                containerQ8 = el.closest('div[class*="question"]') || el.parentElement || el;
                break;
            }
        }

        const inputsQ8 = [];
        const textosQ8 = [];
        let rootScan = containerQ8 ? getAll(containerQ8.parentElement || containerQ8) : all;

        for (let el of rootScan) {
            const tag = el.tagName.toLowerCase();
            const txt = (el.innerText || el.textContent || '').trim();
            if (txt.length > 20 && !txt.includes('D2L.LP') && !txt.includes('Tentativa 1')) {
                textosQ8.push({ tag, txt: txt.slice(0, 150) });
            }
            if (['input', 'textarea', 'd2l-htmleditor', 'd2l-input-number'].includes(tag)) {
                inputsQ8.push({
                    tag,
                    id: el.id,
                    aria: el.getAttribute('aria-label'),
                    name: el.getAttribute('name'),
                    val: el.value || el.getAttribute('value')
                });
            }
        }

        // Todos os botões na página
        const botoes = all.filter(el => ['button', 'd2l-button'].includes(el.tagName.toLowerCase())).map(b => ({
            tag: b.tagName,
            id: b.id,
            txt: (b.innerText || b.textContent || '').trim()
        })).filter(b => b.txt);

        return {
            achouContainer: !!containerQ8,
            inputsQ8: inputsQ8.slice(0, 20),
            textosQ8: textosQ8.slice(0, 20),
            botoes
        };
    }""")

    print("\nInformações da Questão 8 / Tela:")
    print("Container achado:", q8_info['achouContainer'])
    print("Inputs:", q8_info['inputsQ8'])
    print("Botões encontrados:", q8_info['botoes'])
    print("Textos:")
    for t in q8_info['textosQ8'][:10]:
        print(" -", t)

    browser.close()
