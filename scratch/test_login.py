import time
from pathlib import Path
from playwright.sync_api import sync_playwright

auth_path = Path("auth_state_04083941.json")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    print("Acessando tela de login...")
    page.goto("https://ava.catolica.edu.br/d2l/login", wait_until="domcontentloaded")
    time.sleep(2)

    btn_acesso = page.get_by_text("Acesso Direto")
    if btn_acesso.count() > 0:
        print("Clicando no botão 'Acesso Direto'...")
        btn_acesso.first.click()
        time.sleep(2)

    user_inp = page.locator("input#userName, input#username")
    pass_inp = page.locator("input#password, input#txtSenha")
    submit_btn = page.locator("button.d2l-button, button[type='submit']")

    print("Preenchendo usuário e senha...")
    user_inp.first.fill("04083941")
    pass_inp.first.fill("04083941")
    submit_btn.first.click()

    page.wait_for_load_state("domcontentloaded")
    time.sleep(5)

    print("URL final:", page.url)
    print("Título:", page.title())

    if "login" not in page.url.lower():
        page.context.storage_state(path=str(auth_path))
        print("Sucesso! auth_state_04083941.json atualizado com cookie válido!")
    else:
        print("Ainda na tela de login:", page.url)

    browser.close()
