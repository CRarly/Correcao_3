import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155388"
db = "169898"

# Testar as duas URLs: a de envio do estudante (onde aparecem as instruções) e a de edição do professor
url_aluno = f"https://ava.catolica.edu.br/d2l/lms/dropbox/user/folder_submit_files.d2l?db={db}&ou={ou}"
url_edit = f"https://ava.catolica.edu.br/d2l/lms/dropbox/admin/modify/folder_newedit_properties.d2l?db={db}&ou={ou}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    print(f"1. Acessando URL do Aluno/Submissão: {url_aluno}")
    page.goto(url_aluno, wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)
    print(f"   Título: {page.title()}")
    info_aluno = page.evaluate(r"""() => {
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
        let maiorTexto = '';
        for (let el of all) {
            if (['script', 'style', 'noscript'].includes(el.tagName.toLowerCase())) continue;
            const txt = (el.innerText || '').trim();
            if (txt.includes('Instruções') || txt.includes('instruções') || txt.length > maiorTexto.length) {
                if (txt.length < 10000 && !txt.includes('D2L.LP') && !txt.includes('UBEC')) {
                    if (txt.length > maiorTexto.length) maiorTexto = txt;
                }
            }
        }
        // Anexos do professor
        const anexos = Array.from(document.querySelectorAll('a[href*="Attachment"], a[href*="download"], a[class*="attachment"]')).map(a => a.innerText.trim()).filter(Boolean);
        return { maiorTexto: maiorTexto.slice(0, 500), anexos };
    }""")
    print("   Resultado URL do Aluno:", info_aluno)

    print(f"\n2. Acessando URL de Edição da Pasta: {url_edit}")
    page.goto(url_edit, wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)
    print(f"   URL final: {page.url} | Título: {page.title()}")
    info_edit = page.evaluate(r"""() => {
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
        let maiorTexto = '';
        for (let el of all) {
            if (['script', 'style', 'noscript'].includes(el.tagName.toLowerCase())) continue;
            const txt = (el.innerText || '').trim();
            if (txt.length > 50 && txt.length > maiorTexto.length && !txt.includes('D2L.LP') && !txt.includes('UBEC')) {
                maiorTexto = txt;
            }
        }
        return { maiorTexto: maiorTexto.slice(0, 500) };
    }""")
    print("   Resultado URL de Edição:", info_edit)

    # 3. Testar botão 'Editar Atividade' clicando nele a partir da tela de envios de pasta
    url_pasta = f"https://ava.catolica.edu.br/d2l/lms/dropbox/admin/mark/folder_submissions_users.d2l?db={db}&ou={ou}"
    print(f"\n3. Acessando tela de envios de pasta e localizando botão 'Editar Atividade': {url_pasta}")
    page.goto(url_pasta, wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)
    btn_link = page.evaluate("""() => {
        const links = Array.from(document.querySelectorAll('a, button'));
        for (let l of links) {
            const t = (l.innerText || '').trim();
            if (t === 'Editar Atividade' || t.includes('Editar Atividade') || t.includes('Editar pasta')) {
                return { text: t, href: l.href || '' };
            }
        }
        return null;
    }""")
    print("   Botão Editar Atividade encontrado:", btn_link)

    browser.close()
