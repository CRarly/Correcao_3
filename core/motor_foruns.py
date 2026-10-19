import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from config import get_forums_url, get_quickeval_url, DYNAMIC_LOAD_WAIT_MS, NAV_TIMEOUT
from engine_state import state
from cognitive.detector_plagio import detector_plagio
from cognitive.construtor_feedback import extrair_primeiro_nome
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
    remover_nota_e_feedback_consistent_evaluation
)
from core.browser_session import obter_primeiro_nome_docente

class MotorForuns:
    """
    Motor especialista de avaliação e auditoria para o Fórum de Discussão.
    Implementa métrica pedagógica própria baseada no comando do fórum:
    - 50% postagem principal e 50% comentários/réplicas aos colegas (se exigido no enunciado).
    - 100% na postagem principal (caso o enunciado não exija comentários).
    - Avaliação analítica com justificativa qualitativa dos critérios e regras de nota zero.
    - Duplo salvamento em rascunho e sem assinatura docente.
    """

    def gerar_criterios_forum(self, comando: str, nota_maxima: float = 1.0) -> Dict[str, Any]:
        """
        Analisa o comando do Fórum e monta a métrica de avaliação pré-estabelecida:
        - Se o comando exige comentários com colegas:
          * 50% para Postagem Principal (Domínio Temático e Fundamentação)
          * 50% para Comentários aos Colegas (Interação Dialógica e Contribuição ao Debate)
        - Se NÃO exige comentários:
          * 100% para Postagem Principal (Domínio Temático, Argumentação e Clareza)
        """
        cmd_lower = (comando or "").lower()
        padrao_exigencia = r"(coment|interaj|réplic|replic|debat|discut|colega|outro participante|postagem de um colega|resposta a um colega)"
        exige_comentarios = bool(re.search(padrao_exigencia, cmd_lower))

        if exige_comentarios:
            peso_post = round(nota_maxima * 0.50, 2)
            peso_coment = round(nota_maxima - peso_post, 2)
            criterios = {
                "exige_comentarios": True,
                "nota_maxima": nota_maxima,
                "peso_post_principal": peso_post,
                "peso_comentarios": peso_coment,
                "criterios_post": [
                    {
                        "nome": "Domínio Temático e Resolução da Proposta",
                        "peso": round(peso_post * 0.50, 2),
                        "descricao": "Responde diretamente às questões e diretrizes propostas no comando do fórum."
                    },
                    {
                        "nome": "Fundamentação e Argumentação Técnica",
                        "peso": round(peso_post * 0.50, 2),
                        "descricao": "Articula raciocínio teórico consistente, com vocabulário técnico e clareza argumentativa."
                    }
                ],
                "criterios_coment": [
                    {
                        "nome": "Interação Dialógica e Relevância ao Colega",
                        "peso": round(peso_coment * 0.50, 2),
                        "descricao": "Dialoga diretamente com as ideias do colega, analisando seus argumentos de forma respeitosa e pertinente."
                    },
                    {
                        "nome": "Contribuição Construtiva e Expansão do Debate",
                        "peso": round(peso_coment * 0.50, 2),
                        "descricao": "Acrescenta novos pontos de vista, perguntas reflexivas ou correlações práticas, superando concordâncias genéricas."
                    }
                ]
            }
        else:
            peso_post = nota_maxima
            peso_coment = 0.0
            p1 = round(peso_post * 0.50, 2)
            p2 = round(peso_post * 0.30, 2)
            p3 = round(peso_post - p1 - p2, 2)
            criterios = {
                "exige_comentarios": False,
                "nota_maxima": nota_maxima,
                "peso_post_principal": peso_post,
                "peso_comentarios": 0.0,
                "criterios_post": [
                    {
                        "nome": "Domínio Temático e Resolução da Proposta",
                        "peso": p1,
                        "descricao": "Atendimento integral às questões orientadoras formuladas no enunciado do fórum."
                    },
                    {
                        "nome": "Fundamentação Teórica e Argumentação",
                        "peso": p2,
                        "descricao": "Desenvolvimento com profundidade técnica e fundamentação conceitual na disciplina."
                    },
                    {
                        "nome": "Clareza Textual e Norma Culta",
                        "peso": p3,
                        "descricao": "Texto bem estruturado, fluido, coeso e em conformidade com o padrão formal da língua."
                    }
                ],
                "criterios_coment": []
            }

        return criterios

    def separar_post_e_comentarios(self, postagens: List[Dict[str, Any]], comando: str = "") -> Tuple[str, List[str]]:
        """
        Separa a postagem principal dos comentários/réplicas aos colegas.
        A postagem principal é a postagem mais substantiva que responde ao tema proposto.
        """
        if not postagens:
            return "", []

        textos = [p.get("texto", "").strip() for p in postagens if p.get("texto", "").strip()]
        if not textos:
            return "", []

        if len(textos) == 1:
            return textos[0], []

        # Localizar a postagem mais longa/completa como principal
        idx_maior = 0
        max_palavras = len(textos[0].split())
        for i, t in enumerate(textos):
            plen = len(t.split())
            if plen > max_palavras:
                max_palavras = plen
                idx_maior = i

        post_principal = textos[idx_maior]
        comentarios = [t for i, t in enumerate(textos) if i != idx_maior]

        return post_principal, comentarios

    def avaliar_estudante_forum(
        self,
        post_principal: str,
        comentarios: List[str],
        nome_aluno: str,
        comando: str,
        criterios_info: Dict[str, Any],
        nota_maxima: float = 1.0,
        docente: str = "Prof. Avaliador"
    ) -> Dict[str, Any]:
        """
        Avalia a participação do estudante no Fórum de Discussão segundo a métrica analítica:
        - 50% postagem principal + 50% comentários (se exigido) ou 100% postagem principal.
        - Zera com justificativa transparente em caso de ausência ou fuga ao tema.
        - Sempre inicia com "Olá, {FirstName}!" e encerra com "Atenciosamente, Prof. [Primeiro nome]".
        """
        primeiro_nome_docente = obter_primeiro_nome_docente(docente)
        post = (post_principal or "").strip()
        coments = [c.strip() for c in (comentarios or []) if c.strip()]
        todos_textos = (post + "\n" + "\n".join(coments)).strip()
        palavras_total = len(re.findall(r"\b\w+\b", todos_textos))
        texto_lower = todos_textos.lower()
        letras_count = len(re.findall(r"[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]", todos_textos))

        # 1. Caso de ausência de participação ou '-Nenhum texto inserido-'
        is_vazio = (
            palavras_total < 5
            or "nenhum texto inserido" in texto_lower
            or "-nenhum texto inserido-" in texto_lower
            or "sem postagens" in texto_lower
            or letras_count < 15
        )

        if is_vazio:
            motivo_branco = "Não houve participação ou postagem identificada no fórum de discussão (-Nenhum texto inserido-)."
            feedback_html = (
                f"<p>Olá, {{FirstName}}!</p>"
                f"<p>Sua participação no <strong>Fórum de Discussão</strong> foi avaliada com a pontuação de <strong>0,00 de {nota_maxima:.2f} pontos</strong>.</p>"
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

        # 2. Extração de radicais conceituais do comando oficial
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
            "post", "coment", "forum", "coleg", "particip"
        }
        rads_comando = _extrair_radicais(comando) - stopwords_rad
        rads_post = _extrair_radicais(post)

        exige_comentarios = criterios_info.get("exige_comentarios", False)
        peso_post_max = criterios_info.get("peso_post_principal", nota_maxima)
        peso_coment_max = criterios_info.get("peso_comentarios", 0.0)

        descontos = []
        fb_secoes = []

        # 3. Avaliação da Postagem Principal
        palavras_post = len(re.findall(r"\b\w+\b", post))
        intersecao_post = rads_post & rads_comando

        if not post or palavras_post < 5:
            nota_post = 0.0
            descontos.append("Ausência de postagem principal respondendo à temática orientadora do fórum.")
            fb_secoes.append("<li><strong>Postagem Principal:</strong> Não foi localizada postagem principal respondendo ao tema proposto.</li>")
        elif len(intersecao_post) == 0 and len(rads_comando) > 0:
            nota_post = 0.0
            descontos.append("Fuga ao tema na postagem principal: o conteúdo publicado não abordou os conceitos e diretrizes solicitados no enunciado.")
            fb_secoes.append("<li><strong>Postagem Principal:</strong> A postagem publicada não correspondeu à proposta nem aos conceitos solicitados no fórum (fuga ao tema).</li>")
        else:
            meta_termos = max(2, min(len(rads_comando) * 0.4, 5))
            cobertura_post = min(1.0, max(0.0, len(intersecao_post) / meta_termos))

            conectivos = sum(1 for c in ["portanto", "contudo", "entretanto", "além disso", "nesse sentido", "assim sendo", "desta forma", "por conseguinte"] if c in post.lower())
            fundamentacao = 1.0 if (palavras_post >= 70 and conectivos >= 1) else 0.70 if palavras_post >= 40 else 0.40

            nota_c1 = round((peso_post_max * 0.50) * cobertura_post, 2)
            nota_c2 = round((peso_post_max * 0.50) * fundamentacao, 2)
            nota_post = min(peso_post_max, round(nota_c1 + nota_c2, 2))

            if cobertura_post >= 0.85:
                parecer_post = "Abordou com clareza e domínio conceitual as diretrizes do tema proposto."
            elif cobertura_post >= 0.50:
                parecer_post = "Abordou parcialmente os tópicos solicitados, recomendando-se maior aprofundamento teórico."
                descontos.append("Desenvolvimento temático parcial na postagem principal: aprofunde a correlação com os conceitos do comando.")
            else:
                parecer_post = "Abordagem superficial ou concisa dos temas orientadores da discussão."
                descontos.append("Abordagem superficial na postagem principal: os tópicos do comando foram apenas tangenciados.")

            fb_secoes.append(f"<li><strong>Postagem Principal:</strong> {parecer_post}</li>")

        # 4. Avaliação dos Comentários aos Colegas (se exigidos)
        nota_comentarios = 0.0
        if exige_comentarios:
            if not coments:
                nota_comentarios = 0.0
                descontos.append("Ausência de comentários ou réplicas aos colegas: o comando do fórum solicitou expressamente a interação dialógica com colegas de turma.")
                fb_secoes.append("<li><strong>Comentários aos Colegas:</strong> Não foram identificadas interações ou réplicas em postagens de colegas.</li>")
            else:
                texto_coments = " ".join(coments)
                palavras_coments = len(re.findall(r"\b\w+\b", texto_coments))
                qtd_coments = len(coments)

                termos_dialogo = sum(1 for t in ["concordo", "discordo", "ponto", "destaco", "complemento", "questão", "visão", "colega", "exemplo"] if t in texto_coments.lower())
                substantivo = (palavras_coments >= 30 and termos_dialogo >= 1) or (palavras_coments >= 50)

                if qtd_coments >= 1 and substantivo:
                    nota_comentarios = peso_coment_max
                    parecer_coment = "Interação dialógica consistente e construtiva, contribuindo com relevância para o debate dos colegas."
                elif qtd_coments >= 1:
                    nota_comentarios = round(peso_coment_max * 0.60, 2)
                    parecer_coment = "Interação protocolar ou sucinta, recomendando-se maior aprofundamento crítico nos comentários aos colegas."
                    descontos.append("Comentários aos colegas concisos: busque expandir os argumentos e trazer novos pontos de vista ao debater com os colegas.")
                else:
                    nota_comentarios = 0.0
                    parecer_coment = "Comentários não atenderam ao padrão mínimo de interação reflexiva."

                fb_secoes.append(f"<li><strong>Comentários aos Colegas:</strong> {parecer_coment}</li>")

        # 5. Cálculo Final da Nota
        nota_total = round(nota_post + nota_comentarios, 2)
        # Múltiplos de 0.05
        nota_total = round(nota_total * 20) / 20
        nota_total = min(nota_maxima, max(0.0, nota_total))

        if nota_total < nota_maxima and not descontos:
            descontos.append("Aprofundamento analítico: para atingimento da pontuação integral, desenvolva as postagens com maior amplitude reflexiva e dialógica.")

        descontos_limpos = [re.sub(r"\s*\(-?\d+[\.,]?\d*\s*pts?\)", "", d).strip() for d in descontos]

        # 6. Formatação do Feedback HTML
        nota_str = f"{nota_total:.2f}".replace(".", ",")
        fb_parts = [
            "<p>Olá, {FirstName}!</p>",
            f"<p>Sua participação no <strong>Fórum de Discussão</strong> foi avaliada com a pontuação de <strong>{nota_str} de {nota_maxima:.2f} pontos</strong>.</p>",
            "<p><strong>Análise Detalhada dos Critérios do Fórum:</strong></p>",
            "<ul>",
            "".join(fb_secoes),
            "</ul>"
        ]

        if descontos_limpos:
            fb_parts.append("<p><strong>Justificativa do Desconto de Nota:</strong></p>")
            fb_parts.append("<ul>")
            for d in descontos_limpos:
                fb_parts.append(f"<li>{d}</li>")
            fb_parts.append("</ul>")

        fb_parts.append(
            "<p>Continue se dedicando aos estudos e articulando a teoria com a prática da disciplina. Conte com o apoio docente!</p>"
        )
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
        docente: str
    ) -> List[Dict[str, Any]]:
        state.log(f"Iniciando Motor de Fóruns para [{ou}] {disciplina} (Modo: {modo.upper()})...")
        resultados = []
        nota_maxima = plano.get("forum", {}).get("valor", 1.0)
        comando_oficial = plano.get("forum", {}).get("comando", "")

        # Gerar critérios analíticos do fórum (50%/50% se exigido ou 100%)
        criterios_info = self.gerar_criterios_forum(comando_oficial, nota_maxima)
        if criterios_info.get("exige_comentarios"):
            state.log(f"[Fórum] Comando exige interação com colegas: 50% postagem principal ({criterios_info['peso_post_principal']:.2f} pts) + 50% comentários ({criterios_info['peso_comentarios']:.2f} pts).")
        else:
            state.log(f"[Fórum] Sem exigência explícita de comentários: 100% postagem principal ({criterios_info['peso_post_principal']:.2f} pts).")

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
                state.log(f"[Execução Normal] {novos_envios} novo(s) envio(s) pendente(s) no Fórum. Iniciando correções e auditoria...")
                forum_href = url_all
                modo_efetivo = "tradicional_com_auditoria"
        elif modo == "recorrigir":
            state.log(f"[Recorrigir] Reavaliando 100% dos estudantes do Fórum ({disciplina})...")
            forum_href = url_all
            modo_efetivo = "recorrigir_e_auditar"
        else:
            state.log(f"[{modo.upper()}] Acessando estudantes para avaliação/auditoria...")
            forum_href = url_all
            modo_efetivo = modo

        state.log(f"Acessando Avaliação Consistente do Fórum: {forum_href}")
        page.goto(forum_href, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
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
                state.log(f"Aluno {nome_aluno} já processado nesta rodada. Avançando...")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    break
                continue

            alunos_processados.add(chave_aluno)
            total_estimado = pos_info.get("total") or plano.get("forum", {}).get("total_geral", 10)
            state.update_progress(pos_info.get("atual") or aluno_idx, total_estimado, nome_aluno, "Fórum de Discussão")

            # 3. Aguardar carregamento completo e extrair postagens e réplicas
            postagens = self._aguardar_e_extrair_postagens_forum(page)

            # Separar postagem principal dos comentários
            post_principal, comentarios = self.separar_post_e_comentarios(postagens, comando_oficial)

            if not post_principal and not comentarios:
                state.log(f"{pos_str}{nome_aluno}: Sem postagens no Fórum (-Nenhum texto inserido-).")

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
                    state.log(f"{pos_str}{nome_aluno}: Nota 0 ou comentário prévio detectado em estudante sem participação. Removendo nota e comentário e salvando rascunho...")
                    remover_nota_e_feedback_consistent_evaluation(page)
                    time.sleep(1.0)
                    self._salvar_rascunho(page)
                    time.sleep(1.5)
                    self._salvar_rascunho(page)
                    state.log(f"{pos_str}{nome_aluno}: Rascunho salvo com nota e feedback limpos.")

                state.log(f"{pos_str}{nome_aluno}: Estudante sem participação pulado conforme diretriz operacional.")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    state.log("Todos os estudantes da turma do Fórum foram concluídos com sucesso!")
                    break
                continue

            qtd_coments = len(comentarios)
            state.log(f"{pos_str}{nome_aluno}: Postagem principal identificada ({len(post_principal.split())} palavras) | Comentários: {qtd_coments}")

            # 4. Avaliação analítica segundo os critérios do fórum
            diag = self.avaliar_estudante_forum(
                post_principal=post_principal,
                comentarios=comentarios,
                nome_aluno=nome_aluno,
                comando=comando_oficial,
                criterios_info=criterios_info,
                nota_maxima=nota_maxima,
                docente=docente
            )

            nota_calculada = diag["nota"]
            feedback_html = diag["feedback_html"]
            state.log(f"{pos_str}{nome_aluno}: Nota atribuída = {nota_calculada:.2f} / {nota_maxima:.2f} (Conceito: {diag['qualidade']})")

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

            # 5. Registrar histórico
            registro = {
                "ou": str(ou),
                "disciplina": disciplina,
                "atividade": "Fórum de discussão",
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

            # 6. Avançar para o próximo estudante no iterator
            if state.should_stop:
                break
            if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                state.log("Todos os estudantes da turma do Fórum foram concluídos com sucesso!")
                break

        return resultados

    def _aguardar_e_extrair_postagens_forum(self, page: Page, max_wait_sec: float = 7.0) -> List[Dict[str, Any]]:
        """
        Aguarda ativamente o carregamento da evidência do Fórum no Consistent Evaluation.
        """
        start_time = time.time()
        min_wait = 2.5

        while time.time() - start_time < max_wait_sec:
            postagens = self._extrair_postagens_forum(page)
            if postagens:
                return postagens

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
                sem_posts = page.evaluate("""() => {
                    const text = (document.body.innerText || '').toLowerCase();
                    return text.includes('nenhuma postagem') ||
                           text.includes('nenhum tópico') ||
                           text.includes('não há postagens') ||
                           text.includes('no posts') ||
                           text.includes('o usuário não postou') ||
                           text.includes('nenhum texto inserido') ||
                           text.includes('nenhuma evidência');
                }""")
                if sem_posts:
                    return []

            time.sleep(0.5)

        return self._extrair_postagens_forum(page)

    def _extrair_postagens_forum(self, page: Page) -> List[Dict[str, Any]]:
        try:
            # Expandir paginação 'Carregar mais' no painel de discussões, se houver
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
                        if (txtLimpo.length > 5 && !vistos.has(txtLimpo) && !txtLimpo.includes('Sua sessão')) {
                            vistos.add(txtLimpo);
                            results.push({ texto: txtLimpo, tipo: 'post' });
                        }
                    }
                }

                if (results.length === 0) {
                    const fallbacks = document.querySelectorAll('.d2l-consistent-evaluation-discussion-post, [class*="discussion-post"], .d2l-text-styled');
                    for (let el of fallbacks) {
                        const t = (el.innerText || el.textContent || '').trim();
                        if (t.length > 10 && !vistos.has(t) && !t.includes('Sua sessão')) {
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
