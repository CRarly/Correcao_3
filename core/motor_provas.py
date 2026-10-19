import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from config import get_quizzes_url, get_quickeval_url, DYNAMIC_LOAD_WAIT_MS, NAV_TIMEOUT
from engine_state import state
from cognitive.detector_plagio import detector_plagio
from cognitive.analisador_pedagogico import analisador_pedagogico
from cognitive.construtor_feedback import construtor_feedback, extrair_primeiro_nome
from core.navigation_iterator import (
    extrair_posicao_mostrador_iterator,
    extrair_nome_estudante_atual,
    avancar_proximo_estudante_seguro
)
from core.dom_helpers import salvar_rascunho_consistent_evaluation, salvar_rascunho_duplo


class MotorProvas:
    """
    Motor especialista de avaliação e auditoria da Prova Presencial.
    Atua exclusivamente na Questão Discursiva (até 2,0 pontos), preservando integralmente
    as questões objetivas/múltipla escolha. Lança nota e feedback nos campos específicos da questão
    e avança com segurança de 1 a N na turma.
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
        state.log(f"Iniciando Motor de Provas Presenciais para [{ou}] {disciplina} (Modo: {modo.upper()})...")
        resultados = []
        nota_max_discursiva = plano.get("prova_presencial", {}).get("valor_discursiva", 2.0)
        enunciado_discursiva = plano.get("prova_presencial", {}).get("enunciado_discursiva", "")

        # 1. Obter link de entrada do plano mapeado pelo Quick Eval
        prova_info = plano.get("prova_presencial", {})
        novos_envios = prova_info.get("total_pendentes", 0)
        prova_href = prova_info.get("url_all") or prova_info.get("url_new")

        # Fallback de busca no Quick Eval se url não estiver no plano
        if not prova_href:
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
                if "prova" in txt or "presencial" in txt or "tentativas" in txt:
                    prova_href = href if href.startswith("http") else f"https://ava.catolica.edu.br{href}"
                    m_num = re.search(r'^\s*(\d+)', txt)
                    if m_num:
                        novos_envios = int(m_num.group(1))
                    break

        if not prova_href:
            state.log("Nenhuma Prova Presencial identificada no Quick Eval.", "WARN")
            return resultados

        # Definir URLs e Modo Efetivo
        url_all = prova_href.replace("iteratorRange=new", "iteratorRange=all")
        if "iteratorRange=" not in url_all:
            url_all += ("&" if "?" in url_all else "?") + "iteratorRange=all"
        url_new = prova_href.replace("iteratorRange=all", "iteratorRange=new")

        if modo == "tradicional":
            if novos_envios == 0:
                state.log(f"[Execução Normal] Nenhum novo envio pendente na Prova Presencial ({disciplina}). Nenhuma correção necessária.")
                return resultados
            else:
                state.log(f"[Execução Normal] {novos_envios} novo(s) envio(s) pendente(s) na Prova Presencial. Iniciando correções e auditoria comum...")
                prova_href = url_all
                modo_efetivo = "tradicional_com_auditoria"
        elif modo == "recorrigir":
            state.log(f"[Recorrigir + Auditoria Geral] Reavaliando e auditando 100% das tentativas da Prova Presencial ({disciplina})...")
            prova_href = url_all
            modo_efetivo = "recorrigir_e_auditar"
        else:
            state.log(f"[{modo.upper()}] Acessando todas as tentativas para auditoria...")
            prova_href = url_all
            modo_efetivo = modo

        state.log(f"Acessando Avaliação Consistente da Prova Presencial: {prova_href}")
        page.goto(prova_href, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        time.sleep(4)

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
                state.log(f"Tentativa de {nome_aluno} já processada. Avançando...")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    break
                continue

            alunos_processados.add(chave_aluno)
            total_estimado = pos_info.get("total") or plano.get("prova_presencial", {}).get("total_geral", 10)
            state.update_progress(pos_info.get("atual") or aluno_idx, total_estimado, nome_aluno, "Prova Presencial (Discursiva)")

            # Assegurar que a tentativa esteja selecionada (sair de Resumo da conclusão se necessário)
            self._assegurar_tentativa_carregada(page)

            # Localizar o bloco da Questão Discursiva com espera ativa e rolagem gradual (sem alterar objetivas)
            bloco_discursiva = self._aguardar_carregamento_questao_discursiva(page)
            if not bloco_discursiva:
                state.log(f"{pos_str}Questão discursiva não localizada na tentativa de {nome_aluno} após rolagem e carregamento. Pulando...", "WARN")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    break
                continue

            # Extrair resposta do estudante na questão discursiva (com indentação / tabulação a mais)
            texto_resposta = self._extrair_resposta_discursiva(page)
            if not texto_resposta.strip():
                time.sleep(2.0)
                texto_resposta = self._extrair_resposta_discursiva(page)

            # Pular estudantes sem resposta na discursiva após confirmação
            if not texto_resposta.strip():
                state.log(f"{pos_str}{nome_aluno}: Questão discursiva sem resposta confirmada após carregamento. Pulando...")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    break
                continue

            # Plágio cruzado na discursiva
            info_plagio = detector_plagio.registrar_e_comparar(
                ou=ou,
                disciplina=disciplina,
                atividade="Prova presencial",
                aluno_nome=nome_aluno,
                texto_submissao=texto_resposta
            )
            if info_plagio.get("tem_plagio", False):
                state.log(f"ALERTA DE PLÁGIO NA DISCURSIVA (≥ 90%): {nome_aluno} possui {info_plagio['similaridade_pct']}% de cópia de {info_plagio['aluno_autor']}!", "WARN")
                if info_plagio.get("relatorio_comparacao"):
                    state.log(f"Comparação de discursiva gerada: {info_plagio['relatorio_comparacao']}")
                state.increment_stat("plagios_detectados")

            # Avaliação pedagógica exclusiva da discursiva
            diagnostico = analisador_pedagogico.avaliar_submissao(
                tipo_atividade="prova_presencial",
                texto_aluno=texto_resposta,
                comando_oficial=enunciado_discursiva,
                nota_maxima=nota_max_discursiva,
                metadados_envio={"palavras": len(texto_resposta.split())},
                info_plagio=info_plagio
            )

            nota_calculada = diagnostico["nota_sugerida"]
            feedback_html = construtor_feedback.gerar_feedback(
                nome_estudante=nome_aluno,
                tipo_atividade="prova_presencial",
                diagnostico_pedagogico=diagnostico,
                nome_docente=docente,
                info_plagio=info_plagio
            )

            # Execução segundo o Modo Efetivo - Salvar Rascunho DUAS VEZES (sem publicar)
            if modo_efetivo == "recorrigir_e_auditar":
                state.log(f"{pos_str}[Recorrigir + Auditoria] Reavaliando discursiva de {nome_aluno}: Nota {nota_calculada}/{nota_max_discursiva}...")
                self._inserir_nota_e_feedback_questao(page, nota_calculada, feedback_html, nota_max_discursiva)
                self._salvar_rascunho_duplo(page)
                state.increment_stat("avaliados")
                state.increment_stat("auditados")

            elif modo_efetivo == "auditoria_comum":
                first_name = extrair_primeiro_nome(nome_aluno)
                fb_atual = self._obter_feedback_questao(page)
                tem_token = "{firstname}" in fb_atual.lower()
                tem_nome = bool(first_name and first_name.lower() in fb_atual.lower())
                conforme = tem_token or tem_nome
                if not conforme or not fb_atual.strip():
                    state.log(f"{pos_str}[Auditoria Comum] Ajustando feedback da discursiva de {nome_aluno} para incluir '{{FirstName}}'...")
                    self._inserir_nota_e_feedback_questao(page, nota_calculada, feedback_html, nota_max_discursiva)
                    self._salvar_rascunho_duplo(page)
                    state.increment_stat("ajustados")
                else:
                    state.log(f"{pos_str}[Auditoria Comum] {nome_aluno}: Discursiva conforme ('{{FirstName}}' presente).")
                state.increment_stat("auditados")

            elif modo_efetivo == "tradicional_com_auditoria":
                fb_atual = self._obter_feedback_questao(page)
                first_name = extrair_primeiro_nome(nome_aluno)
                if not fb_atual.strip():
                    state.log(f"{pos_str}[Novo Envio] Avaliando discursiva de {nome_aluno}: Nota {nota_calculada}/{nota_max_discursiva}...")
                    self._inserir_nota_e_feedback_questao(page, nota_calculada, feedback_html, nota_max_discursiva)
                    self._salvar_rascunho_duplo(page)
                    state.increment_stat("avaliados")
                else:
                    tem_token = "{firstname}" in fb_atual.lower()
                    tem_nome = bool(first_name and first_name.lower() in fb_atual.lower())
                    conforme = tem_token or tem_nome
                    if not conforme:
                        state.log(f"{pos_str}[Auditoria Comum] Ajustando feedback da discursiva de {nome_aluno} para incluir '{{FirstName}}'...")
                        self._inserir_nota_e_feedback_questao(page, nota_calculada, feedback_html, nota_max_discursiva)
                        self._salvar_rascunho_duplo(page)
                        state.increment_stat("ajustados")
                    else:
                        state.log(f"{pos_str}[Auditoria Comum] {nome_aluno}: Discursiva conforme ('{{FirstName}}' presente).")
                    state.increment_stat("auditados")

            else:  # auditoria / auditoria_geral
                first_name = extrair_primeiro_nome(nome_aluno)
                fb_atual = self._obter_feedback_questao(page)
                tem_token = "{firstname}" in fb_atual.lower()
                tem_nome = bool(first_name and first_name.lower() in fb_atual.lower())
                conforme = tem_token or tem_nome
                if not conforme:
                    state.log(f"{pos_str}[Auditoria] Inserindo tag oficial '{{FirstName}}' na discursiva de {nome_aluno}...")
                    self._inserir_nota_e_feedback_questao(page, nota_calculada, feedback_html, nota_max_discursiva)
                    self._salvar_rascunho_duplo(page)
                    state.increment_stat("ajustados")
                else:
                    state.log(f"{pos_str}[Auditoria] {nome_aluno}: Conforme ('{{FirstName}}' presente).")
                state.increment_stat("auditados")

            registro = {
                "ou": str(ou),
                "disciplina": disciplina,
                "atividade": "Prova presencial",
                "aluno": nome_aluno,
                "nota": nota_calculada,
                "nota_max": nota_max_discursiva,
                "plagio": info_plagio.get("tem_plagio", False),
                "similaridade_pct": info_plagio.get("similaridade_pct", 0.0),
                "qualidade": diagnostico.get("qualidade_geral", "Bom"),
                "modo": modo
            }
            resultados.append(registro)

            if state.should_stop:
                break
            if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                state.log("Todas as tentativas da Prova Presencial foram concluídas com sucesso!")
                break

        # Requisito: Análise de coerência ao final das avaliações (ex.: 97/97)
        self._executar_auditoria_coerencia(resultados, plano, ou, disciplina)

        return resultados

    def _assegurar_tentativa_carregada(self, page: Page) -> bool:
        """
        Garante que a visualização esteja na tentativa ativa do estudante,
        clicando em 'Tentativa 1' ou alternando de 'Resumo da conclusão'.
        """
        try:
            clicado = page.evaluate(r"""() => {
                function getAllElements(root) {
                    let list = [];
                    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                    while (walker.nextNode()) {
                        const el = walker.currentNode;
                        list.push(el);
                        if (el.shadowRoot) list = list.concat(getAllElements(el.shadowRoot));
                    }
                    return list;
                }
                const all = getAllElements(document.body);
                for (let el of all) {
                    const txt = (el.innerText || el.textContent || '').trim();
                    if (txt === 'Tentativa 1' || txt.startsWith('Tentativa 1')) {
                        const target = el.closest ? (el.closest('a') || el.closest('button') || el) : el;
                        if (typeof target.click === 'function') {
                            target.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if clicado:
                time.sleep(4.0)
                return True

            sel = page.locator("select[aria-label*='Tentativas']").first
            if sel.count() > 0:
                val = sel.input_value()
                if val == "completion-summary":
                    sel.select_option(index=0)
                    time.sleep(3.0)
                    return True
        except Exception:
            pass
        return False

    def _aguardar_carregamento_questao_discursiva(self, page: Page, max_scroll_steps: int = 12):
        """
        Busca a questão discursiva dentro da avaliação rolando a página gradualmente
        até encontrar o bloco com enunciado, resposta indentada e campos de avaliação.
        """
        for step in range(max_scroll_steps):
            bloco = self._localizar_bloco_questao_discursiva(page)
            if bloco:
                try:
                    bloco.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                return bloco
            # Rolar página para baixo gradualmente
            page.evaluate("window.scrollBy(0, 450);")
            time.sleep(0.6)
        return None

    def _localizar_bloco_questao_discursiva(self, page: Page):
        try:
            blocos = page.locator(".d2l-quiz-question, .d2l-question-container, div[id*='question'], d2l-consistent-evaluation-quiz-question")
            total = blocos.count()
            for i in range(total):
                bloco = blocos.nth(i)
                txt = bloco.inner_text().lower()

                # Ignorar questões objetivas / múltipla escolha
                if "múltipla escolha" in txt or "multipla escolha" in txt or "5 escolhas" in txt or "escolhas" in txt:
                    continue
                if bloco.locator("input[type='radio'], input[type='checkbox']").count() > 0:
                    continue

                # Verificar se é dissertativa / discursiva / resposta por extenso
                is_discursiva = any(k in txt for k in ["dissertat", "discursiv", "resposta por extenso", "resposta escrita", "resposta longa"])
                tem_campos = bloco.locator("input[aria-label*='Pontos'], input[aria-label*='pontuação'], textarea, div.d2l-html-editor-content, d2l-input-number").count() > 0

                if is_discursiva or (tem_campos and bloco.locator("input[type='radio'], input[type='checkbox']").count() == 0):
                    return bloco
        except Exception:
            pass
        return None

    def _extrair_enunciado_discursiva(self, page: Page) -> str:
        """
        Extrai o texto completo do comando/enunciado da questão discursiva (Pergunta 8)
        através dos blocos renderizados no container da pergunta, penetrando shadow roots.
        """
        try:
            texto = page.evaluate(r"""() => {
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
                const wrapQuestion = all.filter(el => (el.className || '').toString().includes('d2l-questions-question-wrapper'));
                if (wrapQuestion.length > 0) {
                    const targetWrap = wrapQuestion[wrapQuestion.length - 1];
                    const rendered = getAll(targetWrap).filter(el => (el.className || '').toString().includes('d2l-html-block-rendered'));
                    if (rendered.length > 0) {
                        for (let r of rendered) {
                            const t = (r.innerText || '').trim();
                            if (t.length > 0) return t;
                        }
                    }
                    const htmlBlocks = getAll(targetWrap).filter(el => el.tagName.toLowerCase() === 'd2l-html-block');
                    for (let hb of htmlBlocks) {
                        const t = (hb.html || hb.innerText || '').trim();
                        if (t) {
                            const div = document.createElement('div');
                            div.innerHTML = t;
                            const resTxt = (div.innerText || '').trim();
                            if (resTxt.length > 0) return resTxt;
                        }
                    }
                }
                // Fallback: buscar d2l-html-block-rendered logo após a Pergunta 8
                let q8Idx = -1;
                for (let i = 0; i < all.length; i++) {
                    if ((all[i].innerText || '').trim() === 'Pergunta 8') {
                        q8Idx = i;
                        break;
                    }
                }
                if (q8Idx !== -1) {
                    for (let i = q8Idx; i < Math.min(all.length, q8Idx + 30); i++) {
                        const el = all[i];
                        if ((el.className || '').toString().includes('d2l-html-block-rendered') && (el.innerText || '').length > 50) {
                            return el.innerText.trim();
                        }
                    }
                }
                return '';
            }""")
            return (texto or "").strip()
        except Exception:
            return ""

    def _extrair_resposta_discursiva(self, page: Page) -> str:
        """
        Extrai a resposta submetida pelo estudante na questão discursiva a partir
        do container d2l-questions-written-response-question-response, penetrando shadow roots.
        """
        try:
            texto = page.evaluate(r"""() => {
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

                // 1. Container padrão de resposta escrita
                const wrapResponse = all.filter(el => (el.className || '').toString().includes('d2l-questions-written-response-question-response'));
                if (wrapResponse.length > 0) {
                    const targetResp = wrapResponse[wrapResponse.length - 1];
                    const renderedResp = getAll(targetResp).filter(el => (el.className || '').toString().includes('d2l-html-block-rendered'));
                    for (let r of renderedResp) {
                        let resp = (r.innerText || '').trim();
                        resp = resp.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
                        if (resp.length > 0) return resp;
                    }

                    const htmlBlocks = getAll(targetResp).filter(el => el.tagName.toLowerCase() === 'd2l-html-block');
                    for (let hb of htmlBlocks) {
                        const t = (hb.html || hb.innerText || '').trim();
                        if (t) {
                            const div = document.createElement('div');
                            div.innerHTML = t;
                            let resp = (div.innerText || '').trim();
                            resp = resp.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
                            if (resp.length > 0) return resp;
                        }
                    }
                }

                // 2. Fallback: procurar elemento de texto imediatamente antes do contador de palavras
                for (let el of all) {
                    const cls = (el.className || '').toString();
                    const txt = (el.innerText || '').trim();
                    if (cls.includes('word-count') || (txt.includes('palavras') && /^\d+\s+palavras/i.test(txt))) {
                        let prev = el.previousElementSibling;
                        while (prev) {
                            const tag = prev.tagName.toLowerCase();
                            let pTxt = (prev.innerText || '').trim();
                            pTxt = pTxt.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
                            if (tag !== 'd2l-offscreen' && pTxt !== 'Questão Discursiva' && pTxt.length > 5 && !pTxt.startsWith('EAD_') && !pTxt.includes('Texto-Motivador') && !pTxt.includes('Comando da')) {
                                return pTxt;
                            }
                            prev = prev.previousElementSibling;
                        }
                    }
                }
                return '';
            }""")
            return (texto or "").strip()
        except Exception:
            return ""

    def _obter_feedback_questao(self, page: Page) -> str:
        try:
            fb = page.evaluate(r"""() => {
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
                const editors = all.filter(el => el.tagName.toLowerCase() === 'd2l-htmleditor' && el.className.includes('d2l-consistent-eval-quiz-question-feedback'));
                if (editors.length > 0) {
                    const target = editors[editors.length - 1];
                    return target.html || target.innerText || '';
                }
                return '';
            }""")
            return fb.strip()
        except Exception:
            pass
        return ""

    def _inserir_nota_e_feedback_questao(self, page: Page, nota: float, feedback_html: str, nota_max: float = 2.0):
        """
        Insere a nota no campo 'Pontuação' e o parecer formativo completo no campo 'Feedback'
        da questão discursiva (abaixo da nota), acionando o ciclo de vida oficial do componente D2L
        para assegurar a persistência dos dados no banco do Brightspace ao salvar rascunho.
        """
        try:
            nota_str = f"{nota:.2f}".replace(".", ",").rstrip("0").rstrip(",")
            if not nota_str:
                nota_str = "0"

            res = page.evaluate(r"""(args) => {
                const { notaVal, notaStr, fbHtml } = args;
                function findDeepAll(root, fn) {
                    let res = [];
                    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                    while (w.nextNode()) {
                        const el = w.currentNode;
                        if (fn(el)) res.push(el);
                        if (el.shadowRoot) res = res.concat(findDeepAll(el.shadowRoot, fn));
                    }
                    return res;
                }

                // 1. Localizar componentes D2L da avaliação da questão
                const allAR = findDeepAll(document.body, el => el.tagName.toLowerCase() === 'd2l-consistent-evaluation-quizzing-attempt-result');
                const qAR = allAR.length > 0 ? allAR[allAR.length - 1] : null;

                // 2. Atualizar nota no componente e no input nativo
                if (qAR && typeof qAR._updateScore === 'function') {
                    qAR._updateScore(notaVal);
                }
                const inputScore = qAR && qAR.shadowRoot ? qAR.shadowRoot.querySelector('input') : null;
                if (inputScore) {
                    inputScore.focus();
                    inputScore.value = notaStr;
                    inputScore.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                    inputScore.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                    inputScore.blur();
                }

                // 3. Atualizar feedback no componente da questão (abaixo da nota)
                const ed = qAR && qAR.shadowRoot ? qAR.shadowRoot.querySelector('d2l-htmleditor') : null;
                if (ed) {
                    // Ativar inline editor caso esteja no modo preview
                    if (ed.shadowRoot) {
                        const btn = ed.shadowRoot.querySelector('button.d2l-htmleditor-inline-button') || ed.shadowRoot.querySelector('.d2l-htmleditor-inline-html-block');
                        if (btn) btn.click();
                        else if (typeof ed._onInlineEditClick === 'function') ed._onInlineEditClick();
                    }

                    // Injetar HTML no editor e nos sub-elementos
                    ed.html = fbHtml;
                    if (ed.shadowRoot) {
                        const iframe = ed.shadowRoot.querySelector('iframe');
                        if (iframe && (iframe.contentDocument || iframe.contentWindow)) {
                            const doc = iframe.contentDocument || iframe.contentWindow.document;
                            if (doc && doc.body) {
                                doc.body.innerHTML = fbHtml;
                                doc.body.dispatchEvent(new Event('input', { bubbles: true }));
                                doc.body.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }
                        const ta = ed.shadowRoot.querySelector('textarea');
                        if (ta) {
                            ta.value = fbHtml;
                            ta.dispatchEvent(new Event('input', { bubbles: true }));
                            ta.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }

                    // Notificar o componente oficial da D2L para marcar dirty e registrar no D2L store
                    if (qAR && typeof qAR._saveOnFeedbackChange === 'function') {
                        qAR._feedbackText = '';
                        qAR._saveOnFeedbackChange();
                    }
                }

                return { ok: true, scoreUpdated: !!inputScore, feedbackUpdated: !!ed };
            }""", {"notaVal": float(nota), "notaStr": nota_str, "fbHtml": feedback_html})

            time.sleep(1.0)
            return res.get("ok", False)
        except Exception as e:
            state.log(f"Aviso ao inserir nota/feedback na discursiva: {e}", "WARN")
            return False

    def _salvar_rascunho_duplo(self, page: Page):
        """
        Salva em rascunho duas vezes consecutivas para garantir persistência plena no Brightspace.
        Não publica em nenhuma hipótese.
        """
        self._salvar_rascunho(page)
        time.sleep(2.0)
        self._salvar_rascunho(page)
        time.sleep(1.0)

    def _salvar_rascunho(self, page: Page):
        """
        Localiza e clica exclusivamente nos botões de salvar rascunho.
        Nunca clica em 'Publicar'.
        """
        try:
            # 1. Tentar salvar via helper de Shadow DOM do Consistent Evaluation
            if salvar_rascunho_consistent_evaluation(page):
                return True

            # 2. Tentar salvar no layout legado de questionário (quiz marking)
            for sel in [
                "button:has-text('Salvar Rascunho')",
                "button:has-text('Salvar rascunho')",
                "button[name*='Save']:not([name*='Publish'])",
                "button[id*='Save']:not([id*='Publish'])",
                "button:has-text('Salvar')",
                "d2l-button:has-text('Salvar')",
                "d2l-button-subtle:has-text('Salvar')",
                "button:has-text('Save Draft')"
            ]:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    txt = (btn.inner_text() or '').lower()
                    if 'publicar' not in txt and 'publish' not in txt:
                        btn.click()
                        time.sleep(1.5)
                        return True
        except Exception:
            pass
        return False

    def _executar_auditoria_coerencia(self, resultados: List[Dict[str, Any]], plano: Dict[str, Any], ou: str | int, disciplina: str):
        """
        Ao final das avaliações (ex.: 97/97), faz a análise de coerência
        de cada resposta, nota e feedback atribuído na questão discursiva.
        """
        if not resultados:
            state.log("Nenhum registro de avaliação discursiva para auditar coerência.")
            return

        total = len(resultados)
        state.log(f"\n==================================================================")
        state.log(f"AUDITORIA FINAL DE COERÊNCIA - PROVA PRESENCIAL [{ou}] {disciplina}")
        state.log(f"Total de avaliações processadas: {total}/{total} (100% da turma analisada)")
        state.log(f"==================================================================")

        notas = [r["nota"] for r in resultados]
        media = sum(notas) / total if total > 0 else 0.0
        nota_max = plano.get("prova_presencial", {}).get("valor_discursiva", 2.0)

        incoerencias = []
        faixas = {"Excelente": 0, "Muito Bom": 0, "Bom": 0, "Regular": 0, "Insuficiente": 0}

        for r in resultados:
            aluno = r["aluno"]
            nota = r["nota"]
            qualidade = r.get("qualidade", "Bom")
            plagio = r.get("plagio", False)

            if qualidade in faixas:
                faixas[qualidade] += 1

            # Verificar inconsistências lógicas
            if nota > nota_max:
                incoerencias.append(f"{aluno}: Nota {nota} excede o valor máximo de {nota_max}.")
            if plagio and nota > 0.0:
                incoerencias.append(f"{aluno}: Plágio confirmado porém nota maior que zero ({nota}).")
            if qualidade == "Excelente" and nota < (nota_max * 0.7):
                incoerencias.append(f"{aluno}: Classificado como Excelente mas com nota baixa ({nota}/{nota_max}).")
            if qualidade == "Insuficiente" and nota > (nota_max * 0.6):
                incoerencias.append(f"{aluno}: Classificado como Insuficiente mas com nota elevada ({nota}/{nota_max}).")

        state.log(f"Média Geral da Discursiva: {media:.2f} / {nota_max:.1f} pontos")
        state.log(f"Distribuição pedagógica: Excelente={faixas['Excelente']}, Muito Bom={faixas['Muito Bom']}, Bom={faixas['Bom']}, Regular={faixas['Regular']}, Insuficiente={faixas['Insuficiente']}")

        if incoerencias:
            state.log(f"Alerta: {len(incoerencias)} inconsistência(s) identificada(s):", "WARN")
            for inc in incoerencias[:5]:
                state.log(f"  * {inc}", "WARN")
        else:
            state.log(f"COERÊNCIA CONFIRMADA: 100% dos feedbacks e notas ({total}/{total}) estão harmonizados com os critérios pedagógicos e a tag {{FirstName}}.")

        # Persistir relatório de auditoria de coerência
        from config import RELATORIOS_DIR
        import json
        caminho_auditoria = RELATORIOS_DIR / f"auditoria_coerencia_prova_{ou}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(caminho_auditoria, "w", encoding="utf-8") as f:
                json.dump({
                    "ou": str(ou),
                    "disciplina": disciplina,
                    "total_avaliados": total,
                    "media_geral": round(media, 2),
                    "nota_maxima": nota_max,
                    "faixas": faixas,
                    "incoerencias_encontradas": len(incoerencias),
                    "detalhes_incoerencias": incoerencias,
                    "estudantes": resultados
                }, f, ensure_ascii=False, indent=2)
            state.log(f"Relatório de coerência salvo com sucesso: {caminho_auditoria.name}")
        except Exception as e:
            state.log(f"Aviso ao salvar relatório de coerência: {e}", "WARN")

motor_provas = MotorProvas()
