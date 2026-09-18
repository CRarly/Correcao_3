import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155388"
db = "169898"
url_pasta = f"https://ava.catolica.edu.br/d2l/lms/dropbox/admin/mark/folder_submissions_users.d2l?db={db}&ou={ou}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    print(f"Acessando: {url_pasta}")
    page.goto(url_pasta, wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)

    # Inspecionar atributos do botão Editar Atividade
    btn_info = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('a, button, d2l-button'));
        for (let b of btns) {
            const t = (b.innerText || '').trim();
            if (t === 'Editar Atividade' || t.includes('Editar Atividade')) {
                return {
                    tag: b.tagName,
                    onclick: b.getAttribute('onclick'),
                    href: b.getAttribute('href'),
                    outerHTML: b.outerHTML.slice(0, 300)
                };
            }
        }
        return null;
    }""")
    print("Botão Editar Atividade:", btn_info)

    # Clicar no botão Editar Atividade
    print("\nClicando no botão Editar Atividade...")
    with page.expect_navigation(timeout=15000):
        page.click("text='Editar Atividade'")
    time.sleep(5)

    print(f"URL pós-clique: {page.url} | Título: {page.title()}")

    # Inspecionar a página aberta (Activity Editor)
    detalhes_edicao = page.evaluate(r"""() => {
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

        // 1. Procurar d2l-htmleditor com instruções
        const editores = [];
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'd2l-htmleditor') {
                const html = el.html || el.innerText || '';
                if (html.length > 20) editores.push({ tag: 'd2l-htmleditor', id: el.id, len: html.length, preview: html.slice(0, 300) });
            }
        }

        // 2. Procurar d2l-html-block
        const blocks = [];
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'd2l-html-block') {
                const html = el.html || el.innerHTML || el.innerText || '';
                if (html.length > 50 && !html.includes('Sua sessão')) {
                    blocks.push({ tag: 'd2l-html-block', len: html.length, preview: html.slice(0, 300) });
                }
            }
        }

        // 3. Procurar anexos / arquivos do modelo
        const anexos = [];
        for (let el of all) {
            const txt = (el.innerText || el.textContent || '').trim();
            const aria = (el.getAttribute('aria-label') || '').trim();
            const href = (el.getAttribute('href') || '').trim();
            if (href.includes('Attachment') || href.includes('download') || aria.toLowerCase().includes('anexo')) {
                anexos.push({ txt: txt.slice(0, 50), aria, href: href.slice(0, 80) });
            }
        }

        // 4. Input de nota / pontuação
        const notas = [];
        for (let el of all) {
            if (el.tagName.toLowerCase() === 'd2l-input-number' || el.tagName.toLowerCase() === 'input') {
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                const id = (el.id || '').toLowerCase();
                if (aria.includes('pontuação') || aria.includes('nota') || id.includes('score') || aria.includes('fora de')) {
                    notas.push({ tag: el.tagName, aria, id, val: el.value });
                }
            }
        }

        return { editores, blocks, anexos, notas };
    }""")

    print("\nDetalhes encontrados na edição da Atividade:")
    print("Editores:", detalhes_edicao['editores'])
    print("Blocks:", detalhes_edicao['blocks'])
    print("Anexos:", detalhes_edicao['anexos'])
    print("Notas:", detalhes_edicao['notas'])

    browser.close()
