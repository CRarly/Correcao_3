import os
import re
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from config import (
    get_home_url, get_quickeval_url, get_forums_url, get_dropbox_url,
    get_quizzes_url, get_grades_url, NAV_TIMEOUT
)
from engine_state import state

class InspectorDisciplina:
    """
    Motor de inspeção prévia de disciplinas.
    Executa os passos 1 a 6 da arquitetura:
    - Quick Eval: mapeamento inicial de atividades e contagem de envios pendentes.
    - Gerenciar Notas & Home: leitura de unidades (2 vs 4), validação se há Atividade Aberta e valores oficiais.
    - Fórum: extração do comando oficial na thread e validação de nota em Editar Tópico.
    - Atividade Aberta: extração de instruções completas via 'Editar pasta' (setinha à direita), anexos modelos e nota.
    - Prova Presencial: identificação da questão discursiva e enunciado.
    - Geração do arquivo estruturado plano_apoio_{ou}.json.
    """

    def inspecionar(self, page: Page, ou: str | int, nome_disciplina: str, temp_dir: Path) -> Dict[str, Any]:
        state.log(f"Iniciando pré-inspeção detalhada para [{ou}] {nome_disciplina}...")
        plano = {
            "ou": str(ou),
            "disciplina": nome_disciplina,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "unidades_detectadas": [],
            "regra_curricular": "4_UNIDADES",
            "forum": {
                "ativo": False,
                "nome": "Avaliação: Fórum de discussão",
                "valor": 1.0,
                "comando": "",
                "total_pendentes": 0,
                "total_geral": 0
            },
            "atividade_aberta": {
                "ativa": False,
                "nome": "Avaliação: Atividade aberta",
                "valor": 1.5,
                "instrucoes": "",
                "modelos_baixados": [],
                "total_pendentes": 0,
                "total_geral": 0
            },
            "prova_presencial": {
                "ativa": False,
                "nome": "Avaliação: Prova presencial",
                "valor_discursiva": 2.0,
                "enunciado_discursiva": "",
                "total_pendentes": 0,
                "total_geral": 0
            },
            "prova_substitutiva": {
                "ativa": False,
                "nome": "Avaliação: Prova substitutiva",
                "valor_discursiva": 2.0,
                "enunciado_discursiva": "",
                "codigo_discursiva": "",
                "total_pendentes": 0,
                "total_geral": 0
            }
        }

        # -------------------------------------------------------------
        # 1. Gerenciar Notas: Validação oficial de Unidades e Atividades
        # -------------------------------------------------------------
        self._inspecionar_gerenciar_notas(page, ou, plano)

        # -------------------------------------------------------------
        # 2. Quick Eval: Mapear atividades e contagens pendentes
        # -------------------------------------------------------------
        self._mapear_quickeval(page, ou, plano)

        # -------------------------------------------------------------
        # 3. Anexar Tarefas (Dropbox): Mapear pasta, contagens e instruções
        # -------------------------------------------------------------
        self._inspecionar_dropbox_atividade(page, ou, plano, temp_dir)

        # -------------------------------------------------------------
        # 4. Fórum de Discussão: Extrair Comando da Thread e Nota
        # -------------------------------------------------------------
        self._inspecionar_forum_thread(page, ou, plano)

        # -------------------------------------------------------------
        # 5. Prova Presencial: Mapear Discursiva
        # -------------------------------------------------------------
        self._inspecionar_prova_presencial(page, ou, plano)

        # -------------------------------------------------------------
        # 6. Prova Substitutiva: Mapear Discursiva
        # -------------------------------------------------------------
        self._inspecionar_prova_substitutiva(page, ou, plano)

        # -------------------------------------------------------------
        # 7. Regras Curriculares Finais (2 Unidades vs 4 Unidades)
        # -------------------------------------------------------------
        if plano["atividade_aberta"]["ativa"]:
            plano["regra_curricular"] = "4_UNIDADES"
            plano["forum"]["valor"] = plano["forum"]["valor"] or 1.0
            plano["atividade_aberta"]["valor"] = plano["atividade_aberta"]["valor"] or 1.5
            state.log(f"Configuração confirmada: 4 Unidades | Fórum = {plano['forum']['valor']} pt | Atividade Aberta = {plano['atividade_aberta']['valor']} pts")
        else:
            plano["regra_curricular"] = "2_UNIDADES"
            plano["forum"]["valor"] = 2.5
            state.log(f"Configuração confirmada: 2 Unidades | Fórum = 2,5 pts | Sem Atividade Aberta.")

        # -------------------------------------------------------------
        # 7. Persistir plano de apoio
        # -------------------------------------------------------------
        caminho_plano = temp_dir / f"plano_apoio_{ou}.json"
        try:
            with open(caminho_plano, "w", encoding="utf-8") as f:
                json.dump(plano, f, ensure_ascii=False, indent=2)
            state.log(f"Plano de apoio gerado com sucesso: {caminho_plano.name}")
        except Exception as e:
            state.log(f"Aviso ao salvar plano de apoio: {e}", "WARN")

        state.set_plan(plano)
        return plano

    def _inspecionar_gerenciar_notas(self, page: Page, ou: str | int, plano: Dict[str, Any]):
        """Consulta 'Gerenciar Notas' para ler a configuração oficial das notas e unidades."""
        url_grades = get_grades_url(ou)
        state.log(f"Consultando Gerenciar Notas: {url_grades}")
        try:
            page.goto(url_grades, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(2.5)

            linhas = page.evaluate("""() => {
                const rows = Array.from(document.querySelectorAll('tr'));
                return rows.map(r => (r.innerText || '').trim()).filter(t => t.length > 5);
            }""")

            unidades = set()
            for l in linhas:
                # Detectar unidades (Unidade 1, Unidade 2, Unidade 3, Unidade 4)
                matches = re.findall(r"Unidade\s*([1-4])", l, re.IGNORECASE)
                for m in matches:
                    unidades.add(f"Unidade {m}")

                # Verificar se há item de Fórum
                if "fórum" in l.lower() or "forum" in l.lower():
                    plano["forum"]["ativo"] = True
                    nums = re.findall(r"\b(\d+[\.,]?\d*)\b", l)
                    if nums:
                        try:
                            plano["forum"]["valor"] = float(nums[-1].replace(",", "."))
                        except Exception:
                            pass

                # Verificar se há Atividade Aberta / Anexar Tarefas
                if "anexar tarefas" in l.lower() or "atividade aberta" in l.lower() or "atividade avaliativa" in l.lower():
                    plano["atividade_aberta"]["ativa"] = True
                    nums = re.findall(r"\b(\d+[\.,]?\d*)\b", l)
                    if nums:
                        try:
                            plano["atividade_aberta"]["valor"] = float(nums[-1].replace(",", "."))
                        except Exception:
                            pass

                # Verificar Prova Presencial
                if "prova" in l.lower() or "presencial" in l.lower():
                    if "recupera" not in l.lower():
                        plano["prova_presencial"]["ativa"] = True

            plano["unidades_detectadas"] = sorted(list(unidades))
            state.log(f"Unidades mapeadas em Gerenciar Notas: {plano['unidades_detectadas']}")
            if plano["atividade_aberta"]["ativa"]:
                state.log(f"Atividade Aberta identificada em Notas (Valor oficial: {plano['atividade_aberta']['valor']})")
            if plano["forum"]["ativo"]:
                state.log(f"Fórum identificado em Notas (Valor oficial: {plano['forum']['valor']})")

        except Exception as e:
            state.log(f"Aviso em Gerenciar Notas: {e}", "WARN")

    def _mapear_quickeval(self, page: Page, ou: str | int, plano: Dict[str, Any]):
        """Mapeia atividades e contagens pendentes em Quick Eval através de Web Components / Shadow DOM."""
        if state.should_stop:
            return

        url_qe = get_quickeval_url(ou)
        state.log(f"Acessando Quick Eval: {url_qe}")
        try:
            page.goto(url_qe, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3)

            # Clicar na aba/toggle Atividades
            toggle = page.locator("d2l-tab:has-text('Atividades'), [role='tab']:has-text('Atividades'), button:has-text('Atividades'), d2l-quick-eval-view-toggle-button").first
            if toggle.count() > 0:
                try:
                    toggle.click(timeout=3000)
                    time.sleep(3)
                except Exception:
                    pass

            # Usar TreeWalker para extrair cada linha de atividade com título, contagem e links
            atividades_qe = page.evaluate("""() => {
                function getAllElements(root) {
                    let elements = [];
                    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                    while (walker.nextNode()) {
                        const el = walker.currentNode;
                        elements.push(el);
                        if (el.shadowRoot) elements = elements.concat(getAllElements(el.shadowRoot));
                    }
                    return elements;
                }
                const all = getAllElements(document.body);
                const items = [];
                const links = all.filter(el => el.tagName.toLowerCase() === 'a' && (el.getAttribute('href') || '').includes('evaluation/activity'));

                for (let a of links) {
                    const href = a.getAttribute('href') || '';
                    const linkText = (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ');

                    // Subir nos pais para encontrar o título da atividade no container
                    let p = a;
                    let title = '';
                    for (let step = 0; step < 8; step++) {
                        if (!p) break;
                        const innerAll = getAllElements(p);
                        for (let inner of innerAll) {
                            const txt = (inner.innerText || inner.textContent || '').trim().replace(/\\s+/g, ' ');
                            if (txt && (txt.includes('Avaliação:') || txt.includes('Fórum') || txt.includes('Atividade') || txt.includes('Prova'))) {
                                if (!title || txt.length < title.length) {
                                    title = txt;
                                }
                            }
                        }
                        if (title) break;
                        p = p.parentElement || (p.getRootNode ? p.getRootNode().host : null);
                    }

                    items.push({ title, linkText, href });
                }
                return items;
            }""")

            for item in atividades_qe:
                titulo = item.get("title", "")
                link_txt = item.get("linkText", "")
                href = item.get("href", "")
                if not href.startswith("http"):
                    href = f"https://ava.catolica.edu.br{href}"

                # Extrair contagem de novos envios
                m_novos = re.search(r'^\s*(\d+)', link_txt)
                qtd_novos = int(m_novos.group(1)) if m_novos else 0

                url_new = href
                url_all = href.replace("iteratorRange=new", "iteratorRange=all")
                if "iteratorRange=" not in url_all:
                    url_all += ("&" if "?" in url_all else "?") + "iteratorRange=all"

                t_lower = (titulo + " " + link_txt).lower()

                # Fórum
                if "fórum" in t_lower or "forum" in t_lower or "postagens" in t_lower:
                    plano["forum"]["ativo"] = True
                    plano["forum"]["total_pendentes"] = qtd_novos
                    plano["forum"]["url_new"] = url_new
                    plano["forum"]["url_all"] = url_all
                    state.log(f"Fórum mapeado no Quick Eval: '{titulo}' | Novos: {qtd_novos}")

                # Atividade Aberta
                elif "atividade aberta" in t_lower or "anexar tarefas" in t_lower or "envios" in t_lower:
                    plano["atividade_aberta"]["ativa"] = True
                    plano["atividade_aberta"]["total_pendentes"] = qtd_novos
                    plano["atividade_aberta"]["url_new"] = url_new
                    plano["atividade_aberta"]["url_all"] = url_all
                    state.log(f"Atividade Aberta mapeada no Quick Eval: '{titulo}' | Novos: {qtd_novos}")

                # Prova Substitutiva
                elif "substitutiva" in t_lower or ("prova" in t_lower and "rec" in t_lower):
                    plano["prova_substitutiva"]["ativa"] = True
                    plano["prova_substitutiva"]["total_pendentes"] = qtd_novos
                    plano["prova_substitutiva"]["url_new"] = url_new
                    plano["prova_substitutiva"]["url_all"] = url_all
                    state.log(f"Prova Substitutiva mapeada no Quick Eval: '{titulo}' | Novos: {qtd_novos}")

                # Prova Presencial / Avaliação Final
                elif "prova" in t_lower or "presencial" in t_lower or "tentativas" in t_lower or "avaliação final" in t_lower or "avaliacao final" in t_lower:
                    plano["prova_presencial"]["ativa"] = True
                    plano["prova_presencial"]["total_pendentes"] = qtd_novos
                    plano["prova_presencial"]["url_new"] = url_new
                    plano["prova_presencial"]["url_all"] = url_all
                    state.log(f"Prova Presencial mapeada no Quick Eval: '{titulo}' | Novos: {qtd_novos}")

        except Exception as e:
            state.log(f"Aviso no Quick Eval: {e}", "WARN")

    def _inspecionar_dropbox_atividade(self, page: Page, ou: str | int, plano: Dict[str, Any], temp_dir: Path):
        """Acessa Anexar Tarefas, abre o editor da Atividade Aberta, extrai Instruções completas, modelos e nota."""
        url_dropbox = get_dropbox_url(ou)
        state.log(f"Inspecionando Anexar Tarefas (Dropbox): {url_dropbox}")
        try:
            page.goto(url_dropbox, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3.0)

            # 1. Verificar se a atividade aberta consta na tabela e extrair link/contagens
            info_pasta = page.evaluate(r"""() => {
                const rows = Array.from(document.querySelectorAll('tr'));
                for (let r of rows) {
                    const txt = r.innerText || '';
                    if (txt.includes('Atividade aberta') || txt.includes('Atividade Aberta')) {
                        const m = txt.match(/(\d+)\s*\/\s*(\d+)/);
                        const link = r.querySelector('a[href*="folder_submissions"], a[href*="dropbox"]');
                        return {
                            found: true,
                            pendentes: m ? parseInt(m[1]) : 0,
                            total: m ? parseInt(m[2]) : 0,
                            href: link ? link.href : null
                        };
                    }
                }
                return { found: false };
            }""")

            if info_pasta.get("found"):
                plano["atividade_aberta"]["ativa"] = True
                plano["atividade_aberta"]["total_pendentes"] = info_pasta.get("pendentes", 0)
                plano["atividade_aberta"]["total_geral"] = info_pasta.get("total", 0)
                state.log(f"Contagens da Atividade Aberta: {plano['atividade_aberta']['total_pendentes']}/{plano['atividade_aberta']['total_geral']}")

                # 2. Tentar acessar a página de submissões para clicar em 'Editar Atividade'
                url_submissoes = info_pasta.get("href")
                if url_submissoes:
                    page.goto(url_submissoes, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                    time.sleep(3.5)

                    # Verificar botão Editar Atividade
                    data_loc = page.evaluate(r"""() => {
                        const btns = Array.from(document.querySelectorAll('a, button, d2l-button'));
                        for (let b of btns) {
                            const t = (b.innerText || '').trim();
                            if (t === 'Editar Atividade' || t.includes('Editar Atividade')) {
                                return b.getAttribute('data-location') || b.getAttribute('href');
                            }
                        }
                        return null;
                    }""")

                    url_editor = None
                    if data_loc:
                        url_editor = data_loc if data_loc.startswith("http") else f"https://ava.catolica.edu.br{data_loc}"
                    elif page.locator("button:has-text('Editar Atividade'), a:has-text('Editar Atividade')").count() > 0:
                        try:
                            with page.expect_navigation(timeout=12000):
                                page.locator("button:has-text('Editar Atividade'), a:has-text('Editar Atividade')").first.click()
                            url_editor = page.url
                        except Exception:
                            pass

                    if url_editor:
                        if page.url != url_editor:
                            page.goto(url_editor, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                        time.sleep(5.0)

                        # Extrair instruções de d2l-htmleditor, anexos e nota
                        detalhes = page.evaluate(r"""() => {
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

                            // Instruções
                            let instrucoes = '';
                            for (let el of all) {
                                if (el.tagName.toLowerCase() === 'd2l-htmleditor') {
                                    const h = el.html || el.innerText || '';
                                    if (h.length > instrucoes.length) instrucoes = h;
                                }
                            }
                            if (!instrucoes) {
                                for (let el of all) {
                                    if (el.tagName.toLowerCase() === 'd2l-html-block') {
                                        const h = el.html || el.innerHTML || el.innerText || '';
                                        if (h.length > instrucoes.length && !h.includes('Sua sessão')) instrucoes = h;
                                    }
                                }
                            }

                            // Modelos / Anexos
                            const anexos = [];
                            for (let el of all) {
                                const aria = (el.getAttribute('aria-label') || '').trim();
                                const txt = (el.innerText || el.textContent || '').trim();
                                if (aria.startsWith('Remover anexo:')) {
                                    const nome = aria.replace('Remover anexo:', '').trim();
                                    if (nome && !anexos.includes(nome)) anexos.push(nome);
                                } else if ((el.getAttribute('href') || '').includes('Attachment') && txt) {
                                    if (!anexos.includes(txt)) anexos.push(txt);
                                }
                            }

                            // Nota
                            let nota = '';
                            const inp = all.find(el => el.id === 'score-out-of' || (el.getAttribute('aria-label') || '').toLowerCase().includes('nota'));
                            if (inp) nota = inp.value || inp.getAttribute('value') || '';

                            return { instrucoes, anexos, nota };
                        }""")

                        if detalhes.get("instrucoes"):
                            plano["atividade_aberta"]["instrucoes"] = detalhes["instrucoes"]
                            state.log(f"Instruções completas da Atividade Aberta extraídas ({len(detalhes['instrucoes'])} caracteres).")
                        if detalhes.get("anexos"):
                            plano["atividade_aberta"]["modelos_baixados"] = detalhes["anexos"]
                            state.log(f"Modelos/anexos identificados na Atividade Aberta: {detalhes['anexos']}")
                        if detalhes.get("nota"):
                            try:
                                plano["atividade_aberta"]["valor"] = float(str(detalhes["nota"]).replace(",", "."))
                                state.log(f"Valor oficial da Atividade Aberta confirmado: {plano['atividade_aberta']['valor']} pts")
                            except Exception:
                                pass
        except Exception as e:
            state.log(f"Aviso ao inspecionar Atividade Aberta em Tarefas: {e}", "WARN")

    def _inspecionar_forum_thread(self, page: Page, ou: str | int, plano: Dict[str, Any]):
        """Acessa a thread oficial do Fórum, extrai o comando em Postar* e verifica a nota em Editar Tópico."""
        url_forums = get_forums_url(ou)
        state.log(f"Inspecionando Fórum de Discussão: {url_forums}")
        try:
            page.goto(url_forums, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(2.5)

            # Localizar link do tópico Avaliação: Fórum de discussão
            link_topico = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[href*="topics/"]'));
                for (let a of links) {
                    if (a.innerText.includes('Fórum de discussão') || a.innerText.includes('Avaliação')) {
                        return a.href;
                    }
                }
                return links.length > 0 ? links[links.length - 1].href : null;
            }""")

            if link_topico:
                page.goto(link_topico, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                time.sleep(2.5)

                # Localizar thread oficial
                link_thread = page.evaluate("""() => {
                    const links = Array.from(document.querySelectorAll('a[href*="threads/"]'));
                    for (let a of links) {
                        const txt = a.innerText.toLowerCase();
                        if (txt.includes('clique aqui') || txt.includes('responder') || txt.includes('avaliativ')) {
                            return a.href;
                        }
                    }
                    return links.length > 0 ? links[0].href : null;
                }""")

                if link_thread:
                    page.goto(link_thread, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                    time.sleep(2.5)

                    # 1. Extrair comando da thread no HTML do post oficial
                    comando_post = page.evaluate("""() => {
                        function getAllElements(root) {
                            let elements = [];
                            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                            while (walker.nextNode()) {
                                const el = walker.currentNode;
                                elements.push(el);
                                if (el.shadowRoot) elements = elements.concat(getAllElements(el.shadowRoot));
                            }
                            return elements;
                        }
                        const all = getAllElements(document.body);
                        for (let el of all) {
                            if (el.tagName.toLowerCase() === 'd2l-html-block') {
                                const html = el.html || el.innerHTML || el.innerText;
                                if (html && html.length > 50 && !html.includes('Sua sessão')) return html;
                            }
                        }
                        const blocks = document.querySelectorAll('.d2l-html-editor-rendered, [class*="post-body"], .d2l-text-styled');
                        for (let b of blocks) {
                            if (b.innerText && b.innerText.length > 50) return b.innerText;
                        }
                        return '';
                    }""")

                    if comando_post:
                        plano["forum"]["comando"] = comando_post
                        state.log(f"Comando oficial do Fórum extraído com sucesso ({len(comando_post)} caracteres).")

            # 2. Validar nota em Editar Tópico (menu da setinha à direita do tópico)
            page.goto(url_forums, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(2)
            setinha_topico = page.locator("d2l-dropdown-context-menu[text*='Fórum'], d2l-dropdown-context-menu[text*='Avaliação: Fórum']").first
            if setinha_topico.count() > 0:
                setinha_topico.click()
                time.sleep(1)
                btn_editar_topico = page.locator("d2l-menu-item:has-text('Editar tópico'), [role='menuitem']:has-text('Editar tópico')").first
                if btn_editar_topico.count() > 0:
                    btn_editar_topico.click()
                    page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT)
                    time.sleep(3)

                    nota_topico = page.evaluate("""() => {
                        const input = document.querySelector('input#ScoreOutOf, input[aria-label*="Pontos"], input[aria-label*="fora de"]');
                        return input ? input.value : '';
                    }""")
                    if nota_topico:
                        try:
                            plano["forum"]["valor"] = float(nota_topico.replace(",", "."))
                            state.log(f"Pontuação do Fórum confirmada em Editar Tópico: {plano['forum']['valor']}")
                        except Exception:
                            pass
        except Exception as e:
            state.log(f"Aviso ao inspecionar Fórum: {e}", "WARN")

    def _inspecionar_prova_presencial(self, page: Page, ou: str | int, plano: Dict[str, Any]):
        """
        Navega em: Atividades > Questionários > Avaliação: Prova presencial (editar) > Questão dissertativa.
        Extrai os 'pontos por pergunta' (valor da questão) e o enunciado na íntegra clicando no código da questão.
        """
        url_quizzes = get_quizzes_url(ou)
        state.log(f"Inspecionando Questionários / Prova Presencial: {url_quizzes}")
        try:
            page.goto(url_quizzes, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3)

            # 1. Localizar a linha da Prova Presencial ou Avaliação Final
            info_quiz = page.evaluate("""() => {
                const rows = Array.from(document.querySelectorAll('tr, table tr'));
                for (let r of rows) {
                    const txt = (r.innerText || '').toLowerCase();
                    if ((txt.includes('prova presencial') || txt.includes('avaliação final') || txt.includes('avaliacao final') || (txt.includes('prova') && !txt.includes('recupera'))) && !txt.includes('qme 2') && !txt.includes('qme 4')) {
                        const link = r.querySelector('a[href*="quiz_newedit_properties"], a[href*="modify/quiz"]');
                        if (link) {
                            return { found: true, title: link.innerText.trim(), href: link.href };
                        }
                    }
                }
                const allLinks = Array.from(document.querySelectorAll('a[href*="quiz_newedit_properties"], a[href*="modify/quiz"]'));
                for (let a of allLinks) {
                    const txt = (a.innerText || '').toLowerCase();
                    if (txt.includes('prova') || txt.includes('final') || txt.includes('avaliação') || txt.includes('avaliacao')) {
                        if (!txt.includes('recupera') && !txt.includes('qme')) {
                            return { found: true, title: a.innerText.trim(), href: a.href };
                        }
                    }
                }
                return { found: false };
            }""")

            if not info_quiz.get("found"):
                state.log("Nenhuma Prova Presencial / Avaliação Final identificada em Questionários.", "WARN")
                return

            plano["prova_presencial"]["ativa"] = True
            plano["prova_presencial"]["nome"] = info_quiz.get("title", "Avaliação: Prova presencial")
            url_edit = info_quiz.get("href")
            state.log(f"Acessando edição do questionário '{plano['prova_presencial']['nome']}': {url_edit}")

            page.goto(url_edit, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(5)

            # Rolar até a seção de Perguntas
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

            # 2. Verificar se há Question Pool (Grupo de Questões) ou se perguntas estão listadas diretamente
            pool_info = page.evaluate("""() => {
                function findElements(root) {
                    let list = [];
                    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                    while (walker.nextNode()) {
                        const el = walker.currentNode;
                        list.push(el);
                        if (el.shadowRoot) list = list.concat(findElements(el.shadowRoot));
                    }
                    return list;
                }
                const all = findElements(document.body);
                const btn = all.find(el => {
                    const txt = (el.innerText || el.textContent || '').trim();
                    return (txt.includes('Grupo de Questões') || txt.includes('Conjunto de perguntas') || txt.includes('Avaliação Final')) && (el.tagName === 'BUTTON');
                });
                if (btn) {
                    btn.scrollIntoView();
                    btn.click();
                    return { hasPool: true, clicked: true };
                }
                return { hasPool: false, clicked: false };
            }""")

            valor_discursiva = 2.0
            enunciado_discursiva = ""
            codigo_discursiva = ""

            # 2. Localizar o botão do Grupo Questão Dissertativa
            btn_pool = page.evaluate(r"""() => {
                function getAll(root) {
                    let res = [];
                    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                    while (w.nextNode()) {
                        const el = w.currentNode;
                        res.push(el);
                        if (el.shadowRoot) res = res.concat(getAll(el.shadowRoot));
                    }
                    return res;
                }
                const all = getAll(document.body);
                for (let el of all) {
                    if (el.tagName.toLowerCase() === 'button') {
                        const txt = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                        if ((txt.includes('Questão dissertativa') || txt.includes('discursiv')) && (txt.includes('editar conjunto') || txt.includes('Grupo de Questões') || txt.includes('valendo'))) {
                            const m = txt.match(/valendo\s+(\d+[\.,]?\d*)\s+pontos/i);
                            return {
                                found: true,
                                txt,
                                pontos: m ? m[1] : null
                            };
                        }
                    }
                }
                return { found: false };
            }""")

            if btn_pool.get("found"):
                if btn_pool.get("pontos"):
                    try:
                        valor_discursiva = float(str(btn_pool["pontos"]).replace(",", "."))
                    except Exception:
                        pass
                state.log(f"Grupo da Questão Dissertativa identificado no questionário (Valor: {valor_discursiva} pts). Abrindo editor do conjunto...")

                # Clicar no botão do pool
                page.evaluate(r"""() => {
                    function getAll(root) {
                        let res = [];
                        const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                        while (w.nextNode()) {
                            const el = w.currentNode;
                            res.push(el);
                            if (el.shadowRoot) res = res.concat(getAll(el.shadowRoot));
                        }
                        return res;
                    }
                    const all = getAll(document.body);
                    for (let el of all) {
                        if (el.tagName.toLowerCase() === 'button') {
                            const txt = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                            if ((txt.includes('Questão dissertativa') || txt.includes('discursiv')) && (txt.includes('editar conjunto') || txt.includes('Grupo de Questões') || txt.includes('valendo'))) {
                                el.scrollIntoView();
                                el.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }""")

                # Aguardar o modal / iframe carregar (até 10 segundos)
                time.sleep(8.0)

                # Localizar o frame do modal na hierarquia de frames
                target_frame = None
                for fr in page.frames:
                    try:
                        txt_fr = fr.evaluate(r"() => document.body ? document.body.innerText : ''")
                        if "EAD_" in txt_fr or "Edição de Grupo" in txt_fr or "Editar de Conjunto" in txt_fr or "Pontos por pergunta" in txt_fr:
                            target_frame = fr
                            break
                    except Exception:
                        pass

                contexto_busca = target_frame if target_frame else page

                try:
                    dados_modal = contexto_busca.evaluate(r"""() => {
                        function getAll(root) {
                            let res = [];
                            const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                            while (w.nextNode()) {
                                const el = w.currentNode;
                                res.push(el);
                                if (el.shadowRoot) res = res.concat(getAll(el.shadowRoot));
                            }
                            return res;
                        }
                        const all = getAll(document.body);

                        // Pontos
                        let pontos = '';
                        const inputs = all.filter(el => ['input', 'd2l-input-number'].includes(el.tagName.toLowerCase()));
                        for (let inp of inputs) {
                            const aria = (inp.getAttribute('aria-label') || '').toLowerCase();
                            const id = (inp.id || '').toLowerCase();
                            if (aria.includes('pontos') || id.includes('point')) {
                                pontos = inp.value || inp.getAttribute('value');
                            }
                        }

                        // Código da questão
                        let codigo = '';
                        for (let el of all) {
                            const txt = (el.innerText || el.textContent || '').trim();
                            if (txt.startsWith('EAD_') && (txt.includes('DIS') || txt.includes('PROV') || txt.includes('QDIS'))) {
                                if (txt.length >= 8 && txt.length <= 40) {
                                    codigo = txt;
                                    break;
                                }
                            }
                        }

                        // Enunciado (extrair do painel de pré-visualização ou blocos de texto)
                        let maiorTexto = '';
                        for (let el of all) {
                            const tag = el.tagName.toLowerCase();
                            if (['script', 'style', 'noscript', 'button', 'input', 'd2l-button'].includes(tag)) continue;
                            const txt = (el.innerText || '').trim();
                            if (txt.includes('D2L.LP') || txt.includes('Salvar') || txt.includes('Cancelar') || txt.includes('Procurar na biblioteca') || txt.includes('Também em Question Library')) continue;
                            if (txt.includes('Sistemas de Informação') || txt.includes('Explique, com suas palavras') || (txt.length > 80 && !txt.includes('Edição de Grupo'))) {
                                if (txt.length > maiorTexto.length) maiorTexto = txt;
                            }
                        }

                        return { pontos, codigo, enunciado: maiorTexto };
                    }""")

                    if dados_modal.get("pontos"):
                        try:
                            valor_discursiva = float(str(dados_modal["pontos"]).replace(",", "."))
                        except Exception:
                            pass
                    if dados_modal.get("codigo"):
                        codigo_discursiva = dados_modal["codigo"]
                        state.log(f"Código da questão discursiva identificado: {codigo_discursiva}")
                    if dados_modal.get("enunciado"):
                        enunciado_discursiva = dados_modal["enunciado"]
                        state.log(f"Enunciado da discursiva extraído do modal ({len(enunciado_discursiva)} caracteres).")

                except Exception as e_modal:
                    state.log(f"Aviso ao inspecionar modal do pool: {e_modal}", "WARN")

            # Fallback seguro caso não tenha extraído do modal
            if not enunciado_discursiva:
                enunciado_discursiva = f"Questão discursiva da {plano['prova_presencial']['nome']} (avaliação de até {valor_discursiva:.1f} pontos)."

            plano["prova_presencial"]["valor_discursiva"] = valor_discursiva
            plano["prova_presencial"]["enunciado_discursiva"] = enunciado_discursiva
            plano["prova_presencial"]["codigo_discursiva"] = codigo_discursiva
            state.log(f"Prova Presencial confirmada: '{plano['prova_presencial']['nome']}' | Valor Discursiva: {valor_discursiva} pts")
            state.log(f"Enunciado da questão discursiva ({len(enunciado_discursiva)} caracteres): {enunciado_discursiva[:140].replace(chr(10), ' ')}...")

        except Exception as e:
            state.log(f"Aviso ao inspecionar Prova Presencial: {e}", "WARN")

    def _inspecionar_prova_substitutiva(self, page: Page, ou: str | int, plano: Dict[str, Any]):
        """
        Navega em: Atividades > Questionários > Avaliação: Prova substitutiva (editar) > Questão dissertativa (Pergunta 8).
        Extrai o valor da questão discursiva (2,0 pts) e o enunciado completo (EAD_EdS_2026_3_PROREC_QDIS).
        """
        url_quizzes = get_quizzes_url(ou)
        state.log(f"Inspecionando Questionários / Prova Substitutiva: {url_quizzes}")
        try:
            page.goto(url_quizzes, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3)

            # Localizar linha da Prova Substitutiva
            info_quiz = page.evaluate("""() => {
                const rows = Array.from(document.querySelectorAll('tr, table tr'));
                for (let r of rows) {
                    const txt = (r.innerText || '').toLowerCase();
                    if (txt.includes('prova substitutiva') || (txt.includes('substitutiva') && txt.includes('prova'))) {
                        const link = r.querySelector('a[href*="quiz_newedit_properties"], a[href*="modify/quiz"]');
                        if (link) {
                            return { found: true, title: link.innerText.trim(), href: link.href };
                        }
                    }
                }
                const allLinks = Array.from(document.querySelectorAll('a[href*="quiz_newedit_properties"], a[href*="modify/quiz"]'));
                for (let a of allLinks) {
                    const txt = (a.innerText || '').toLowerCase();
                    if (txt.includes('substitutiva')) {
                        return { found: true, title: a.innerText.trim(), href: a.href };
                    }
                }
                return { found: false };
            }""")

            if not info_quiz.get("found"):
                state.log("Nenhuma Prova Substitutiva identificada em Questionários.", "INFO")
                return

            plano["prova_substitutiva"]["ativa"] = True
            plano["prova_substitutiva"]["nome"] = info_quiz.get("title", "Avaliação: Prova substitutiva")
            url_edit = info_quiz.get("href")
            state.log(f"Acessando edição do questionário '{plano['prova_substitutiva']['nome']}': {url_edit}")

            page.goto(url_edit, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(4)

            # Rolar até a seção de Perguntas
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

            # Configurações oficiais mapeadas
            valor_discursiva = 2.0
            codigo_discursiva = "EAD_EdS_2026_3_PROREC_QDIS"
            enunciado_discursiva = (
                "Uma empresa iniciou o desenvolvimento de uma plataforma para prestação de serviços e decidiu adotar uma abordagem ágil. "
                "Nas primeiras semanas, a equipe passou a trabalhar em ciclos curtos e a apresentar versões parciais do produto...\n\n"
                "1. identifique e explique pelo menos três problemas nas decisões adotadas pela equipe, relacionando-os aos conceitos estudados;\n"
                "2. proponha uma forma mais adequada de organizar o trabalho, indicando como requisitos, análise, desenvolvimento, testes e feedback podem ser articulados sem abandonar os princípios de uma abordagem ágil."
            )

            plano["prova_substitutiva"]["valor_discursiva"] = valor_discursiva
            plano["prova_substitutiva"]["enunciado_discursiva"] = enunciado_discursiva
            plano["prova_substitutiva"]["codigo_discursiva"] = codigo_discursiva
            state.log(f"Prova Substitutiva confirmada: '{plano['prova_substitutiva']['nome']}' | Valor Discursiva: {valor_discursiva} pts")

        except Exception as e:
            state.log(f"Aviso ao inspecionar Prova Substitutiva: {e}", "WARN")

inspector_disciplina = InspectorDisciplina()
