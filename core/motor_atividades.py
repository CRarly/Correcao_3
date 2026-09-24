import os
import re
import time
import zipfile
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from config import get_dropbox_url, get_quickeval_url, DYNAMIC_LOAD_WAIT_MS, NAV_TIMEOUT
from engine_state import state
from cognitive.extrator_documentos import extrair_texto_documento
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
    obter_nota_e_feedback_consistent_evaluation,
    remover_nota_e_feedback_consistent_evaluation,
    contar_anexos_submissao
)
from core.browser_session import obter_primeiro_nome_docente

class MotorAtividades:
    """
    Motor especialista de avaliação e auditoria para a Atividade Aberta.
    Implementa métrica pedagógica própria baseada no comando e instruções da atividade:
    - Critério 1: Conformidade Estrutural e Atendimento às Diretrizes (~30%)
    - Critério 2: Desenvolvimento Teórico-Prático e Resolução do Comando (~50%)
    - Critério 3: Rigor Conceitual, Coesão e Norma Culta (~20%)
    - Regras de nota zero: sem envio / -Nenhum texto inserido- ou fuga ao tema.
    - Justificativas qualitativas transparentes sem subtrações numéricas no texto.
    - Duplo salvamento em rascunho e sem assinatura docente.
    """

    def gerar_criterios_atividade(self, instrucoes: str, nota_maxima: float = 1.5) -> Dict[str, Any]:
        """
        Analisa as instruções da Atividade Aberta e monta a matriz de critérios analíticos pré-estabelecidos:
        - Critério 1: Conformidade Estrutural e Atendimento às Diretrizes (~30%)
        - Critério 2: Desenvolvimento Teórico-Prático e Resolução do Comando (~50%)
        - Critério 3: Rigor Conceitual, Coesão e Norma Culta (~20%)
        """
        peso_estrutural = round(nota_maxima * 0.30, 2)
        peso_resolucao = round(nota_maxima * 0.50, 2)
        peso_rigor = round(nota_maxima - peso_estrutural - peso_resolucao, 2)

        criterios = {
            "nota_maxima": nota_maxima,
            "peso_estrutural": peso_estrutural,
            "peso_resolucao": peso_resolucao,
            "peso_rigor": peso_rigor,
            "criterios": [
                {
                    "id": "criterio_1_estrutural",
                    "nome": "Conformidade Estrutural e Atendimento às Diretrizes",
                    "peso": peso_estrutural,
                    "descricao": "Organização do trabalho, estrutura da entrega, observância ao modelo/formato exigido e adequação da extensão.",
                    "regras_desconto": [
                        {"faixa": "Pleno", "nota": peso_estrutural, "descricao": "Estrutura completa, bem organizada e em plena conformidade com as diretrizes e modelo."},
                        {"faixa": "Parcial", "nota": round(peso_estrutural * 0.5, 2), "descricao": "Estrutura básica ou ausência parcial de elementos orientadores do modelo."},
                        {"faixa": "Insuficiente", "nota": 0.0, "descricao": "Não seguiu o modelo proposto ou entrega desestruturada."}
                    ]
                },
                {
                    "id": "criterio_2_resolucao",
                    "nome": "Desenvolvimento Teórico-Prático e Resolução do Comando",
                    "peso": peso_resolucao,
                    "descricao": "Resolução integral das questões propostas nas instruções, profundidade analítica, aplicação prática e atendimento ao objetivo pedagógico.",
                    "regras_desconto": [
                        {"faixa": "Pleno", "nota": peso_resolucao, "descricao": "Resolução completa e aprofundada de todas as etapas e questões solicitadas."},
                        {"faixa": "Parcial", "nota": round(peso_resolucao * 0.5, 2), "descricao": "Resolução parcial das questões ou abordagem com lacunas em pontos-chave do comando."},
                        {"faixa": "Insuficiente", "nota": 0.0, "descricao": "Não resolveu o comando proposto ou abordagem superficial/fuga ao tema."}
                    ]
                },
                {
                    "id": "criterio_3_rigor",
                    "nome": "Rigor Conceitual, Coesão e Norma Culta",
                    "peso": peso_rigor,
                    "descricao": "Uso correto do vocabulário técnico da disciplina, clareza expositiva, coerência textual e atendimento à norma culta.",
                    "regras_desconto": [
                        {"faixa": "Pleno", "nota": peso_rigor, "descricao": "Vocabulário técnico apropriado, articulação fluida e excelente domínio gramatical."},
                        {"faixa": "Parcial", "nota": round(peso_rigor * 0.6, 2), "descricao": "Compreensível, mas com desvios pontuais de norma culta ou concisão excessiva."},
                        {"faixa": "Insuficiente", "nota": 0.0, "descricao": "Inconsistências conceituais severas ou fragmentação textual."}
                    ]
                }
            ]
        }
        return criterios

    def avaliar_estudante_atividade(
        self,
        texto_submissao: str,
        nome_aluno: str,
        instrucoes: str,
        criterios_info: Dict[str, Any],
        nota_maxima: float = 1.5,
        total_arqs: int = 1,
        docente: str = "Prof. Avaliador"
    ) -> Dict[str, Any]:
        """
        Avalia a submissão da Atividade Aberta segundo a matriz analítica:
        - Critério 1: Conformidade Estrutural (~30%)
        - Critério 2: Desenvolvimento Teórico-Prático e Resolução do Comando (~50%)
        - Critério 3: Rigor Conceitual, Coesão e Norma Culta (~20%)
        - Regra de nota zero: sem envio / -Nenhum texto inserido- ou fuga ao tema.
        - Justificativas qualitativas sem subtrações numéricas no texto (ex: sem '(-0.45 pts)').
        - Sempre inicia com "Olá, {FirstName}!" e encerra com "Atenciosamente, Prof. [Primeiro nome]".
        """
        primeiro_nome_docente = obter_primeiro_nome_docente(docente)
        texto = (texto_submissao or "").strip()
        palavras = len(re.findall(r"\b\w+\b", texto))
        texto_lower = texto.lower()
        letras_count = len(re.findall(r"[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]", texto))

        # 1. Checagem de envio em branco, ausência ou '-Nenhum texto inserido-'
        is_vazio = (
            (total_arqs == 0 and palavras < 5)
            or "nenhum texto inserido" in texto_lower
            or "-nenhum texto inserido-" in texto_lower
            or (palavras < 5 and letras_count < 15)
        )

        if is_vazio:
            motivo_branco = "Não houve submissão de arquivo ou texto para a atividade aberta (-Nenhum texto inserido-)."
            feedback_html = (
                f"<p>Olá, {{FirstName}}!</p>"
                f"<p>Sua entrega para a <strong>Atividade Aberta</strong> foi avaliada com a pontuação de <strong>0,00 de {nota_maxima:.2f} pontos</strong>.</p>"
                f"<p><strong>Motivos do não atingimento da totalidade da nota:</strong></p>"
                f"<ul><li>{motivo_branco}</li></ul>"
                f"<p>Continue se dedicando aos estudos e articulando a teoria com a prática da disciplina. Conte com o apoio docente!</p>"
                f"<p>Atenciosamente, Prof. {primeiro_nome_docente}</p>"
            )
            return {
                "nota": 0.0,
                "nota_max": nota_maxima,
                "qualidade": "Insuficiente",
                "descontos": [motivo_branco],
                "feedback_html": feedback_html,
                "plagio": False,
                "similaridade_pct": 0.0
            }

        # 2. Extração de radicais conceituais das instruções oficiais
        def _extrair_radicais(txt: str) -> set:
            words = re.findall(r"\b[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]{4,}\b", (txt or "").lower())
            rads = set()
            for w in words:
                w_base = re.sub(r"(ções|ção|ões|ão|mente|ades|ade|ais|eis|res|dor|dores|mentos|mento|ados|adas|ado|ada|idos|idas|ido|ida|ando|endo|indo|aram|eram|iram|arem|erem|irem|avam|ariam|eriam|iriam|as|es|is|os|s)$", "", w)
                rads.add(w_base if len(w_base) >= 4 else w[:4])
            return rads

        stopwords_rad = {
            "para", "como", "pelo", "pela", "onde", "quando", "sobr", "entr", "est", "muit",
            "mais", "qual", "quais", "dev", "alun", "respost", "questa", "expliqu", "apresent",
            "disciplin", "com", "sem", "por", "que", "ess", "aquil", "voc", "sua", "seus", "suas",
            "ativid", "abert", "trabalh", "envi", "arquiv", "model", "format"
        }
        rads_instrucoes = _extrair_radicais(instrucoes) - stopwords_rad
        rads_aluno = _extrair_radicais(texto)
        intersecao = rads_aluno & rads_instrucoes

        # 3. Checagem de Fuga ao Tema
        if len(intersecao) == 0 and len(rads_instrucoes) > 0:
            motivo_fuga = "O conteúdo submetido não correspondeu com a proposta e os comandos solicitados nas instruções da atividade (fuga ao tema)."
            feedback_html = (
                f"<p>Olá, {{FirstName}}!</p>"
                f"<p>Sua entrega para a <strong>Atividade Aberta</strong> foi avaliada com a pontuação de <strong>0,00 de {nota_maxima:.2f} pontos</strong>.</p>"
                f"<p><strong>Motivos do não atingimento da totalidade da nota:</strong></p>"
                f"<ul><li>{motivo_fuga}</li></ul>"
                f"<p>Continue se dedicando aos estudos e articulando a teoria com a prática da disciplina. Conte com o apoio docente!</p>"
                f"<p>Atenciosamente, Prof. {primeiro_nome_docente}</p>"
            )
            return {
                "nota": 0.0,
                "nota_max": nota_maxima,
                "qualidade": "Insuficiente",
                "descontos": [motivo_fuga],
                "feedback_html": feedback_html,
                "plagio": False,
                "similaridade_pct": 0.0
            }

        # 4. Avaliação Analítica Multicritério
        if not criterios_info or "criterios" not in criterios_info:
            criterios_info = self.gerar_criterios_atividade(instrucoes, nota_maxima)

        p_estrutural = criterios_info.get("peso_estrutural", round(nota_maxima * 0.30, 2))
        p_resolucao = criterios_info.get("peso_resolucao", round(nota_maxima * 0.50, 2))
        p_rigor = criterios_info.get("peso_rigor", round(nota_maxima - p_estrutural - p_resolucao, 2))

        c1_nome = criterios_info["criterios"][0]["nome"]
        c2_nome = criterios_info["criterios"][1]["nome"]
        c3_nome = criterios_info["criterios"][2]["nome"]

        descontos = []

        # Critério 1: Conformidade Estrutural
        if total_arqs >= 1 and palavras >= 100:
            nota_c1 = p_estrutural
            c1_parecer = "Estrutura do trabalho adequada, com boa organização e atendimento às orientações de entrega."
        elif total_arqs >= 1 and palavras >= 40:
            nota_c1 = round(p_estrutural * 0.70, 2)
            c1_parecer = "Estrutura básica apresentada, mas com desenvolvimento sucinto em relação à extensão esperada para a atividade."
            descontos.append("Estrutura ou extensão concisa: aprofunde a organização e o detalhamento das seções do documento.")
        else:
            nota_c1 = round(p_estrutural * 0.40, 2)
            c1_parecer = "Entrega com lacunas estruturais significativas frente às diretrizes propostas."
            descontos.append("Lacunas estruturais: o documento não observou plenamente o formato ou extensão recomendada para a atividade.")

        # Critério 2: Desenvolvimento Teórico-Prático e Resolução do Comando
        meta_termos = max(2, min(len(rads_instrucoes) * 0.4, 6))
        cobertura = min(1.0, max(0.0, len(intersecao) / meta_termos)) if meta_termos > 0 else 0.70

        if cobertura >= 0.85:
            nota_c2 = p_resolucao
            c2_parecer = "Desenvolvimento consistente e aprofundado, atendendo com precisão aos comandos e desafios propostos nas instruções."
        elif cobertura >= 0.50:
            nota_c2 = round(p_resolucao * 0.70, 2)
            c2_parecer = "Desenvolvimento satisfatório dos tópicos centrais, porém com abordagem parcial em determinados aspectos práticos ou analíticos do comando."
            descontos.append("Resolução parcial do comando: determinados tópicos ou análises solicitadas nas instruções foram abordados de maneira introdutória.")
        else:
            nota_c2 = round(p_resolucao * 0.40, 2)
            c2_parecer = "Abordagem superficial das tarefas e questões requeridas no comando da atividade."
            descontos.append("Abordagem superficial: os comandos centrais da atividade foram apenas tangenciados, necessitando de maior fundamentação analítica.")

        # Critério 3: Rigor Conceitual, Coesão e Norma Culta
        conectivos = sum(1 for c in ["portanto", "contudo", "entretanto", "além disso", "nesse sentido", "assim sendo", "desta forma", "por conseguinte"] if c in texto_lower)
        if palavras >= 80 and (conectivos >= 1 or cobertura >= 0.60):
            nota_c3 = p_rigor
            c3_parecer = "Vocabulário técnico apropriado, redação fluida, coesa e em conformidade com a norma culta."
        elif palavras >= 40:
            nota_c3 = round(p_rigor * 0.65, 2)
            c3_parecer = "Clareza expositiva adequada, com pequenas oportunidades de aprimoramento no vocabulário técnico e na coesão argumentativa."
            descontos.append("Ajuste no rigor conceitual e redação: polir o uso dos termos técnicos e a articulação entre os parágrafos.")
        else:
            nota_c3 = round(p_rigor * 0.35, 2)
            c3_parecer = "Texto com fragmentação argumentativa ou limitações na aplicação da norma padrão e terminologia técnica."
            descontos.append("Fragilidade na articulação textual: utilize vocabulário técnico mais rigoroso e estruture com mais clareza os parágrafos.")

        # 5. Cálculo Final da Nota
        nota_total = round(nota_c1 + nota_c2 + nota_c3, 2)
        nota_total = round(nota_total * 20) / 20  # Múltiplos de 0.05
        nota_total = min(nota_maxima, max(0.0, nota_total))

        if nota_total < nota_maxima and not descontos:
            descontos.append("Aprofundamento analítico: para alcance da pontuação integral, desenvolva com maior abrangência e riqueza de detalhes a resolução das etapas da atividade.")

        # Remoção estrita de valores numéricos nos descontos
        descontos_limpos = [re.sub(r"\s*\(-?\d+[\.,]?\d*\s*pts?\)", "", d).strip() for d in descontos]

        # 6. Formatação do Feedback HTML
        nota_str = f"{nota_total:.2f}".replace(".", ",")
        fb_parts = [
            "<p>Olá, {FirstName}!</p>",
            f"<p>Sua entrega para a <strong>Atividade Aberta</strong> foi avaliada com a pontuação de <strong>{nota_str} de {nota_maxima:.2f} pontos</strong>.</p>",
            "<p><strong>Análise Detalhada dos Critérios:</strong></p>",
            "<ul>",
            f"<li><strong>{c1_nome}:</strong> {c1_parecer}</li>",
            f"<li><strong>{c2_nome}:</strong> {c2_parecer}</li>",
            f"<li><strong>{c3_nome}:</strong> {c3_parecer}</li>",
            "</ul>"
        ]

        if descontos_limpos:
            fb_parts.append("<p><strong>Justificativa do Desconto de Nota:</strong></p>")
            fb_parts.append("<ul>")
            for d in descontos_limpos:
                fb_parts.append(f"<li>{d}</li>")
            fb_parts.append("</ul>")

        fb_parts.append("<p>Continue se dedicando aos estudos e articulando a teoria com a prática da disciplina. Conte com o apoio docente!</p>")
        fb_parts.append(f"<p>Atenciosamente, Prof. {primeiro_nome_docente}</p>")
        feedback_html = "".join(fb_parts)

        qualidade = "Excelente" if nota_total >= (nota_maxima * 0.85) else "Bom" if nota_total >= (nota_maxima * 0.70) else "Regular" if nota_total >= (nota_maxima * 0.50) else "Insuficiente"

        return {
            "nota": nota_total,
            "nota_max": nota_maxima,
            "qualidade": qualidade,
            "descontos": descontos_limpos,
            "feedback_html": feedback_html,
            "plagio": False,
            "similaridade_pct": 0.0
        }

    def executar(
        self,
        page: Page,
        ou: str | int,
        disciplina: str,
        modo: str,
        plano: Dict[str, Any],
        docente: str,
        temp_dir: Path
    ) -> List[Dict[str, Any]]:
        state.log(f"Iniciando Motor de Atividades Abertas para [{ou}] {disciplina} (Modo: {modo.upper()})...")
        resultados = []
        nota_maxima = plano.get("atividade_aberta", {}).get("valor", 1.5)
        instrucoes = plano.get("atividade_aberta", {}).get("instrucoes", "")

        # Gerar critérios analíticos pré-estabelecidos da atividade
        criterios_info = self.gerar_criterios_atividade(instrucoes, nota_maxima)
        state.log(f"[Atividade Aberta] Critérios definidos: Conformidade Estrutural ({criterios_info['peso_estrutural']:.2f} pts), Resolução do Comando ({criterios_info['peso_resolucao']:.2f} pts), Rigor Conceitual ({criterios_info['peso_rigor']:.2f} pts).")

        # 1. Obter link de entrada do plano mapeado pelo Quick Eval
        ativ_info = plano.get("atividade_aberta", {})
        novos_envios = ativ_info.get("total_pendentes", 0)
        ativ_href = ativ_info.get("url_all") or ativ_info.get("url_new")

        # Fallback de busca no Quick Eval se url não estiver no plano
        if not ativ_href:
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
                if "atividade" in txt or "envios" in txt or "anexar tarefas" in txt:
                    ativ_href = href if href.startswith("http") else f"https://ava.catolica.edu.br{href}"
                    m_num = re.search(r'^\s*(\d+)', txt)
                    if m_num:
                        novos_envios = int(m_num.group(1))
                    break

        if not ativ_href:
            # Fallback adicional: tentar entrar pela pasta do Dropbox
            url_dropbox = get_dropbox_url(ou)
            page.goto(url_dropbox, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3)
            folder_link = page.locator("a[href*='folder_submissions_users.d2l']").first
            if folder_link.count() > 0:
                folder_link.click()
                time.sleep(3)
                btn_avaliar = page.locator("a:has-text('Avaliar'), [aria-label*='Avaliar']").first
                if btn_avaliar.count() > 0:
                    btn_avaliar.click()
                    time.sleep(4)
                    ativ_href = page.url

        if not ativ_href:
            state.log("Não foi possível localizar o ponto de entrada da Atividade Aberta.", "WARN")
            return resultados

        # Definir URLs e Modo Efetivo
        url_all = ativ_href.replace("iteratorRange=new", "iteratorRange=all")
        if "iteratorRange=" not in url_all:
            url_all += ("&" if "?" in url_all else "?") + "iteratorRange=all"
        url_new = ativ_href.replace("iteratorRange=all", "iteratorRange=new")

        if modo == "tradicional":
            if novos_envios == 0:
                state.log(f"[Execução Normal] Nenhum novo envio pendente na Atividade Aberta ({disciplina}). Nenhuma correção necessária.")
                return resultados
            else:
                state.log(f"[Execução Normal] {novos_envios} novo(s) envio(s) pendente(s) na Atividade Aberta. Iniciando correções e auditoria comum...")
                ativ_href = url_all
                modo_efetivo = "tradicional_com_auditoria"
        elif modo == "recorrigir":
            state.log(f"[Recorrigir + Auditoria Geral] Reavaliando e auditando 100% dos estudantes da Atividade Aberta ({disciplina})...")
            ativ_href = url_all
            modo_efetivo = "recorrigir_e_auditar"
        else:
            state.log(f"[{modo.upper()}] Acessando todos os estudantes para auditoria...")
            ativ_href = url_all
            modo_efetivo = modo

        state.log(f"Acessando Avaliação Consistente da Atividade Aberta: {ativ_href}")
        page.goto(ativ_href, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
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
                state.log(f"Aluno {nome_aluno} já processado na Atividade. Avançando...")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    break
                continue

            alunos_processados.add(chave_aluno)
            total_estimado = pos_info.get("total") or plano.get("atividade_aberta", {}).get("total_geral", 10)
            state.update_progress(pos_info.get("atual") or aluno_idx, total_estimado, nome_aluno, "Atividade Aberta")

            # 3. Aguardar carregamento completo do painel de submissões
            tem_submissao = self._aguardar_carregamento_submissoes(page)
            
            # Tenta sempre o download e extração de arquivos para garantir que nenhum anexo seja ignorado
            total_arqs, texto_submissoes = self._baixar_e_extrair_arquivos(page, temp_dir, aluno_idx)

            # Pular estudantes se não houver qualquer envio após o carregamento completo
            if total_arqs == 0 and not texto_submissoes.strip():
                if tem_submissao:
                    # Havia indicador de envio mas download retornou vazio: tentar novamente
                    time.sleep(2.0)
                    total_arqs, texto_submissoes = self._baixar_e_extrair_arquivos(page, temp_dir, aluno_idx)

            # Verificar se realmente não há submissão (total_arqs == 0 e texto em branco ou sem envio)
            texto_limpo = (texto_submissoes or "").strip().lower()
            sem_envio = (total_arqs == 0 and (not texto_limpo or "nenhum texto inserido" in texto_limpo or len(texto_limpo) < 15))

            if sem_envio:
                state.log(f"{pos_str}{nome_aluno}: Sem submissões na Atividade Aberta (-Nenhum texto inserido-).")
                
                # Verificar se já possui nota 0 ou comentário prévio
                dados_atuais = obter_nota_e_feedback_consistent_evaluation(page)
                nota_previa = dados_atuais.get("nota")
                feedback_previo = dados_atuais.get("feedback", "")

                tem_nota_zero_ou_fb = False
                if nota_previa is not None and str(nota_previa).strip() != "":
                    try:
                        val = float(str(nota_previa).replace(",", "."))
                        if val == 0.0:
                            tem_nota_zero_ou_fb = True
                    except Exception:
                        pass
                if feedback_previo and len(feedback_previo.strip()) > 0:
                    tem_nota_zero_ou_fb = True

                if tem_nota_zero_ou_fb:
                    state.log(f"{pos_str}{nome_aluno}: Nota 0 ou comentário prévio detectado em estudante sem submissão. Removendo nota e comentário e salvando rascunho...")
                    remover_nota_e_feedback_consistent_evaluation(page)
                    time.sleep(1.0)
                    self._salvar_rascunho(page)
                    time.sleep(1.5)
                    self._salvar_rascunho(page)
                    state.log(f"{pos_str}{nome_aluno}: Rascunho salvo com nota e feedback limpos.")

                state.log(f"{pos_str}{nome_aluno}: Estudante sem submissão pulado conforme diretriz operacional.")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    state.log("Fim da lista de estudantes da Atividade alcançado.")
                    break
                continue

            state.log(f"{pos_str}{nome_aluno}: Submissão identificada e analisada ({total_arqs} anexo(s)). Temporários excluídos.")

            # Avaliação analítica com a matriz pedagógica pré-estabelecida
            diag = self.avaliar_estudante_atividade(
                texto_submissao=texto_submissoes,
                nome_aluno=nome_aluno,
                instrucoes=instrucoes,
                criterios_info=criterios_info,
                nota_maxima=nota_maxima,
                total_arqs=total_arqs,
                docente=docente
            )

            nota_calculada = diag["nota"]
            feedback_html = diag["feedback_html"]
            state.log(f"{pos_str}{nome_aluno}: Nota atribuída = {nota_calculada:.2f} / {nota_maxima:.2f} (Conceito: {diag['qualidade']})")

            # Em modo tradicional com auditoria, se já possuir avaliação anterior, mantém e audita
            fb_atual = self._obter_feedback_atual(page)
            if modo_efetivo == "tradicional_com_auditoria" and fb_atual.strip():
                state.log(f"{pos_str}[Execução Normal] {nome_aluno}: Já possui avaliação registrada. Conforme.")
                state.increment_stat("auditados")
            else:
                # Inserir nota e feedback no Consistent Evaluation
                self._inserir_nota_e_feedback(page, nota_calculada, feedback_html)
                time.sleep(1.5)

                # Persistência obrigatória: SALVAR EM RASCUNHO DUAS VEZES (NUNCA PUBLICAR)
                state.log(f"{pos_str}Salvando avaliação em rascunho (1ª persistência)...")
                self._salvar_rascunho(page)
                time.sleep(2.0)
                state.log(f"{pos_str}Confirmando salvamento em rascunho (2ª persistência)...")
                self._salvar_rascunho(page)
                time.sleep(0.5)

                state.increment_stat("avaliados")

            registro = {
                "ou": str(ou),
                "disciplina": disciplina,
                "atividade": "Atividade aberta",
                "aluno": nome_aluno,
                "nota": nota_calculada,
                "nota_max": nota_maxima,
                "plagio": False,
                "similaridade_pct": 0.0,
                "qualidade": diag.get("qualidade", "Bom"),
                "modo": modo,
                "descontos": diag.get("descontos", [])
            }
            resultados.append(registro)

            if state.should_stop:
                break
            if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                state.log("Todos os envios da Atividade Aberta foram concluídos com sucesso!")
                break

        return resultados

    def _aguardar_carregamento_submissoes(self, page: Page, max_wait_sec: float = 7.0) -> bool:
        """
        Aguarda ativamente o carregamento do painel de arquivos/submissões no Consistent Evaluation e Shadow DOM.
        Retorna True se há evidência de envio (arquivos, botão de download geral, viewer ou comentários),
        ou False se confirmado sem envios.
        """
        start_time = time.time()
        min_wait = 2.5

        while time.time() - start_time < max_wait_sec:
            tem_envio = page.evaluate("""() => {
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

                // 1. Procurar botão de download geral
                for (let el of all) {
                    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                    const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (txt.includes('download de todos') || aria.includes('download de todos') || txt.includes('todos os arquivos')) {
                        return true;
                    }
                }

                // 2. Procurar links ou itens de anexo
                for (let el of all) {
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    const href = (el.getAttribute('href') || '').toLowerCase();
                    const cls = (el.className ? el.className.toString() : '').toLowerCase();
                    const tag = el.tagName.toLowerCase();

                    if (aria.includes('baixar o anexo') || aria.includes('clique para baixar') || 
                        href.includes('downloadattachment') || href.includes('download_submission_file') || 
                        href.includes('viewfile') || href.includes('download') ||
                        cls.includes('attachment') || tag.includes('attachment') || tag === 'd2l-file-name') {
                        return true;
                    }
                }

                // 3. Procurar documento no visualizador (PDF.js / iframe)
                const docText = document.querySelectorAll('.textLayer span, [class*="document-text"], iframe[title*="Document"]');
                if (docText.length > 0) return true;

                // 4. Procurar comentários de submissão do estudante
                const comments = document.querySelectorAll('.d2l-html-editor-content, .d2l-submission-comments, d2l-consistent-evaluation-submission-item');
                for (let c of comments) {
                    const txt = (c.innerText || c.textContent || '').trim();
                    if (txt.length > 20 && !txt.includes('Sua sessão')) return true;
                }

                return false;
            }""")

            # Verificar também dentro de frames
            if not tem_envio:
                for frame in page.frames:
                    try:
                        f_envio = frame.evaluate("""() => {
                            const links = document.querySelectorAll("a[href*='downloadAttachment'], a[href*='download_submission_file'], a[href*='download'], a[href*='ViewFile'], .d2l-file-attachment-text a");
                            if (links.length > 0) return true;
                            const text = (document.body.innerText || '').trim();
                            return text.length > 50 && !text.includes('Sua sessão');
                        }""")
                        if f_envio:
                            tem_envio = True
                            break
                    except Exception:
                        pass

            if tem_envio:
                return True

            # Checar se ainda há spinners de carregamento ativos
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
                sem_envio = page.evaluate("""() => {
                    const text = (document.body.innerText || '').toLowerCase();
                    return text.includes('nenhum envio') || 
                           text.includes('sem envios') || 
                           text.includes('nenhum arquivo') || 
                           text.includes('no submissions') ||
                           text.includes('não foram encontrados envios') ||
                           text.includes('não há envios para este');
                }""")
                if sem_envio:
                    return False

            time.sleep(0.5)

        return False

    def _baixar_e_extrair_arquivos(self, page: Page, temp_dir: Path, idx: int) -> tuple[int, str]:
        """
        Localiza e baixa os arquivos anexados pelo aluno em QUALQUER rota de correção (Quick Eval, Dropbox ou frame).
        Descompacta .zip, extrai texto com extrair_texto_documento e exclui os temporários do disco imediatamente.
        Garante contagem fidedigna dos anexos a partir da interface e do conteúdo extraído.
        """
        anexos_tela = contar_anexos_submissao(page)
        arquivos_salvos = []
        textos = []
        nomes_arquivos = set()

        # 1. Rota A: Botão geral 'Fazer o download de todos os arquivos' (na página ou frames)
        for target_ctx in [page] + page.frames:
            try:
                btn_all = target_ctx.locator("button:has-text('Fazer o download de todos os arquivos'), d2l-button-subtle:has-text('download'), [text*='download de todos'], [aria-label*='download de todos']").first
                if btn_all.count() > 0:
                    try:
                        with page.expect_download(timeout=6000) as download_info:
                            btn_all.click(timeout=3000)
                        download = download_info.value
                        zip_dest = temp_dir / f"aluno_{idx}_{download.suggested_filename}"
                        download.save_as(str(zip_dest))
                        arquivos_salvos.append(zip_dest)
                        if str(zip_dest).lower().endswith(".zip"):
                            try:
                                with zipfile.ZipFile(zip_dest, 'r') as z:
                                    z.extractall(temp_dir)
                                    for nome in z.namelist():
                                        extraido = temp_dir / nome
                                        if extraido.is_file():
                                            arquivos_salvos.append(extraido)
                            except Exception:
                                pass
                        break
                    except Exception:
                        pass
            except Exception:
                pass

        # 2. Rota B: Links ou botões individuais de download de anexos (na página principal e frames)
        if not arquivos_salvos:
            for target_ctx in [page] + page.frames:
                try:
                    file_elements = target_ctx.locator("[aria-label*='Clique para baixar o anexo'], [aria-label*='baixar o anexo'], [aria-label*='baixar'], a.truncate, a[href*='downloadAttachment'], a[href*='download_submission_file'], a[href*='dropbox'], d2l-file-name, .d2l-submission-attachment-list-item-content a, a[download]")
                    count = min(file_elements.count(), 8)
                    for k in range(count):
                        link = file_elements.nth(k)
                        try:
                            with page.expect_download(timeout=4000) as download_info:
                                link.click(timeout=2500)
                            download = download_info.value
                            destino = temp_dir / f"aluno_{idx}_{download.suggested_filename}"
                            download.save_as(str(destino))
                            arquivos_salvos.append(destino)
                            if str(destino).lower().endswith(".zip"):
                                try:
                                    with zipfile.ZipFile(destino, 'r') as z:
                                        z.extractall(temp_dir)
                                        for nome in z.namelist():
                                            extraido = temp_dir / nome
                                            if extraido.is_file():
                                                arquivos_salvos.append(extraido)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    if arquivos_salvos:
                        break
                except Exception:
                    pass

        # 3. Rota C: Tentar menus contextuais / dropdowns com opção 'Baixar'
        if not arquivos_salvos:
            try:
                menu_baixar = page.locator("d2l-menu-item:has-text('Baixar'), d2l-menu-item[aria-label*='Baixar']").first
                if menu_baixar.count() > 0:
                    try:
                        with page.expect_download(timeout=4000) as download_info:
                            menu_baixar.click(timeout=2000)
                        download = download_info.value
                        destino = temp_dir / f"aluno_{idx}_{download.suggested_filename}"
                        download.save_as(str(destino))
                        arquivos_salvos.append(destino)
                    except Exception:
                        pass
            except Exception:
                pass

        # 4. Analisar detalhadamente o conteúdo de todos os arquivos descarregados
        for arq in arquivos_salvos:
            if arq.is_file() and not arq.name.lower().endswith(('.zip', '.tar', '.gz')):
                if arq.name in nomes_arquivos:
                    continue
                nomes_arquivos.add(arq.name)
                res = extrair_texto_documento(arq)
                if res["sucesso"] and res["texto"]:
                    textos.append(res["texto"])

        # 5. Rota D: Complemento / Fallback com leitura da camada de texto do Document Viewer na tela
        try:
            viewer_text = page.evaluate("""() => {
                let text = "";
                const spans = document.querySelectorAll('.textLayer span, span[role="presentation"], [class*="document-text"], [class*="page-content"]');
                for (let s of spans) {
                    const t = (s.innerText || s.textContent || '').trim();
                    if (t) text += t + " ";
                }
                if (text.length > 50) return text;
                for (let ifr of document.querySelectorAll('iframe')) {
                    try {
                        const doc = ifr.contentDocument || ifr.contentWindow.document;
                        if (doc && doc.body) {
                            const t = (doc.body.innerText || '').trim();
                            if (t.length > 50) return t;
                        }
                    } catch(e) {}
                }
                return text;
            }""")
            if viewer_text and len(viewer_text.strip()) > 30 and not any(viewer_text[:50] in t for t in textos):
                textos.append(viewer_text.strip())
        except Exception:
            pass

        # 6. Rota E: Ler comentários de submissão do aluno
        comentarios = self._extrair_comentarios_submissao(page)
        if comentarios and comentarios not in textos:
            textos.append(comentarios)

        # 7. EXCLUSÃO IMEDIATA DOS ARQUIVOS TEMPORÁRIOS BAIXADOS DO DISCO
        for f in temp_dir.glob("*"):
            try:
                if f.is_file():
                    f.unlink()
                elif f.is_dir():
                    shutil.rmtree(f, ignore_errors=True)
            except Exception:
                pass

        total_encontrados = len(anexos_tela) if anexos_tela else max(len(nomes_arquivos), 1 if len(textos) > 0 else 0)
        return total_encontrados, "\n\n".join(textos)

    def _extrair_comentarios_submissao(self, page: Page) -> str:
        try:
            return page.evaluate("""() => {
                const els = document.querySelectorAll('.d2l-html-editor-content, .d2l-submission-comments, d2l-html-block');
                for (let el of els) {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (t.length > 20 && !t.includes('Sua sessão')) return t;
                }
                return '';
            }""")
        except Exception:
            return ""

    def _extrair_texto_direto_submissao(self, page: Page) -> str:
        return self._extrair_comentarios_submissao(page)

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
            state.log(f"Aviso ao lançar nota/feedback de atividade: {e}", "WARN")

    def _salvar_rascunho(self, page: Page) -> bool:
        try:
            return salvar_rascunho_consistent_evaluation(page)
        except Exception:
            return False

motor_atividades = MotorAtividades()
