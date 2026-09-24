import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
import time
import json
from playwright.sync_api import sync_playwright
from config import BASE_AVA_URL

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(storage_state='auth_state_04084531.json', viewport={'width': 1280, 'height': 900})
    page = ctx.new_page()
    page.goto(f'{BASE_AVA_URL}/d2l/home', wait_until='domcontentloaded', timeout=60000)
    time.sleep(4)

    # 1. Abrir Exibir Todos os Cursos
    page.evaluate("""() => {
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

        const links = querySelectorAllDeep('#viewAllCourses, d2l-link');
        const link = links.find(l => (l.innerText || '').includes('Exibir Todos') || (l.id === 'viewAllCourses'));
        if (link) link.click();
    }""")
    time.sleep(3)

    # 2. Testar aba Fixado e aba 2026/1 dentro do dialog
    res = page.evaluate("""async () => {
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

        const openedDialog = querySelectorAllDeep('d2l-dialog-fullscreen').find(d => d.hasAttribute('opened'));
        if (!openedDialog) return { error: "Dialog não aberto" };

        const tabs = querySelectorAllDeep('d2l-tab', openedDialog);
        
        async function clicarAbaEExtrair(tabId, nomeAba) {
            const tab = tabs.find(t => t.id === tabId || (t.innerText || t.getAttribute('title') || '').includes(nomeAba));
            if (!tab) return { erro: `Aba ${nomeAba} não encontrada` };
            tab.click();
            await new Promise(r => setTimeout(r, 2000));

            // Rolar painel para o final para garantir carregamento de todos os itens (lazy load)
            const panelId = tab.getAttribute('aria-controls');
            const panel = panelId ? querySelectorAllDeep('#' + panelId, openedDialog)[0] : null;
            
            if (panel) {
                panel.scrollTop = panel.scrollHeight;
                await new Promise(r => setTimeout(r, 1000));
            }

            // Cards visíveis no painel
            const containerBusca = panel || openedDialog;
            const cards = querySelectorAllDeep('d2l-enrollment-card, d2l-card', containerBusca);
            
            const turmas = [];
            cards.forEach(c => {
                const text = (c.getAttribute('text') || c.innerText || '').trim();
                const href = c.getAttribute('href') || (c.querySelector('a') ? c.querySelector('a').href : '');
                
                // Verificar se está fixado
                let isPinned = false;
                if (c.hasAttribute('pinned') && c.getAttribute('pinned') !== 'false') isPinned = true;
                const pinBtn = querySelectorAllDeep('d2l-button-icon, [aria-label*="fixar"], [aria-label*="Fixar"], [title*="fixar"], [title*="Fixar"]', c);
                pinBtn.forEach(pb => {
                    const l = (pb.getAttribute('aria-label') || pb.getAttribute('text') || pb.getAttribute('icon') || '').toLowerCase();
                    if (l.includes('desafixar') || l.includes('unpin') || l.includes('remover dos fixados') || l.includes('tier1:pin-filled') || l.includes('pin-filled')) {
                        isPinned = true;
                    }
                });

                if (href) {
                    turmas.push({ text: text.split('\\n')[0], href, isPinned });
                }
            });

            return {
                tabId: tab.id,
                nome: tab.innerText || tab.getAttribute('title'),
                totalCards: cards.length,
                turmas: turmas.slice(0, 10)
            };
        }

        const fixados = await clicarAbaEExtrair('all-courses-tab-search-my-pinned-enrollments', 'Fixado');
        const sem2026_1 = await clicarAbaEExtrair('all-courses-tab-BySemester132035', '2026/1');
        const todos = await clicarAbaEExtrair('all-courses-tab-search-my-enrollments', 'Todos');

        return { fixados, sem2026_1, todos };
    }""")

    print(json.dumps(res, indent=2, ensure_ascii=False))
    browser.close()

