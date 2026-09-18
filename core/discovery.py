import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List
from playwright.sync_api import sync_playwright

from config import BASE_AVA_URL, NAV_TIMEOUT
from core.browser_session import obter_caminho_auth

def extrair_cards_turmas(page) -> List[Dict[str, str]]:
    cards = page.locator("d2l-enrollment-card, d2l-card, a.d2l-card-container, [role='tabpanel'] a[href*='/d2l/home/']")
    count = cards.count()
    turmas = []
    seen = set()
    descartar = ['recuperação', 'recuperacao', 'comunidade', 'tutoria', 'coordenação', 'coordenacao', 'orientações', 'orientacoes']
    
    for i in range(count):
        el = cards.nth(i)
        txt = el.inner_text().strip()
        href = el.get_attribute("href") or ""
        if not href:
            sub = el.locator("a[href*='/d2l/home/']").first
            if sub.count() > 0:
                href = sub.get_attribute("href") or ""
        
        m = re.search(r'/d2l/home/(\d+)', href)
        if m:
            ou = m.group(1)
            if ou not in seen and ou not in ['6606', '6682', '6803', '50227']:
                linhas = [l.strip() for l in txt.split('\n') if l.strip()]
                nome = linhas[0] if linhas else f"Disciplina {ou}"
                if not any(d in nome.lower() for d in descartar):
                    seen.add(ou)
                    turmas.append({"ou": ou, "name": nome})
    return turmas

def descobrir_todas_abas_e_cursos(username: str, password: str, headless: bool = True) -> Dict[str, Any]:
    """
    Descobre todas as abas e catálogo de disciplinas disponíveis no AVA.
    """
    auth_file = obter_caminho_auth(username)
    resultado = {"abas": ["Fixado", "2026/3", "2026/2", "2026/1", "Todas as Disciplinas"], "disciplinas_por_aba": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        ctx_kwargs = {"viewport": {"width": 1200, "height": 800}}
        if auth_file.exists():
            ctx_kwargs["storage_state"] = str(auth_file)
            
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()
        page.set_default_timeout(NAV_TIMEOUT)

        try:
            page.goto(f"{BASE_AVA_URL}/d2l/home", wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(2)

            if "login" in page.url.lower():
                # Realizar login se necessário
                acesso_direto = page.locator("text='Acesso Direto'").first
                if acesso_direto.count() > 0:
                    acesso_direto.click()
                user_input = page.locator("#userName, #username, #txtUsuario").first
                user_input.fill(username)
                pass_input = page.locator("#password, #txtSenha").first
                pass_input.fill(password)
                page.locator("button[type='submit'], button:has-text('Fazer login')").first.click()
                page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT)
                time.sleep(3)
                context.storage_state(path=str(auth_file))

            # Mapear abas disponíveis
            tab_locators = page.locator("d2l-tab, [role='tab']")
            total_tabs = tab_locators.count()
            abas_encontradas = []

            for i in range(total_tabs):
                nome_aba = tab_locators.nth(i).inner_text().strip()
                if nome_aba and nome_aba not in abas_encontradas:
                    abas_encontradas.append(nome_aba)

            if not abas_encontradas:
                abas_encontradas = ["Fixado", "2026/3", "2026/2", "2026/1"]

            disciplinas_por_aba = {}
            for aba in abas_encontradas:
                try:
                    tab_target = page.locator(f"d2l-tab:has-text('{aba}'), [role='tab']:has-text('{aba}')").first
                    if tab_target.count() > 0:
                        tab_target.click(force=True, timeout=4000)
                        time.sleep(2)
                    cursos = extrair_cards_turmas(page)
                    disciplinas_por_aba[aba] = cursos
                except Exception:
                    disciplinas_por_aba[aba] = []

            # Montar a aba consolidada "Todas as Disciplinas"
            todas = []
            seen_all = set()
            for lista in disciplinas_por_aba.values():
                for c in lista:
                    if c["ou"] not in seen_all:
                        seen_all.add(c["ou"])
                        todas.append(c)

            disciplinas_por_aba["Todas as Disciplinas"] = todas
            if "Todas as Disciplinas" not in abas_encontradas:
                abas_encontradas.append("Todas as Disciplinas")

            resultado["abas"] = abas_encontradas
            resultado["disciplinas_por_aba"] = disciplinas_por_aba

        except Exception as e:
            print(f"Erro na descoberta de cursos: {e}")
        finally:
            browser.close()

    return resultado

