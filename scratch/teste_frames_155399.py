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
    print("Clicou no botão 8 - 8. Aguardando 10 segundos para renderizar completamente...")
    time.sleep(10)

    print(f"Total de frames: {len(page.frames)}")
    for i, fr in enumerate(page.frames):
        print(f"Frame {i}: url='{fr.url}' name='{fr.name}'")

    page.screenshot(path=str(BASE_DIR / "quiz_155399_after_10s.png"), full_page=True)

    # Inspecionar em todos os frames
    for i, fr in enumerate(page.frames):
        txts = fr.evaluate(r"""() => {
            return Array.from(document.querySelectorAll('*')).map(e => (e.innerText || '').trim()).filter(t => t.includes('EAD_') || t.includes('SdInO') || t.includes('Pontos por'));
        }""")
        if txts:
            print(f"Textos no Frame {i}:", txts[:5])

    browser.close()
