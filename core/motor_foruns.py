import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from config import get_forums_url, get_quickeval_url, DYNAMIC_LOAD_WAIT_MS, NAV_TIMEOUT
from engine_state import state
from cognitive.detector_plagio import detector_plagio
from cognitive.analisador_pedagogico import analisador_pedagogico
from cognitive.construtor_feedback import construtor_feedback, extrair_primeiro_nome
from core.navigation_iterator import (
    extrair_posicao_mostrador_iterator,
    extrair_nome_estudante_atual,
    avancar_proximo_estudante_seguro
)
from core.dom_helpers import (
    inserir_nota_consistent_evaluation,
    inserir_feedback_consistent_evaluation,
    salvar_rascunho_consistent_evaluation,
    obter_nota_e_feedback_consistent_evaluation
)

class MotorForuns:
    """
    Motor especialista de avaliação e auditoria para o Fórum de Discussão.
    Implementa os 4 modos: Tradicional, Auditoria, Recorrigir e Auditoria Geral.
    Garante navegação completa de 1 a N na turma através de Shadow DOM no iterator.
    """

    def executar(
        self,
        page: Page,
        ou: str | int,
        disciplina: str,
        modo: str,
        plano: Dict[str, Any],
        docente: str
    ) -> List[Dict[str, Any]]:
        state.log(f"Iniciando Motor de Fóruns para [{ou}] {disciplina} (Modo: {modo.upper()})...")
        resultados = []
        nota_maxima = plano.get("forum", {}).get("valor", 1.0)
        comando_oficial = plano.get("forum", {}).get("comando", "")

        # 1. Obter link de entrada do plano mapeado pelo Quick Eval
        forum_info = plano.get("forum", {})
        novos_envios = forum_info.get("total_pendentes", 0)
        forum_href = forum_info.get("url_all") or forum_info.get("url_new")

        # Fallback de busca no Quick Eval se url não estiver no plano
        if not forum_href:
            url_qe = get_quickeval_url(ou)
            page.goto(url_qe, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3)
            # Selecionar aba Atividades
            toggle = page.locator("d2l-tab:has-text('Atividades'), [role='tab']:has-text('Atividades'), button:has-text('Atividades')").first
            if toggle.count() > 0:
                try:
                    toggle.click(timeout=3000)
                    time.sleep(2.5)
                except Exception:
                    pass

            links = page.locator("a[href*='evaluation/activity']")
            for i in range(links.count()):
                txt = links.nth(i).inner_text().lower()
                href = links.nth(i).get_attribute("href")
                if "fórum" in txt or "forum" in txt or "discussão" in txt or "postagens" in txt:
                    forum_href = href if href.startswith("http") else f"https://ava.catolica.edu.br{href}"
                    m_num = re.search(r'^\s*(\d+)', txt)
                    if m_num:
                        novos_envios = int(m_num.group(1))
                    break

        if not forum_href:
            state.log("Não foi possível localizar o ponto de entrada de avaliação do Fórum.", "WARN")
            return resultados

        # Definir URLs e Modo Efetivo
        url_all = forum_href.replace("iteratorRange=new", "iteratorRange=all")
        if "iteratorRange=" not in url_all:
            url_all += ("&" if "?" in url_all else "?") + "iteratorRange=all"
        url_new = forum_href.replace("iteratorRange=all", "iteratorRange=new")

        if modo == "tradicional":
            if novos_envios == 0:
                state.log(f"[Execução Normal] Nenhum novo envio pendente no Fórum ({disciplina}). Nenhuma correção necessária.")
                return resultados
            else:
                state.log(f"[Execução Normal] {novos_envios} novo(s) envio(s) pendente(s) no Fórum. Iniciando correções e auditoria comum...")
                forum_href = url_all
                modo_efetivo = "tradicional_com_auditoria"
        elif modo == "recorrigir":
            state.log(f"[Recorrigir + Auditoria Geral] Reavaliando e auditando 100% dos estudantes do Fórum ({disciplina})...")
            forum_href = url_all
            modo_efetivo = "recorrigir_e_auditar"
        else:
            state.log(f"[{modo.upper()}] Acessando todos os estudantes para auditoria...")
            forum_href = url_all
            modo_efetivo = modo

        state.log(f"Acessando Avaliação Consistente do Fórum: {forum_href}")
        page.goto(forum_href, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        time.sleep(4)

        # Loop de avaliação consistente (iterator de alunos)
        aluno_idx = 0
        alunos_processados = set()

        while not state.should_stop:
            aluno_idx += 1
            time.sleep(DYNAMIC_LOAD_WAIT_MS / 1000.0)

            if state.should_stop:
                break

            pos_info = extrair_posicao_mostrador_iterator(page)
            pos_str = f"[{pos_info['atual']}/{pos_info['total']}] " if pos_info.get("atual") else f"[{aluno_idx}] "
            nome_aluno = extrair_nome_estudante_atual(page)

            chave_aluno = f"{pos_info.get('atual')}_{nome_aluno}" if pos_info.get("atual") else nome_aluno
            if chave_aluno in alunos_processados and nome_aluno != "Estudante":
                state.log(f"Aluno {nome_aluno} já processado nesta rodada. Avançando...")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    break
                continue

            alunos_processados.add(chave_aluno)
            total_estimado = pos_info.get("total") or plano.get("forum", {}).get("total_geral", 10)
            state.update_progress(pos_info.get("atual") or aluno_idx, total_estimado, nome_aluno, "Fórum de Discussão")

            # 3. Aguardar carregamento completo e extrair postagens e réplicas
            postagens = self._aguardar_e_extrair_postagens_forum(page)
            
            # Pular estudantes sem postagens confirmadas após o carregamento
            if not postagens:
                state.log(f"{pos_str}{nome_aluno}: Sem postagens no Fórum confirmadas após carregamento. Pulando...")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    state.log("Fim da lista de estudantes do Fórum alcançado.")
                    break
                continue

            texto_completo = "\n\n".join([p["texto"] for p in postagens])
            qtd_total_posts = len(postagens)
            if qtd_total_posts >= 2:
                qtd_posts = 1
                qtd_replies = qtd_total_posts - 1
            else:
                qtd_posts = 1 if qtd_total_posts == 1 else 0
                qtd_replies = 0

            # 4. Detecção de cópia / plágio cruzado
            info_plagio = detector_plagio.registrar_e_comparar(
                ou=ou,
                disciplina=disciplina,
                atividade="Fórum de discussão",
                aluno_nome=nome_aluno,
                texto_submissao=texto_completo
            )
            if info_plagio.get("tem_plagio", False):
                state.log(f"ALERTA DE PLÁGIO NO FÓRUM (≥ 90%): {nome_aluno} possui {info_plagio['similaridade_pct']}% de similaridade com {info_plagio['aluno_autor']}!", "WARN")
                if info_plagio.get("relatorio_comparacao"):
                    state.log(f"Comparação gerada: {info_plagio['relatorio_comparacao']}")
                state.increment_stat("plagios_detectados")

            # 5. Avaliação pedagógica aprofundada
            metadados = {
                "posts_count": qtd_posts,
                "replies_count": qtd_replies,
                "total_posts": qtd_total_posts
            }
            diagnostico = analisador_pedagogico.avaliar_submissao(
                tipo_atividade="forum",
                texto_aluno=texto_completo,
                comando_oficial=comando_oficial,
                nota_maxima=nota_maxima,
                metadados_envio=metadados,
                info_plagio=info_plagio
            )

            nota_calculada = diagnostico["nota_sugerida"]
            feedback_html = construtor_feedback.gerar_feedback(
                nome_estudante=nome_aluno,
                tipo_atividade="forum",
                diagnostico_pedagogico=diagnostico,
                nome_docente=docente,
                info_plagio=info_plagio
            )

            # 6. Execução segundo o Modo Efetivo
            if modo_efetivo == "recorrigir_e_auditar":
                state.log(f"{pos_str}[Recorrigir + Auditoria] Reavaliando {nome_aluno}: Nota {nota_calculada}/{nota_maxima}...")
                self._inserir_nota_e_feedback(page, nota_calculada, feedback_html)
                self._salvar_rascunho(page)
                state.increment_stat("avaliados")
                state.increment_stat("auditados")

            elif modo_efetivo == "auditoria_comum":
                fb_atual = self._obter_feedback_atual(page)
                first_name = extrair_primeiro_nome(nome_aluno)
                tem_token = "{firstname}" in fb_atual.lower()
                tem_nome = bool(first_name and first_name.lower() in fb_atual.lower())
                conforme = tem_token or tem_nome
                if not conforme or not fb_atual.strip():
                    state.log(f"{pos_str}[Auditoria Comum] {nome_aluno}: Feedback sem '{{FirstName}}'. Atualizando feedback formativo...")
                    self._inserir_nota_e_feedback(page, nota_calculada, feedback_html)
                    self._salvar_rascunho(page)
                    state.increment_stat("ajustados")
                else:
                    state.log(f"{pos_str}[Auditoria Comum] {nome_aluno}: Conforme ('{{FirstName}}' presente).")
                state.increment_stat("auditados")

            elif modo_efetivo == "tradicional_com_auditoria":
                fb_atual = self._obter_feedback_atual(page)
                first_name = extrair_primeiro_nome(nome_aluno)
                if not fb_atual.strip():
                    state.log(f"{pos_str}[Novo Envio] Avaliando novo envio de {nome_aluno}: Nota {nota_calculada}/{nota_maxima}...")
                    self._inserir_nota_e_feedback(page, nota_calculada, feedback_html)
                    self._salvar_rascunho(page)
                    state.increment_stat("avaliados")
                else:
                    tem_token = "{firstname}" in fb_atual.lower()
                    tem_nome = bool(first_name and first_name.lower() in fb_atual.lower())
                    conforme = tem_token or tem_nome
                    if not conforme:
                        state.log(f"{pos_str}[Auditoria Comum] Ajustando feedback de {nome_aluno} para incluir '{{FirstName}}'...")
                        self._inserir_nota_e_feedback(page, nota_calculada, feedback_html)
                        self._salvar_rascunho(page)
                        state.increment_stat("ajustados")
                    else:
                        state.log(f"{pos_str}[Auditoria Comum] {nome_aluno}: Conforme ('{{FirstName}}' presente).")
                    state.increment_stat("auditados")

            else:  # auditoria / auditoria_geral
                fb_atual = self._obter_feedback_atual(page)
                first_name = extrair_primeiro_nome(nome_aluno)
                tem_token = "{firstname}" in fb_atual.lower()
                tem_nome = bool(first_name and first_name.lower() in fb_atual.lower())
                conforme = tem_token or tem_nome
                if not conforme:
                    state.log(f"{pos_str}[Auditoria] Inserindo tag oficial '{{FirstName}}' no feedback de {nome_aluno}...")
                    self._inserir_nota_e_feedback(page, nota_calculada, feedback_html)
                    self._salvar_rascunho(page)
                    state.increment_stat("ajustados")
                else:
                    state.log(f"{pos_str}[Auditoria] {nome_aluno}: Conforme ('{{FirstName}}' presente).")
                state.increment_stat("auditados")

            # 7. Registrar histórico
            registro = {
                "ou": str(ou),
                "disciplina": disciplina,
                "atividade": "Fórum de discussão",
                "aluno": nome_aluno,
                "nota": nota_calculada,
                "nota_max": nota_maxima,
                "plagio": info_plagio.get("tem_plagio", False),
                "similaridade_pct": info_plagio.get("similaridade_pct", 0.0),
                "qualidade": diagnostico.get("qualidade_geral", "Bom"),
                "modo": modo
            }
            resultados.append(registro)

            # 8. Avançar para o próximo estudante no iterator
            if state.should_stop:
                break
            if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                state.log("Todos os estudantes da turma do Fórum foram concluídos com sucesso!")
                break

    def _aguardar_e_extrair_postagens_forum(self, page: Page, max_wait_sec: float = 7.0) -> List[Dict[str, Any]]:
        """
        Aguarda ativamente o carregamento da evidência do Fórum no Consistent Evaluation
        para garantir que postagens/réplicas não sejam ignoradas precipitadamente.
        Retorna as postagens/réplicas encontradas ou lista vazia caso confirmado que o aluno não postou.
        """
        start_time = time.time()
        min_wait = 2.5

        while time.time() - start_time < max_wait_sec:
            postagens = self._extrair_postagens_forum(page)
            if postagens:
                return postagens

            # Verificar se ainda há spinners de carregamento ativos
            try:
                carregando = page.evaluate("""() => {
                    const spinners = document.querySelectorAll('d2l-loading-spinner, [aria-busy="true"], .d2l-loading-spinner');
                    for (let s of spinners) {
                        if (s.offsetParent !== null || s.getAttribute('aria-busy') === 'true') return true;
                    }
                    return false;
                }""")
            except Exception:
                carregando = False

            elapsed = time.time() - start_time
            if not carregando and elapsed >= min_wait:
                # Verificar se há texto explícito indicando ausência de postagens
                sem_posts = page.evaluate("""() => {
                    const text = (document.body.innerText || '').toLowerCase();
                    return text.includes('nenhuma postagem') || 
                           text.includes('nenhum tópico') || 
                           text.includes('não há postagens') || 
                           text.includes('no posts') ||
                           text.includes('o usuário não postou') ||
                           text.includes('nenhuma evidência');
                }""")
                if sem_posts:
                    return []

            time.sleep(0.5)

        return self._extrair_postagens_forum(page)

    def _extrair_postagens_forum(self, page: Page) -> List[Dict[str, Any]]:
        try:
            # 1. Expandir paginação 'Carregar mais' no painel de discussões, se houver
            try:
                page.evaluate("""() => {
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
                        const tag = el.tagName.toLowerCase();
                        if (tag === 'd2l-pager-load-more' || (tag.includes('button') && (el.innerText || '').includes('Carregar mais'))) {
                            const btn = el.shadowRoot ? el.shadowRoot.querySelector('button, d2l-button-subtle') : el;
                            if (btn && typeof btn.click === 'function') btn.click();
                        }
                    }
                }""")
            except Exception:
                pass

            return page.evaluate(r"""() => {
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
                const results = [];
                const vistos = new Set();

                for (let el of all) {
                    const tag = el.tagName.toLowerCase();
                    if (tag === 'd2l-consistent-evaluation-discussion-evidence-body') {
                        const htmlBlock = el.querySelector('d2l-html-block') || (el.shadowRoot ? el.shadowRoot.querySelector('d2l-html-block') : null);
                        let t = "";
                        if (htmlBlock) {
                            t = (htmlBlock.html || htmlBlock.innerText || htmlBlock.textContent || '').trim();
                        }
                        if (!t) {
                            t = (el.getAttribute('post-body') || el.innerText || el.textContent || '').trim();
                        }
                        const div = document.createElement('div');
                        div.innerHTML = t;
                        const txtLimpo = (div.innerText || div.textContent || t).trim();
                        if (txtLimpo.length > 15 && !vistos.has(txtLimpo) && !txtLimpo.includes('Sua sessão')) {
                            vistos.add(txtLimpo);
                            results.push({ texto: txtLimpo, tipo: 'post' });
                        }
                    }
                }

                // Fallback para containers adicionais de postagem
                if (results.length === 0) {
                    const fallbacks = document.querySelectorAll('.d2l-consistent-evaluation-discussion-post, [class*="discussion-post"], .d2l-text-styled');
                    for (let el of fallbacks) {
                        const t = (el.innerText || el.textContent || '').trim();
                        if (t.length > 20 && !vistos.has(t) && !t.includes('Sua sessão')) {
                            vistos.add(t);
                            results.push({ texto: t, tipo: 'post' });
                        }
                    }
                }
                return results;
            }""")
        except Exception:
            return []

    def _obter_feedback_atual(self, page: Page) -> str:
        try:
            dados = obter_nota_e_feedback_consistent_evaluation(page)
            if dados.get("feedback"):
                return dados["feedback"]
        except Exception:
            pass
        return ""

    def _inserir_nota_e_feedback(self, page: Page, nota: float, feedback_html: str):
        try:
            inserir_nota_consistent_evaluation(page, nota)
            inserir_feedback_consistent_evaluation(page, feedback_html)
        except Exception as e:
            state.log(f"Aviso ao inserir nota e feedback no fórum: {e}", "WARN")

    def _salvar_rascunho(self, page: Page) -> bool:
        try:
            return salvar_rascunho_consistent_evaluation(page)
        except Exception:
            return False

motor_foruns = MotorForuns()
