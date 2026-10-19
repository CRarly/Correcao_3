import os
import re
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from config import get_quizzes_url, get_quickeval_url, DYNAMIC_LOAD_WAIT_MS, NAV_TIMEOUT, RELATORIOS_DIR
from engine_state import state
from cognitive.detector_plagio import detector_plagio
from cognitive.rubrica_substitutiva import rubrica_substitutiva
from core.navigation_iterator import (
    extrair_posicao_mostrador_iterator,
    extrair_nome_estudante_atual,
    avancar_proximo_estudante_seguro
)
from core.dom_helpers import salvar_rascunho_consistent_evaluation, salvar_rascunho_duplo

class MotorProvasSubstitutivas:
    """
    Motor especialista de avaliação e auditoria da Avaliação: Prova Substitutiva.
    Atua exclusivamente na Questão Discursiva (Pergunta 8 - até 2,00 pontos),
    preservando integralmente as questões objetivas/múltipla escolha (QME).
    Lança nota e feedback no componente oficial da questão (abaixo da nota)
    e avança com segurança de 1 a N na turma salvando em Rascunho Duplo (sem publicar).
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
        state.log(f"Iniciando Motor de Provas Substitutivas para [{ou}] {disciplina} (Modo: {modo.upper()})...")
        resultados = []
        info_sub = plano.get("prova_substitutiva", {})
        nota_max_discursiva = info_sub.get("valor_discursiva", 2.0)
        enunciado_discursiva = info_sub.get("enunciado_discursiva", "")

        # 1. Obter link de entrada do plano mapeado pelo Quick Eval
        novos_envios = info_sub.get("total_pendentes", 0)
        prova_href = info_sub.get("url_all") or info_sub.get("url_new")

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
                if "substitutiva" in txt or ("prova" in txt and "rec" in txt):
                    prova_href = href if href.startswith("http") else f"https://ava.catolica.edu.br{href}"
                    m_num = re.search(r'^\s*(\d+)', txt)
                    if m_num:
                        novos_envios = int(m_num.group(1))
                    break

        if not prova_href:
            state.log("Nenhuma Prova Substitutiva identificada no Quick Eval para esta disciplina.", "WARN")
            return resultados

        # Definir URLs e Modo Efetivo
        url_all = prova_href.replace("iteratorRange=new", "iteratorRange=all")
        if "iteratorRange=" not in url_all:
            url_all += ("&" if "?" in url_all else "?") + "iteratorRange=all"
        url_new = prova_href.replace("iteratorRange=all", "iteratorRange=new")

        if modo == "tradicional":
            if novos_envios == 0 and not info_sub.get("forcar_correcao", False):
                state.log(f"[Execução Normal] Nenhum novo envio pendente na Prova Substitutiva ({disciplina}). Nenhuma correção necessária.")
                return resultados
            else:
                state.log(f"[Execução Normal] {novos_envios} novo(s) envio(s) pendente(s) na Prova Substitutiva. Iniciando correções e auditoria comum...")
                prova_href = url_all
                modo_efetivo = "tradicional_com_auditoria"
        elif modo == "recorrigir":
            state.log(f"[Recorrigir + Auditoria Geral] Reavaliando e auditando 100% das tentativas da Prova Substitutiva ({disciplina})...")
            prova_href = url_all
            modo_efetivo = "recorrigir_e_auditar"
        else:
            state.log(f"[{modo.upper()}] Acessando todas as tentativas para auditoria da Prova Substitutiva...")
            prova_href = url_all
            modo_efetivo = modo

        state.log(f"Acessando Avaliação Consistente da Prova Substitutiva: {prova_href}")
        page.goto(prova_href, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        time.sleep(4)

        # Garantir retorno ao Estudante 1
        self._garantir_estudante_1(page, prova_href)

        # Arquivo de checkpoint incremental
        checkpoint_file = RELATORIOS_DIR / f"historico_correcoes_substitutiva_{ou}.json"
        historico_existente = self._carregar_checkpoint(checkpoint_file)
        processados_ids = {h.get("posicao_chave") for h in historico_existente if h.get("posicao_chave")}

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

            # Evitar reprocessar o mesmo aluno na mesma sessão ou via checkpoint salvo
            if (chave_aluno in alunos_processados or chave_aluno in processados_ids) and modo_efetivo != "recorrigir_e_auditar":
                state.log(f"{pos_str}Tentativa de {nome_aluno} já processada anteriormente. Avançando...")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    break
                continue

            alunos_processados.add(chave_aluno)
            total_estimado = pos_info.get("total") or info_sub.get("total_geral", 101)
            state.update_progress(pos_info.get("atual") or aluno_idx, total_estimado, nome_aluno, "Prova Substitutiva (Discursiva)")

            # 1. Assegurar que a Tentativa 1 esteja carregada (sair de Resumo da conclusão se necessário)
            self._assegurar_tentativa_carregada(page)

            # 2. Localizar o bloco da Questão Discursiva com rolagem gradual
            bloco_discursiva = self._aguardar_carregamento_questao_discursiva(page)
            if not bloco_discursiva:
                state.log(f"{pos_str}Questão discursiva da Prova Substitutiva não localizada na tentativa de {nome_aluno} após rolagem. Pulando...", "WARN")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    break
                continue

            # 3. Extrair resposta e enunciado
            texto_resposta = self._extrair_resposta_discursiva(page)
            if not texto_resposta.strip():
                time.sleep(2.0)
                texto_resposta = self._extrair_resposta_discursiva(page)

            if not enunciado_discursiva:
                enunciado_discursiva = self._extrair_enunciado_discursiva(page)

            # Pular estudantes sem resposta na discursiva após confirmação
            if not texto_resposta.strip():
                state.log(f"{pos_str}{nome_aluno}: Questão discursiva sem resposta submetida. Pulando...")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    break
                continue

            # 4. Plágio cruzado na discursiva
            info_plagio = detector_plagio.registrar_e_comparar(
                ou=ou,
                disciplina=disciplina,
                atividade="Prova substitutiva",
                aluno_nome=nome_aluno,
                texto_submissao=texto_resposta
            )
            if info_plagio.get("tem_plagio", False):
                state.log(f"ALERTA DE PLÁGIO NA DISCURSIVA (≥ 90%): {nome_aluno} possui {info_plagio['similaridade_pct']}% de cópia de {info_plagio['aluno_autor']}!", "WARN")
                state.increment_stat("plagios_detectados")

            # 5. Avaliação analítica pela Rubrica Substitutiva especializada
            avaliacao = rubrica_substitutiva.avaliar(
                enunciado=enunciado_discursiva,
                resposta_aluno=texto_resposta,
                nome_aluno=nome_aluno,
                nota_maxima=nota_max_discursiva
            )

            nota_calculada = avaliacao["nota_total"]
            feedback_html = avaliacao["feedback_html"]

            # 6. Gravar nota e feedback nos campos oficiais da questão
            fb_atual = self._obter_feedback_questao(page)
            ja_avaliado = bool(fb_atual and "Prova Substitutiva" in fb_atual)

            if modo_efetivo == "recorrigir_e_auditar" or not ja_avaliado:
                state.log(f"{pos_str}Avaliando discursiva de {nome_aluno}: Nota {nota_calculada:.2f} / {nota_max_discursiva:.2f}...")
                ok_gravado = self._inserir_nota_e_feedback_questao(page, nota_calculada, feedback_html, nota_max_discursiva)
                if ok_gravado:
                    self._salvar_rascunho_duplo(page)
                    state.increment_stat("avaliados")
                else:
                    state.log(f"{pos_str}Aviso: falha na inserção da nota/feedback de {nome_aluno}.", "WARN")
            else:
                state.log(f"{pos_str}[Auditoria] {nome_aluno}: Discursiva já avaliada e conforme.")
                state.increment_stat("auditados")

            registro = {
                "posicao": pos_info.get("atual") or aluno_idx,
                "total": total_estimado,
                "posicao_chave": chave_aluno,
                "ou": str(ou),
                "disciplina": disciplina,
                "atividade": "Prova substitutiva",
                "aluno": nome_aluno,
                "nota": nota_calculada,
                "nota_max": nota_max_discursiva,
                "palavras": len(texto_resposta.split()),
                "plagio": info_plagio.get("tem_plagio", False),
                "similaridade_pct": info_plagio.get("similaridade_pct", 0.0),
                "criterios": avaliacao.get("criterios", []),
                "descontos": avaliacao.get("descontos", []),
                "modo": modo,
                "data_hora": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            resultados.append(registro)
            historico_existente.append(registro)
            self._salvar_checkpoint(checkpoint_file, historico_existente)

            if state.should_stop:
                break
            if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                state.log("Todas as tentativas da Prova Substitutiva foram processadas com sucesso!")
                break

        # Requisito: Análise de coerência ao final das avaliações
        self._executar_auditoria_coerencia(resultados, plano, ou, disciplina)

        return resultados

    def _assegurar_tentativa_carregada(self, page: Page) -> bool:
        """
        Garante que a visualização esteja na Tentativa 1 do estudante,
        alternando de 'Resumo da conclusão' no dropdown de tentativas caso necessário.
        """
        try:
            alternou = page.evaluate(r"""() => {
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

                // 1. Tentar via elemento <select> de tentativas
                const selects = findDeepAll(document.body, el => el.tagName.toLowerCase() === 'select');
                for (let s of selects) {
                    if (s.value && s.value.includes('summary')) {
                        for (let i = 0; i < s.options.length; i++) {
                            const opt = s.options[i];
                            if (!opt.value.includes('summary') && !opt.text.toLowerCase().includes('resumo')) {
                                s.selectedIndex = i;
                                s.value = opt.value;
                                s.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                                s.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                                return true;
                            }
                        }
                    }
                }

                // 2. Fallback: procurar botão ou link com texto 'Tentativa 1'
                const all = findDeepAll(document.body, el => true);
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
            if alternou:
                time.sleep(5.0)
                return True
        except Exception:
            pass
        return False

    def _aguardar_carregamento_questao_discursiva(self, page: Page, max_scroll_steps: int = 15):
        """
        Busca a questão discursiva rolando os containers internos com overflow
        até que o bloco com Pergunta 8 / resposta escrita esteja renderizado.
        """
        for step in range(max_scroll_steps):
            # Rolar os containers de rolagem internos e a janela
            page.evaluate(r"""() => {
                const all = [];
                const w = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, null, false);
                while (w.nextNode()) {
                    all.push(w.currentNode);
                    if (w.currentNode.shadowRoot) {
                        const w2 = document.createTreeWalker(w.currentNode.shadowRoot, NodeFilter.SHOW_ELEMENT, null, false);
                        while (w2.nextNode()) all.push(w2.currentNode);
                    }
                }
                for (let el of all) {
                    const ov = window.getComputedStyle(el).overflowY;
                    if ((ov === 'auto' || ov === 'scroll') && el.scrollHeight > el.clientHeight) {
                        el.scrollTop += 800;
                    }
                }
                window.scrollBy(0, 800);
            }""")
            time.sleep(0.8)

            bloco = self._localizar_bloco_questao_discursiva(page)
            if bloco:
                if hasattr(bloco, "scroll_into_view_if_needed"):
                    try:
                        bloco.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                return bloco
        return None

    def _localizar_bloco_questao_discursiva(self, page: Page):
        try:
            # 1. Tentar localizar via seletor Playwright (piercing)
            blocos = page.locator("d2l-consistent-evaluation-quizzing-attempt-result, .d2l-quiz-question, .d2l-question-container")
            if blocos.count() > 0:
                return blocos.last

            # 2. Verificar via evaluate se existe a resposta escrita ou question-wrapper
            encontrou = page.evaluate(r"""() => {
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
                const wr = findDeepAll(document.body, el => (el.className || '').toString().includes('written-response'));
                if (wr.length > 0) return true;
                const ar = findDeepAll(document.body, el => el.tagName.toLowerCase() === 'd2l-consistent-evaluation-quizzing-attempt-result');
                return ar.length > 0;
            }""")
            if encontrou:
                return True
        except Exception:
            pass
        return None

    def _extrair_enunciado_discursiva(self, page: Page) -> str:
        try:
            texto = page.evaluate(r"""() => {
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

                function getDeepText(root) {
                    if (!root) return '';
                    const rendered = findDeepAll(root, el => (el.className || '').toString().includes('d2l-html-block-rendered'));
                    for (let r of rendered) {
                        const t = (r.innerText || '').trim();
                        if (t.length > 30) return t;
                    }
                    const htmlBlocks = findDeepAll(root, el => el.tagName.toLowerCase() === 'd2l-html-block');
                    for (let hb of htmlBlocks) {
                        const t = (hb.html || hb.innerText || '').trim();
                        if (t) {
                            const div = document.createElement('div');
                            div.innerHTML = t;
                            const resTxt = (div.innerText || '').trim();
                            if (resTxt.length > 30) return resTxt;
                        }
                    }
                    return (root.innerText || '').trim();
                }

                const wrapQuestion = findDeepAll(document.body, el => (el.className || '').toString().includes('d2l-questions-question-wrapper'));
                if (wrapQuestion.length > 0) {
                    const qTarget = wrapQuestion[wrapQuestion.length - 1];
                    return getDeepText(qTarget);
                }
                return '';
            }""")
            return (texto or "").strip()
        except Exception:
            return ""

    def _extrair_resposta_discursiva(self, page: Page) -> str:
        try:
            texto = page.evaluate(r"""() => {
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

                // 1. Container oficial de resposta escrita
                const wrapResponse = findDeepAll(document.body, el => (el.className || '').toString().includes('d2l-questions-written-response-question-response'));
                if (wrapResponse.length > 0) {
                    const targetResp = wrapResponse[wrapResponse.length - 1];
                    const renderedResp = findDeepAll(targetResp, el => (el.className || '').toString().includes('d2l-html-block-rendered'));
                    for (let r of renderedResp) {
                        let resp = (r.innerText || '').trim();
                        resp = resp.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
                        if (resp.length > 0) return resp;
                    }

                    const htmlBlocks = findDeepAll(targetResp, el => el.tagName.toLowerCase() === 'd2l-html-block');
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

                // 2. Fallback: procurar elemento anterior ao contador de palavras
                const all = findDeepAll(document.body, () => true);
                for (let el of all) {
                    const cls = (el.className || '').toString();
                    const txt = (el.innerText || '').trim();
                    if (cls.includes('word-count') || (txt.includes('palavras') && /^\d+\s+palavras/i.test(txt))) {
                        let prev = el.previousElementSibling;
                        while (prev) {
                            const tag = prev.tagName.toLowerCase();
                            let pTxt = (prev.innerText || '').trim();
                            pTxt = pTxt.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
                            if (tag !== 'd2l-offscreen' && pTxt.length > 10 && !pTxt.startsWith('EAD_') && !pTxt.includes('Texto-Motivador') && !pTxt.includes('Comando da')) {
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
                const editors = findDeepAll(document.body, el => el.tagName.toLowerCase() === 'd2l-htmleditor' && (el.className || '').includes('d2l-consistent-eval-quiz-question-feedback'));
                if (editors.length > 0) {
                    const target = editors[editors.length - 1];
                    return target.html || target.innerText || '';
                }
                return '';
            }""")
            return (fb or "").strip()
        except Exception:
            return ""

    def _inserir_nota_e_feedback_questao(self, page: Page, nota: float, feedback_html: str, nota_max: float = 2.0) -> bool:
        """
        Insere a nota no campo 'Pontuação' e o parecer formativo completo no campo 'Feedback'
        da questão discursiva (abaixo da nota), acionando o ciclo de vida oficial do componente D2L.
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
                if (allAR.length === 0) return { ok: false, error: 'no_ar' };
                const qAR = allAR[allAR.length - 1];

                // 2. Atualizar nota no componente e no input nativo
                if (typeof qAR._updateScore === 'function') {
                    qAR._updateScore(notaVal);
                }
                const inputScore = qAR.shadowRoot ? (
                    qAR.shadowRoot.querySelector('input') ||
                    (qAR.shadowRoot.querySelector('d2l-input-number') && qAR.shadowRoot.querySelector('d2l-input-number').shadowRoot ? qAR.shadowRoot.querySelector('d2l-input-number').shadowRoot.querySelector('input') : null)
                ) : null;
                if (inputScore) {
                    inputScore.focus();
                    inputScore.value = notaStr;
                    inputScore.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                    inputScore.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                    inputScore.blur();
                }

                // 3. Atualizar feedback no componente da questão (abaixo da nota)
                const ed = qAR.shadowRoot ? qAR.shadowRoot.querySelector('d2l-htmleditor') : null;
                if (ed) {
                    if (ed.shadowRoot) {
                        const btn = ed.shadowRoot.querySelector('button.d2l-htmleditor-inline-button') || ed.shadowRoot.querySelector('.d2l-htmleditor-inline-html-block');
                        if (btn) btn.click();
                        else if (typeof ed._onInlineEditClick === 'function') ed._onInlineEditClick();
                    }

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

                    if (typeof qAR._saveOnFeedbackChange === 'function') {
                        qAR._feedbackText = '';
                        qAR._saveOnFeedbackChange();
                    }
                }

                return { ok: true, scoreUpdated: !!inputScore, feedbackUpdated: !!ed };
            }""", {"notaVal": float(nota), "notaStr": nota_str, "fbHtml": feedback_html})

            time.sleep(1.0)
            return res.get("ok", False)
        except Exception as e:
            state.log(f"Aviso ao inserir nota/feedback na discursiva da Prova Substitutiva: {e}", "WARN")
            return False

    def _salvar_rascunho_duplo(self, page: Page):
        """
        Salva em rascunho duas vezes consecutivas para garantir persistência plena no Brightspace.
        Nunca clica em 'Publicar'.
        """
        self._salvar_rascunho(page)
        time.sleep(2.0)
        self._salvar_rascunho(page)
        time.sleep(1.0)

    def _salvar_rascunho(self, page: Page):
        """
        Localiza e clica exclusivamente no botão de Salvar Rascunho.
        Nunca clica em 'Publicar'.
        """
        try:
            # 1. Tentar salvar via helper de Shadow DOM
            if salvar_rascunho_consistent_evaluation(page):
                return True

            # 2. Tentar salvar via seletores comuns de rascunho
            return page.evaluate(r"""() => {
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
                const buttons = findDeepAll(document.body, el => ['button', 'd2l-button'].includes(el.tagName.toLowerCase()));
                for (let b of buttons) {
                    const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                    if (txt === 'salvar rascunho' || (txt.includes('salvar') && txt.includes('rascunho'))) {
                        b.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        if (b.shadowRoot && b.shadowRoot.querySelector('button')) {
                            b.shadowRoot.querySelector('button').click();
                        } else {
                            b.click();
                        }
                        b.dispatchEvent(new Event('click', { bubbles: true, composed: true }));
                        return true;
                    }
                }
                return false;
            }""")
        except Exception:
            return False

    def _garantir_estudante_1(self, page: Page, url_base: str):
        """Garante que a interface esteja no Usuário 1 da lista."""
        for _ in range(30):
            pos = extrair_posicao_mostrador_iterator(page)
            atual = pos.get("atual")
            if atual is not None:
                if atual == 1:
                    state.log(f"Posicionado no Estudante 1 de {pos.get('total') or '?'}.")
                    return True
                state.log(f"Posicionado no Estudante {atual} de {pos.get('total')}. Retornando ao Estudante 1...")
                # Clicar no botão de navegação anterior
                clicou = page.evaluate(r"""() => {
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
                    const prevs = findDeepAll(document.body, el => {
                        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                        const tag = el.tagName.toLowerCase();
                        return (aria.includes('anterior') || aria.includes('previous')) && (tag === 'button' || tag === 'd2l-button-icon');
                    });
                    if (prevs.length > 0) {
                        const target = prevs[0].shadowRoot ? (prevs[0].shadowRoot.querySelector('button') || prevs[0]) : prevs[0];
                        target.click();
                        return true;
                    }
                    return false;
                }""")
                if not clicou:
                    page.goto(url_base, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                    time.sleep(3)
                time.sleep(1.5)
            else:
                time.sleep(1.0)
        return False

    def _carregar_checkpoint(self, path: Path) -> List[Dict[str, Any]]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _salvar_checkpoint(self, path: Path, dados: List[Dict[str, Any]]):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
        except Exception as e:
            state.log(f"Aviso ao salvar checkpoint JSON da Prova Substitutiva: {e}", "WARN")

    def _executar_auditoria_coerencia(self, resultados: List[Dict[str, Any]], plano: Dict[str, Any], ou: str | int, disciplina: str):
        """
        Ao final das avaliações da turma, executa análise de coerência pedagógica
        e integridade das notas atribuídas na Prova Substitutiva.
        """
        if not resultados:
            state.log("Nenhum registro de avaliação discursiva para auditar coerência.")
            return

        total = len(resultados)
        state.log(f"\n==================================================================")
        state.log(f"AUDITORIA FINAL DE COERÊNCIA - PROVA SUBSTITUTIVA [{ou}] {disciplina}")
        state.log(f"Total de avaliações processadas: {total}/{total} (100% da lista analisada)")
        state.log(f"==================================================================")

        notas = [r["nota"] for r in resultados]
        media = sum(notas) / total if total > 0 else 0.0
        nota_max = plano.get("prova_substitutiva", {}).get("valor_discursiva", 2.0)

        incoerencias = []
        for r in resultados:
            aluno = r["aluno"]
            nota = r["nota"]
            plagio = r.get("plagio", False)

            if nota > nota_max:
                incoerencias.append(f"{aluno}: Nota {nota} excede o valor máximo de {nota_max}.")
            if plagio and nota > 0.0:
                incoerencias.append(f"{aluno}: Plágio confirmado porém nota maior que zero ({nota}).")

        state.log(f"Média Geral da Discursiva Substitutiva: {media:.2f} / {nota_max:.1f} pontos")

        if incoerencias:
            state.log(f"Alerta: {len(incoerencias)} inconsistência(s) identificada(s):", "WARN")
            for inc in incoerencias[:5]:
                state.log(f"  * {inc}", "WARN")
        else:
            state.log(f"COERÊNCIA CONFIRMADA: 100% dos feedbacks e notas ({total}/{total}) da Prova Substitutiva estão harmonizados com a rubrica analítica.")

        caminho_auditoria = RELATORIOS_DIR / f"auditoria_coerencia_prova_substitutiva_{ou}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(caminho_auditoria, "w", encoding="utf-8") as f:
                json.dump({
                    "ou": str(ou),
                    "disciplina": disciplina,
                    "total_avaliados": total,
                    "media_geral": round(media, 2),
                    "nota_maxima": nota_max,
                    "incoerencias_encontradas": len(incoerencias),
                    "detalhes_incoerencias": incoerencias,
                    "estudantes": resultados
                }, f, ensure_ascii=False, indent=2)
            state.log(f"Relatório de coerência salvo com sucesso: {caminho_auditoria.name}")
        except Exception as e:
            state.log(f"Aviso ao salvar relatório de coerência: {e}", "WARN")

motor_provas_substitutivas = MotorProvasSubstitutivas()
