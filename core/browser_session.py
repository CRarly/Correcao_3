import os
import json
import time
from pathlib import Path
from typing import Optional, Tuple
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from config import LOGIN_URL, BASE_AVA_URL, NAV_TIMEOUT
from engine_state import state

def obter_caminho_auth(username: str) -> Path:
    base = Path(__file__).resolve().parent.parent
    return base / f"auth_state_{username}.json"

class BrowserSession:
    """
    Gerenciador da sessão de navegação do Playwright.
    Suporta persistência de sessão (cookies/storage state), contexto isolado e utilitários de DOM.
    """
    active_session: Optional['BrowserSession'] = None

    def __init__(self, username: str = "", password: str = "", headless: bool = True):
        self.username = username
        self.password = password
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.nome_docente: str = "Prof. Avaliador"
        self._aborted = False

    def iniciar(self) -> Page:
        BrowserSession.active_session = self
        self._aborted = False
        state.log(f"Iniciando navegador Chromium (Headless: {self.headless})...")
        self.playwright = sync_playwright().start()
        
        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled"
        ]
        
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=args
        )

        auth_path = obter_caminho_auth(self.username) if self.username else None
        
        if auth_path and auth_path.exists():
            state.log(f"Reutilizando sessão salva: {auth_path.name}")
            try:
                self.context = self.browser.new_context(
                    storage_state=str(auth_path),
                    viewport={"width": 1400, "height": 900}
                )
            except Exception as e:
                state.log(f"Falha ao carregar storage_state ({e}), criando novo contexto.", "WARN")
                self.context = self.browser.new_context(viewport={"width": 1400, "height": 900})
        else:
            self.context = self.browser.new_context(viewport={"width": 1400, "height": 900})

        self.page = self.context.new_page()
        self.page.set_default_timeout(NAV_TIMEOUT)
        
        # Realizar ou validar login
        self.garantir_login()
        self.detectar_docente()
        return self.page

    def garantir_login(self):
        state.log("Acessando painel principal do AVA Católica...")
        self.page.goto(BASE_AVA_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        time.sleep(2)

        # Checar se caiu na tela de login
        if "login" in self.page.url.lower() or self.page.locator("input#userName, input#username, input#txtUsuario").count() > 0:
            state.log("Autenticação necessária. Efetuando login...")
            if not self.username or not self.password:
                raise ValueError("Credenciais não fornecidas para autenticação no AVA.")

            # No portal UBEC / Catolica, pode haver uma aba ou botao 'Acesso Direto' que torna os campos visiveis
            try:
                acesso_direto = self.page.get_by_text("Acesso Direto").first
                if acesso_direto.count() > 0:
                    acesso_direto.click()
                    time.sleep(1.5)
            except Exception:
                pass

            # Preencher usuário e senha
            user_input = self.page.locator("input#userName, input#username, input#txtUsuario").first
            pass_input = self.page.locator("input#password, input#txtSenha").first
            submit_btn = self.page.locator("button[type='submit'], input[type='submit'], button#btnLogin, button:has-text('Fazer login')").first

            user_input.wait_for(state="visible", timeout=15000)
            user_input.fill(self.username)
            pass_input.fill(self.password)
            submit_btn.click()
            
            # Aguardar pós-login
            self.page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(4)

            # Salvar auth state
            if self.username:
                auth_path = obter_caminho_auth(self.username)
                self.context.storage_state(path=str(auth_path))
                state.log(f"Sessão autenticada e armazenada em {auth_path.name}")

    def detectar_docente(self):
        try:
            # Tentar extrair nome do menu superior de perfil
            btn_user = self.page.locator("d2l-navigation-button-notification-icon, .d2l-navigation-s-personal-menu, span.d2l-navigation-s-personal-menu-text")
            if btn_user.count() > 0:
                texto = btn_user.first.inner_text().strip()
                if texto and len(texto) > 3:
                    if not texto.lower().startswith("prof"):
                        self.nome_docente = f"Prof. {texto}"
                    else:
                        self.nome_docente = texto
                    state.log(f"Docente autenticado(a): {self.nome_docente}")
                    return
        except Exception:
            pass
        self.nome_docente = "Prof. Arly Cristopher Nascimento Alves"
        state.log(f"Docente ativo para assinaturas: {self.nome_docente}")

    def fechar(self):
        try:
            if self.page:
                self.page.close()
        except Exception:
            pass
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
        if BrowserSession.active_session == self:
            BrowserSession.active_session = None
        state.log("Sessão do navegador encerrada com sucesso.")

    def abortar(self):
        """Força o fechamento imediato de todos os contextos do navegador para cancelar qualquer execução."""
        self._aborted = True
        state.log("Abortando sessão ativa do navegador...", "WARN")
        self.fechar()

    @classmethod
    def abortar_sessao_ativa(cls):
        """Cancela instantaneamente a sessão ativa se houver uma em andamento."""
        if cls.active_session:
            try:
                cls.active_session.abortar()
            except Exception:
                pass
            cls.active_session = None

