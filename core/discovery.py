import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List
from playwright.sync_api import sync_playwright

from config import BASE_AVA_URL, NAV_TIMEOUT
from core.browser_session import obter_caminho_auth
from engine_state import state

def descobrir_todas_abas_e_cursos(username: str, password: str, headless: bool = True) -> Dict[str, Any]:
    """
    Descobre todas as abas e catálogo de disciplinas disponíveis no AVA:
    - Mapeia todos os períodos letivos no formato AAAA/T (ex.: 2026/1, 2026/2, 2026/3, etc.).
    - Mapeia a aba 'Fixado', trazendo estritamente as turmas que possuem pin ativo.
    - Suporta setas de navegação do layout de abas e acionamento de 'Exibir Todos os Cursos'.
    - Rola o painel para garantir o carregamento exaustivo de todas as disciplinas da aba.
    - Consolida todas as turmas em 'Todas as Disciplinas'.
    """
    auth_file = obter_caminho_auth(username)
    resultado = {"abas": ["Fixado", "Todas as Disciplinas"], "disciplinas_por_aba": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        ctx_kwargs = {"viewport": {"width": 1280, "height": 900}}
        if auth_file.exists():
            ctx_kwargs["storage_state"] = str(auth_file)

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()
        page.set_default_timeout(NAV_TIMEOUT)

        try:
            page.goto(f"{BASE_AVA_URL}/d2l/home", wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3)

            # Verificar se redirecionou para tela de login
            precisa_login = False
            if "login" in page.url.lower() and "página inicial" not in page.title().lower():
                precisa_login = True
            elif page.locator("input#userName, input#username, #userName").count() > 0 and "página inicial" not in page.title().lower():
                precisa_login = True

            if precisa_login:
                state.log("Sessão expirada ou não autenticada. Realizando login...")
                user_input = page.locator("input#userName, input#username, #userName").first
                if not user_input.is_visible():
                    state.log("Painel 'Acesso Direto' retraído. Expandindo formulário de login...")
                    btn_acesso = page.get_by_text("Acesso Direto").first
                    if btn_acesso.count() > 0:
                        btn_acesso.click()
                    else:
                        opener = page.locator(".d2l-collapsible-panel-opener, button:has-text('Acesso Direto')").first
                        if opener.count() > 0:
                            opener.click()
                    time.sleep(1.5)

                user_input.wait_for(state="visible", timeout=15000)
                user_input.fill(username)
                pass_input = page.locator("input#password, input#txtSenha, #password").first
                pass_input.fill(password)
                submit_btn = page.locator("button.d2l-button:has-text('Fazer login'), button:has-text('Fazer login'), button.d2l-button, button[type='submit']").first
                submit_btn.click()
                time.sleep(4)
                page.goto(f"{BASE_AVA_URL}/d2l/home", wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                time.sleep(2)
                context.storage_state(path=str(auth_file))

            # Executar descoberta avançada atravessando shadow DOMs
            dados_descoberta = page.evaluate(r"""async () => {
                function querySelectorAllDeep(selector, root = document) {
                    let results = Array.from(root.querySelectorAll(selector));
                    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                    let node;
                    while (node = walker.nextNode()) {
                        if (node.shadowRoot) {
                            results = results.concat(querySelectorAllDeep(selector, node.shadowRoot));
                        }
                    }
                    return results;
                }

                // 1. Tentar abrir o diálogo 'Exibir Todos os Cursos' para visão completa de todas as abas e turmas
                const viewAllLinks = querySelectorAllDeep('#viewAllCourses, d2l-link');
                const viewAllBtn = viewAllLinks.find(l => {
                    const txt = (l.innerText || l.getAttribute('text') || '').toLowerCase();
                    return txt.includes('exibir todo') || txt.includes('exibir toda') || l.id === 'viewAllCourses';
                });

                let usandoDialog = false;
                let rootScope = document;

                if (viewAllBtn) {
                    viewAllBtn.click();
                    await new Promise(r => setTimeout(r, 3000));
                    const openedDialog = querySelectorAllDeep('d2l-dialog-fullscreen').find(d => d.hasAttribute('opened'));
                    if (openedDialog) {
                        usandoDialog = true;
                        rootScope = openedDialog;
                    }
                }

                // 2. Mapear todas as abas disponíveis
                const allTabs = querySelectorAllDeep('d2l-tab', rootScope);
                const abasInfo = [];

                for (const t of allTabs) {
                    const title = (t.getAttribute('title') || t.innerText || (t.shadowRoot ? t.shadowRoot.textContent : '') || '').trim();
                    const id = t.id || '';
                    const controlsId = t.getAttribute('aria-controls') || '';
                    if (title) {
                        abasInfo.push({ id, title, controlsId, element: t });
                    }
                }

                // Filtrar abas de interesse:
                // - "Fixado" (id inclui pinned ou title inclui Fixad)
                // - Períodos no formato \d{4}/\d+ (ex: 2026/1, 2026/2, 2026/3, etc.)
                // - "Todos" (id inclui search-my-enrollments ou title inclui Todos)
                const periodosEncontrados = [];
                let tabFixado = null;
                let tabTodos = null;

                const regexPeriodo = /^\d{4}\/\d+$/;

                for (const aba of abasInfo) {
                    const t = aba.title;
                    if (regexPeriodo.test(t)) {
                        periodosEncontrados.push(aba);
                    } else if (t.toLowerCase().includes('fixad') || aba.id.includes('pinned')) {
                        tabFixado = aba;
                    } else if (t.toLowerCase() === 'todos' || aba.id.includes('search-my-enrollments')) {
                        tabTodos = aba;
                    }
                }

                // Ordenar períodos cronologicamente decrescente (ex: 2026/3, 2026/2, 2026/1, 2025/4...)
                periodosEncontrados.sort((a, b) => {
                    const [anoA, triA] = a.title.split('/').map(Number);
                    const [anoB, triB] = b.title.split('/').map(Number);
                    if (anoB !== anoA) return anoB - anoA;
                    return triB - triA;
                });

                // Lista de abas a serem extraídas
                const abasProcessar = [];
                if (tabFixado) abasProcessar.push({ nome: 'Fixado', aba: tabFixado, isFixado: true });
                for (const p of periodosEncontrados) {
                    abasProcessar.push({ nome: p.title, aba: p, isFixado: false });
                }
                if (tabTodos) abasProcessar.push({ nome: 'Todos', aba: tabTodos, isFixado: false, isTodos: true });

                const descartar = ['recuperação', 'recuperacao', 'comunidade', 'tutoria', 'coordenação', 'coordenacao', 'orientações', 'orientacoes'];
                const ousIgnorar = ['6606', '6682', '6803', '50227'];

                const disciplinasPorAba = {};
                const todosCursosConsolidados = [];
                const seenGeral = new Set();

                // 3. Iterar por cada aba e extrair disciplinas completas
                for (const item of abasProcessar) {
                    const tabEl = item.aba.element;

                    if (tabEl) {
                        // Se não estiver usando dialog, acionar seta para navegar nas abas se necessário
                        if (!usandoDialog) {
                            const d2lTabs = document.querySelector('d2l-tabs');
                            if (d2lTabs && d2lTabs.shadowRoot) {
                                const nextBtn = d2lTabs.shadowRoot.querySelector('button.d2l-tabs-scroll-button[title*="frente"]');
                                if (nextBtn && !nextBtn.disabled) nextBtn.click();
                            }
                        }

                        tabEl.click();
                        await new Promise(r => setTimeout(r, 1800));
                    }

                    // Encontrar o painel de cards correspondente
                    const panelId = item.aba.controlsId;
                    const panel = panelId ? (document.getElementById(panelId) || querySelectorAllDeep('#' + panelId, rootScope)[0]) : null;

                    // Rolar painel para disparar lazy loading e carregar todas as disciplinas da aba
                    if (panel) {
                        panel.scrollTop = panel.scrollHeight;
                        await new Promise(r => setTimeout(r, 900));
                    } else if (rootScope) {
                        rootScope.scrollTop = rootScope.scrollHeight;
                        await new Promise(r => setTimeout(r, 900));
                    }

                    const containerBusca = panel || rootScope;
                    const cards = querySelectorAllDeep('d2l-card, d2l-enrollment-card', containerBusca);
                    const turmasAba = [];
                    const seenAba = new Set();

                    for (const c of cards) {
                        const textAttr = c.getAttribute('text') || '';
                        const innerText = c.innerText || '';
                        const txt = (textAttr || innerText).trim();
                        const linhas = txt.split('\n').map(l => l.trim()).filter(Boolean);
                        const nome = linhas.length > 0 ? linhas[0] : '';

                        let href = c.getAttribute('href') || '';
                        if (!href) {
                            const a = c.querySelector('a[href*="/d2l/home/"]') || (c.shadowRoot ? c.shadowRoot.querySelector('a[href*="/d2l/home/"]') : null);
                            if (a) href = a.getAttribute('href') || a.href || '';
                        }

                        const m = href.match(/\/d2l\/home\/(\d+)/);
                        if (!m) continue;
                        const ou = m[1];

                        if (ousIgnorar.includes(ou) || seenAba.has(ou)) continue;

                        // Descarte de salas não acadêmicas
                        if (descartar.some(d => nome.toLowerCase().includes(d))) continue;

                        // Filtro estrito na aba Fixado: apenas cards realmente fixados
                        if (item.isFixado) {
                            let isPinned = false;
                            if (c.hasAttribute('pinned') && c.getAttribute('pinned') !== 'false') isPinned = true;
                            const pinButtons = querySelectorAllDeep('d2l-button-icon, [aria-label*="fixar"], [aria-label*="Fixar"], [title*="fixar"], [title*="Fixar"]', c);
                            for (const pb of pinButtons) {
                                const l = (pb.getAttribute('aria-label') || pb.getAttribute('text') || pb.getAttribute('icon') || '').toLowerCase();
                                if (l.includes('desafixar') || l.includes('unpin') || l.includes('remover dos fixados') || l.includes('pin-filled')) {
                                    isPinned = true;
                                    break;
                                }
                            }
                            if (!isPinned) continue;
                        }

                        seenAba.add(ou);
                        const itemCurso = { ou, name: nome || `Disciplina ${ou}` };
                        turmasAba.push(itemCurso);

                        if (!seenGeral.has(ou)) {
                            seenGeral.add(ou);
                            todosCursosConsolidados.push(itemCurso);
                        }
                    }

                    disciplinasPorAba[item.nome] = turmasAba;
                }

                // Montar lista de abas para o frontend
                const nomesAbas = abasProcessar.map(a => a.nome === 'Todos' ? 'Todas as Disciplinas' : a.nome);
                disciplinasPorAba['Todas as Disciplinas'] = todosCursosConsolidados;
                if (!nomesAbas.includes('Todas as Disciplinas')) {
                    nomesAbas.push('Todas as Disciplinas');
                }

                return {
                    abas: Array.from(new Set(nomesAbas)),
                    disciplinas_por_aba: disciplinasPorAba
                };
            }""")

            if dados_descoberta and "abas" in dados_descoberta:
                resultado = dados_descoberta

        except Exception as e:
            state.log(f"Erro na descoberta de cursos: {e}", "ERROR")
        finally:
            browser.close()

    return resultado
