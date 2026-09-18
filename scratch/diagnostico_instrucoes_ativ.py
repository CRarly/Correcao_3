import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155388"
url_dropbox = f"https://ava.catolica.edu.br/d2l/lms/dropbox/admin/folders_manage.d2l?ou={ou}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(auth_file) if auth_file.exists() else None, viewport={"width": 1400, "height": 900})
    page = context.new_page()

    page.goto(url_dropbox, wait_until="domcontentloaded", timeout=35000)
    time.sleep(5)

    # Inspecionar links de pastas em Tarefas
    pastas = page.evaluate(r"""() => {
        const rows = Array.from(document.querySelectorAll('tr'));
        const list = [];
        for (let r of rows) {
            const txt = (r.innerText || '').trim();
            const link = r.querySelector('a');
            if (txt && link) {
                list.push({ text: txt.replace(/\s+/g, ' ').slice(0, 100), href: link.href });
            }
        }
        return list;
    }""")
    print("Pastas em Tarefas:")
    for p_info in pastas:
        print("  *", p_info)

    # Acessar a pasta da Atividade Aberta clicando no link direto
    link_ativ = next((p['href'] for p in pastas if 'aberta' in p['text'].lower() or 'atividade' in p['text'].lower()), None)
    if link_ativ:
        print(f"\nAcessando link direto da atividade: {link_ativ}")
        page.goto(link_ativ, wait_until="domcontentloaded", timeout=35000)
        time.sleep(5)
        print(f"URL pós-acesso: {page.url} | Título: {page.title()}")

        # Inspecionar texto na página
        text_info = page.evaluate(r"""() => {
            const bodyText = (document.body.innerText || '').trim();
            const blocks = Array.from(document.querySelectorAll('d2l-html-block, .d2l-html-editor-content, [class*="instruction"], [class*="description"], div[class*="content"]')).map(el => ({
                tag: el.tagName,
                cls: el.className,
                txt: (el.innerText || el.textContent || '').trim().slice(0, 200)
            })).filter(b => b.txt.length > 20);
            return { bodyLength: bodyText.length, sampleText: bodyText.slice(0, 400), blocks };
        }""")
        print("Text info:", text_info)

    browser.close()
