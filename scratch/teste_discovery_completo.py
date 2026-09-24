import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
import time
import re
import json
from playwright.sync_api import sync_playwright
from config import BASE_AVA_URL

auth_file = "auth_state_04083941.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(storage_state=auth_file, viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.goto(f"{BASE_AVA_URL}/d2l/home", wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)

    # Executar a nova lógica de descoberta completa
    resultado = page.evaluate("""async () => {
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

        // 1. Tentar abrir o diálogo 'Exibir Todos os Cursos' para visão completa
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
        // - Períodos no formato \d{4}/\d+ (ex: 2026/1, 2026/2, 2026/3, etc)
        // - "Todos" (id inclui search-my-enrollments ou title inclui Todos)
        const periodosEncontrados = [];
        let tabFixado = null;
        let tabTodos = null;

        const regexPeriodo = /^\\d{4}\\/\\d+$/;

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

        // Lista final de abas
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

        // 3. Iterar por cada aba e extrair disciplinas
        for (const item of abasProcessar) {
            const tabEl = item.aba.element;
            
            // Clicar na aba
            if (tabEl) {
                // Se não estiver usando dialog, pode ser necessário rolar as abas
                if (!usandoDialog) {
                    const d2lTabs = document.querySelector('d2l-tabs');
                    if (d2lTabs && d2lTabs.shadowRoot) {
                        const nextBtn = d2lTabs.shadowRoot.querySelector('button[title*="frente"]');
                        if (nextBtn && !nextBtn.disabled) nextBtn.click();
                    }
                }

                tabEl.click();
                await new Promise(r => setTimeout(r, 1800));
            }

            // Encontrar o container ou painel correspondente
            const panelId = item.aba.controlsId;
            const panel = panelId ? (document.getElementById(panelId) || querySelectorAllDeep('#' + panelId, rootScope)[0]) : null;

            // Rolar painel para carregar lazy loading
            if (panel) {
                panel.scrollTop = panel.scrollHeight;
                await new Promise(r => setTimeout(r, 800));
            } else if (rootScope) {
                rootScope.scrollTop = rootScope.scrollHeight;
                await new Promise(r => setTimeout(r, 800));
            }

            const containerBusca = panel || rootScope;
            const cards = querySelectorAllDeep('d2l-card, d2l-enrollment-card', containerBusca);
            const turmasAba = [];
            const seenAba = new Set();

            for (const c of cards) {
                const textAttr = c.getAttribute('text') || '';
                const innerText = c.innerText || '';
                const txt = (textAttr || innerText).trim();
                const linhas = txt.split('\\n').map(l => l.trim()).filter(Boolean);
                const nome = linhas.length > 0 ? linhas[0] : '';

                // Link e OU
                let href = c.getAttribute('href') || '';
                if (!href) {
                    const a = c.querySelector('a[href*="/d2l/home/"]') || (c.shadowRoot ? c.shadowRoot.querySelector('a[href*="/d2l/home/"]') : null);
                    if (a) href = a.getAttribute('href') || a.href || '';
                }

                const m = href.match(/\\/d2l\\/home\\/(\\d+)/);
                if (!m) continue;
                const ou = m[1];

                if (ousIgnorar.includes(ou) || seenAba.has(ou)) continue;

                // Checagem de descarte
                if (descartar.some(d => nome.toLowerCase().includes(d))) continue;

                // Verificação estrita se estiver na aba Fixado
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
                    if (!isPinned) continue; // Pular cards não fixados na aba Fixado
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

        // Consolidação em 'Todas as Disciplinas'
        disciplinasPorAba['Todas as Disciplinas'] = todosCursosConsolidados;
        const nomesAbas = abasProcessar.map(a => a.nome === 'Todos' ? 'Todas as Disciplinas' : a.nome);
        if (!nomesAbas.includes('Todas as Disciplinas')) {
            nomesAbas.push('Todas as Disciplinas');
        }

        return {
            usandoDialog,
            totalPeriodos: periodosEncontrados.length,
            periodos: periodosEncontrados.map(p => p.title),
            abas: Array.from(new Set(nomesAbas)),
            disciplinas_por_aba: disciplinasPorAba,
            totalDisciplinasUnicas: todosCursosConsolidados.length
        };
    }""")

    print(f"Usando Dialog: {resultado.get('usandoDialog')}")
    print(f"Total Períodos Encontrados: {resultado.get('totalPeriodos')}")
    print(f"Períodos: {resultado.get('periodos')}")
    print(f"Abas Finais: {resultado.get('abas')}")
    print(f"Total Disciplinas Únicas: {resultado.get('totalDisciplinasUnicas')}")
    print("\nContagem por aba:")
    for aba, lista in resultado.get("disciplinas_por_aba", {}).items():
        print(f"  Aba '{aba}': {len(lista)} disciplinas")

    browser.close()
