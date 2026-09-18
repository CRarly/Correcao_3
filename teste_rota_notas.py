import sys
import time
import re
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(r"c:\Users\Arly\.gemini\antigravity\scratch\brightspace-grader-v2")
sys.path.insert(0, str(BASE_DIR))
auth_file = BASE_DIR / "auth_state_04083941.json"
ou = "155377"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        storage_state=str(auth_file) if auth_file.exists() else None,
        viewport={"width": 1400, "height": 900}
    )
    page = context.new_page()

    url_notas = f"https://ava.catolica.edu.br/d2l/lms/grades/admin/enter/user_list_view.d2l?ou={ou}"
    print(f"Acessando: {url_notas}")
    page.goto(url_notas, wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)

    # 1. Inspecionar todos os cabeçalhos de tabela com texto e innerHTML
    headers_info = page.evaluate(r"""() => {
        const ths = Array.from(document.querySelectorAll('th, td.d_gh, .d2l-grid-header, th.d_gl'));
        return ths.map((th, i) => ({
            index: i,
            text: (th.innerText || '').trim().replace(/\s+/g, ' '),
            html: th.innerHTML.slice(0, 300)
        })).filter(h => h.text.length > 2);
    }""")

    print(f"\nCabeçalhos da Grade ({len(headers_info)}):")
    for h in headers_info:
        print(f"  [{h['index']}] {h['text']}")

    # 2. Inspecionar especificamente os links e ícones da coluna do Fórum e da Atividade
    detalhes_icones = page.evaluate(r"""() => {
        function norm(s) {
            return (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, "").toLowerCase();
        }

        const table = document.querySelector('table.d_g, table');
        if (!table) return { erro: 'Sem tabela' };

        const rows = Array.from(table.querySelectorAll('tr'));
        const headerRow = rows[0];
        const headers = Array.from(headerRow.children).map((c, i) => ({
            idx: i,
            text: (c.innerText || '').trim(),
            normText: norm(c.innerText)
        }));

        const fHeader = headers.find(h => h.normText.includes('forum'));
        const aHeader = headers.find(h => h.normText.includes('atividade avaliativa') || h.normText.includes('atividade aberta'));

        const samples = [];
        for (let r of rows.slice(1)) {
            const cells = Array.from(r.children);
            const nome = (cells[1] ? cells[1].innerText : '').trim().replace(/\s+/g, ' ');
            if (!nome) continue;

            const fCell = fHeader && cells[fHeader.idx] ? cells[fHeader.idx] : null;
            const aCell = aHeader && cells[aHeader.idx] ? cells[aHeader.idx] : null;

            function extractCell(cell) {
                if (!cell) return null;
                const links = Array.from(cell.querySelectorAll('a, button, img'));
                const iconInfo = links.map(el => ({
                    tag: el.tagName,
                    title: el.getAttribute('title') || el.getAttribute('aria-label') || el.alt || '',
                    href: el.href || el.getAttribute('href') || '',
                    onclick: el.getAttribute('onclick') || '',
                    className: el.className || '',
                    outerHTML: el.outerHTML.slice(0, 200)
                }));
                const inputVal = cell.querySelector('input') ? cell.querySelector('input').value : '';
                return {
                    text: (cell.innerText || '').trim().replace(/\s+/g, ' '),
                    inputVal: inputVal,
                    icons: iconInfo
                };
            }

            samples.push({
                aluno: nome,
                forum: extractCell(fCell),
                atividade: extractCell(aCell)
            });
        }

        return {
            fHeader: fHeader ? fHeader.text : null,
            fIndex: fHeader ? fHeader.idx : null,
            aHeader: aHeader ? aHeader.text : null,
            aIndex: aHeader ? aHeader.idx : null,
            totalRows: samples.length,
            samples: samples
        };
    }""")

    print(f"\nColuna Fórum: {detalhes_icones.get('fHeader')} (Índice: {detalhes_icones.get('fIndex')})")
    print(f"Coluna Atividade: {detalhes_icones.get('aHeader')} (Índice: {detalhes_icones.get('aIndex')})")
    print(f"Total de Alunos Analisados: {detalhes_icones.get('totalRows')}")

    samples = detalhes_icones.get('samples', [])
    forum_com_icone = [s for s in samples if s['forum'] and any(len(ic['title']) > 0 or 'discussion' in ic['onclick'] or 'forum' in ic['href'] or ic['tag'] == 'IMG' for ic in s['forum']['icons'])]
    ativ_com_icone = [s for s in samples if s['atividade'] and any('envio' in ic['title'].lower() or 'submiss' in ic['title'].lower() or 'dropbox' in ic['onclick'] or ic['tag'] == 'IMG' for ic in s['atividade']['icons'])]

    print(f"\nContagem de Envios Reais:")
    print(f"  - Fórum com ícone/submissão: {len(forum_com_icone)} de {len(samples)}")
    print(f"  - Atividade com ícone/submissão: {len(ativ_com_icone)} de {len(samples)}")

    print("\nPrimeiros 3 alunos com envio no Fórum:")
    for s in forum_com_icone[:3]:
        print(f"  * {s['aluno']}")
        for ic in s['forum']['icons']:
            print(f"      Icon: {ic['title']} | onClick: {ic['onclick'][:60]} | Href: {ic['href'][:60]}")

    print("\nPrimeiros 3 alunos com envio na Atividade:")
    for s in ativ_com_icone[:3]:
        print(f"  * {s['aluno']}")
        for ic in s['atividade']['icons']:
            print(f"      Icon: {ic['title']} | onClick: {ic['onclick'][:60]} | Href: {ic['href'][:60]}")

    # 3. Testar a abertura do Consistent Evaluation clicando no ícone do primeiro aluno
    if ativ_com_icone:
        primeiro = ativ_com_icone[0]
        print(f"\n[TESTE DE CLIQUE] Clicando no ícone de envio da Atividade de: {primeiro['aluno']}")
        
        # Inspecionar o que o onclick faz ou capturar nova página/modal
        aluno_nome_curto = primeiro['aluno'].split(',')[0].strip()
        seletor = f"tr:has-text('{aluno_nome_curto}') a:has(img), tr:has-text('{aluno_nome_curto}') a[title*='Exibir envios'], tr:has-text('{aluno_nome_curto}') a[title*='envio']"
        target = page.locator(seletor).first
        if target.count() > 0:
            print("  Elemento encontrado na página. Verificando se abre popup...")
            try:
                # O Brightspace pode abrir em popup ou na mesma aba
                with context.expect_page(timeout=6000) as p_info:
                    target.click()
                nova_pagina = p_info.value
                nova_pagina.wait_for_load_state("domcontentloaded")
                time.sleep(4)
                print(f"  >>> SUCESSO: Nova janela aberta!")
                print(f"      URL: {nova_pagina.url}")
                print(f"      Título: {nova_pagina.title()}")

                from core.navigation_iterator import extrair_posicao_mostrador_iterator, extrair_nome_estudante_atual
                pos = extrair_posicao_mostrador_iterator(nova_pagina)
                aluno_ce = extrair_nome_estudante_atual(nova_pagina)
                print(f"      Posição Mostrador: {pos}")
                print(f"      Aluno no CE: {aluno_ce}")

                nova_pagina.close()
            except Exception as e:
                print(f"  Não abriu nova janela ({e}). Verificando página atual...")
                time.sleep(3)
                print(f"      URL Atual: {page.url}")
                print(f"      Título Atual: {page.title()}")

    browser.close()

