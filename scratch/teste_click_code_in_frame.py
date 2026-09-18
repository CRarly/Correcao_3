import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155399"
qi = "254983"
url_edit = f"https://ava.catolica.edu.br/d2l/lms/quizzing/admin/modify/quiz_newedit_properties.d2l?qi={qi}&ou={ou}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 1000})
    page = context.new_page()

    page.goto(url_edit, wait_until="domcontentloaded", timeout=35000)
    time.sleep(4)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)

    page.click("button:has-text('8 - 8')")
    print("Clicou no botão 8 - 8. Aguardando 8s...")
    time.sleep(8)

    # Localizar o frame do modal
    modal_frame = None
    for fr in page.frames:
        txt = fr.evaluate(r"() => document.body ? document.body.innerText : ''")
        if "EAD_SdInO" in txt or "Edição de Grupo" in txt or "Editar de Conjunto" in txt:
            modal_frame = fr
            break

    if not modal_frame:
        print("Frame do modal não encontrado!")
        sys.exit(1)

    print(f"Frame do modal localizado: name='{modal_frame.name}', url='{modal_frame.url}'")

    # Extrair pontos por pergunta no frame
    pontos = modal_frame.evaluate(r"""() => {
        const inps = Array.from(document.querySelectorAll('input, d2l-input-number'));
        for (let inp of inps) {
            const aria = (inp.getAttribute('aria-label') || '').toLowerCase();
            const id = (inp.id || '').toLowerCase();
            if (aria.includes('pontos') || id.includes('point')) {
                return inp.value || inp.getAttribute('value');
            }
        }
        return '2';
    }""")
    print(f"Pontos por pergunta no modal: {pontos}")

    # Clicar no código EAD_SdInO_2026_3_PROV_QDIS
    print("Clicando no código da questão EAD_SdInO_2026_3_PROV_QDIS...")
    clicado = modal_frame.evaluate(r"""() => {
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
            if (txt === 'EAD_SdInO_2026_3_PROV_QDIS' || txt.includes('EAD_SdInO')) {
                const target = el.closest('button') || el.closest('a') || el;
                target.scrollIntoView();
                target.click();
                return { clicked: true, tag: target.tagName, txt };
            }
        }
        return { clicked: false };
    }""")
    print("Resultado clique código:", clicado)
    time.sleep(6)

    # Inspecionar frames novamente (pode abrir outro modal ou navegar o frame)
    print(f"\nTotal frames pós clique no código: {len(page.frames)}")
    page.screenshot(path=str(BASE_DIR / "quiz_155399_after_click_code.png"), full_page=True)

    for i, fr in enumerate(page.frames):
        txt = fr.evaluate(r"() => document.body ? document.body.innerText : ''")
        if len(txt) > 30:
            print(f"Frame {i} text preview ({len(txt)} chars): {txt[:300].replace(chr(10), ' ')}")

    # Extrair enunciado em qualquer frame ou na página
    for fr in page.frames:
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
            for (let el of all) {
                if (el.tagName.toLowerCase() === 'd2l-htmleditor') {
                    const html = el.html || el.innerText || '';
                    if (html.length > 30) return { source: 'd2l-htmleditor', text: html };
                }
                if (el.tagName.toLowerCase() === 'd2l-html-block') {
                    const html = el.html || el.innerHTML || el.innerText || '';
                    if (html.length > 50 && !html.includes('Sua sessão') && !html.includes('VICTOR')) return { source: 'd2l-html-block', text: html };
                }
            }
            const txtarea = document.querySelector('textarea');
            if (txtarea && txtarea.value && txtarea.value.length > 30 && !txtarea.value.includes('VICTOR')) {
                return { source: 'textarea', text: txtarea.value };
            }
            return null;
        }""")
        if res:
            print("\nENUNCIADO EXTRAÍDO COM SUCESSO!")
            print(f"Fonte: {res['source']}")
            print(res['text'])
            break

    browser.close()
