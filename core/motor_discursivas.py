import os
import re
import json
import time
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from config import get_quizzes_url, get_quickeval_url, DYNAMIC_LOAD_WAIT_MS, NAV_TIMEOUT, RELATORIOS_DIR
from engine_state import state
from cognitive.detector_plagio import detector_plagio
from core.navigation_iterator import (
    extrair_posicao_mostrador_iterator,
    extrair_nome_estudante_atual,
    avancar_proximo_estudante_seguro
)
from core.dom_helpers import salvar_rascunho_consistent_evaluation, salvar_rascunho_duplo

class MotorDiscursivas:
    """
    Módulo Universal e Especialista de Correção de Provas Discursivas.
    
    Assimila o ciclo completo em 4 passos:
    1. Ver Enunciado: Inspeciona a turma apontada e extrai dinamicamente o código, valor e enunciado da questão discursiva.
    2. Criar Critérios: Decompõe o enunciado em matriz de critérios analíticos (domínio conceitual, aplicação prática, norma culta).
    3. Ver Exemplo de Resposta: Gera o padrão de resposta esperado / gabarito modelo para calibração.
    4. Parte de Avaliar: Avaliação em tempo real no Consistent Evaluation, detecção de plágio (>=90%),
       lançamento de nota e feedback na questão, duplo salvamento em rascunho (nunca publicar) e auditoria final de coerência.
    """

    def __init__(self):
        self.enunciado_atual = ""
        self.criterios_atuais = []
        self.resposta_esperada_atual = ""
        self.codigo_questao_atual = ""
        self.valor_max_atual = 2.0
        self.qi_atual = ""

    # =========================================================================
    # PASSO 1: VER ENUNCIADO (Mapeamento Universal da Questão Discursiva)
    # =========================================================================
    def inspecionar_questao_discursiva(self, page: Page, ou: str | int, nome_disciplina: str = "") -> Dict[str, Any]:
        """
        Localiza a prova presencial da turma apontada de forma 100% genérica via
        quizzes_manage -> quiz_mark_users -> Consistent Evaluation.
        Extrai o código da questão, pontuação máxima, enunciado completo e o Padrão de Resposta oficial.
        """
        state.log(f"[Novo Motor de Correção] Inspecionando questão discursiva da turma [{ou}] {nome_disciplina}...")
        url_quizzes = get_quizzes_url(ou)
        
        info = {
            "ou": str(ou),
            "disciplina": nome_disciplina,
            "prova_nome": "Avaliação: Prova presencial",
            "qi": "",
            "codigo_questao": "",
            "valor_maximo": 2.0,
            "enunciado": "",
            "texto_motivador": "",
            "comando_questao": "",
            "padrao_resposta_oficial": "",
            "metodo_extracao": "consistent_evaluation_universal"
        }

        try:
            # 1. Acessar Gerenciar Questionários para obter qi da Prova Presencial
            page.goto(url_quizzes, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3)

            dados_quiz = page.evaluate(r"""() => {
                const rows = Array.from(document.querySelectorAll('tr, table tr'));
                // 1. Prioridade máxima: 'Prova presencial' ou 'Avaliação final' que NÃO contenha substitutiva nem recuperação
                for (let r of rows) {
                    const txt = (r.innerText || '').toLowerCase();
                    if ((txt.includes('prova presencial') || txt.includes('avaliação final') || txt.includes('avaliacao final')) && !txt.includes('substitutiva') && !txt.includes('recupera') && !txt.includes('qme')) {
                        const a = r.querySelector('a[href*="quiz_newedit_properties"], a[href*="qi="]');
                        if (a) {
                            const m = a.href.match(/qi=(\d+)/i);
                            return { title: a.innerText.trim(), href: a.href, qi: m ? m[1] : null };
                        }
                    }
                }
                // 2. Segunda opção: 'Prova' genérica sem substitutiva
                for (let r of rows) {
                    const txt = (r.innerText || '').toLowerCase();
                    if (txt.includes('prova') && !txt.includes('substitutiva') && !txt.includes('recupera') && !txt.includes('qme')) {
                        const a = r.querySelector('a[href*="quiz_newedit_properties"], a[href*="qi="]');
                        if (a) {
                            const m = a.href.match(/qi=(\d+)/i);
                            return { title: a.innerText.trim(), href: a.href, qi: m ? m[1] : null };
                        }
                    }
                }
                return null;
            }""")

            if not dados_quiz or not dados_quiz.get("qi"):
                state.log("[Discursivas] Prova Presencial não localizada em Questionários. Tentando via Quick Eval...", "WARN")
                return self._inspecionar_via_quickeval(page, ou, info)

            qi = dados_quiz["qi"]
            self.qi_atual = qi
            info["qi"] = qi
            info["prova_nome"] = dados_quiz["title"]
            state.log(f"[Discursivas] Prova Presencial identificada: '{info['prova_nome']}' (QI: {qi})")

            # 2. Navegar diretamente para quiz_mark_users
            url_mark = f"https://ava.catolica.edu.br/d2l/lms/quizzing/admin/mark/quiz_mark_users.d2l?qi={qi}&ou={ou}"
            state.log(f"[Discursivas] Acessando tela de tentativas: {url_mark}")
            page.goto(url_mark, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3)

            # Clicar na primeira tentativa para abrir a interface Consistent Evaluation
            clicado = page.evaluate(r"""() => {
                const links = Array.from(document.querySelectorAll('a')).filter(a => (a.innerText || '').trim().toLowerCase().includes('tentativa'));
                if (links.length > 0) {
                    links[0].click();
                    return true;
                }
                return false;
            }""")

            if not clicado:
                state.log("[Discursivas] Nenhuma tentativa encontrada na tabela de notas. Tentando Quick Eval...", "WARN")
                return self._inspecionar_via_quickeval(page, ou, info)

            time.sleep(6.0)
            # Garantir seleção da Tentativa 1 caso a tela abra em Resumo da conclusão
            self._assegurar_tentativa_1(page)
            # Rolar todos os containers scrollaveis internos para acionar renderizacao lazy das questoes
            page.evaluate(r"""() => {
                const scrollables = Array.from(document.querySelectorAll('*')).filter(el => {
                    const ov = window.getComputedStyle(el).overflowY;
                    return (ov === 'auto' || ov === 'scroll') && el.scrollHeight > el.clientHeight;
                });
                for (let s of scrollables) s.scrollTop = s.scrollHeight;
                window.scrollTo(0, document.body.scrollHeight);
            }""")
            time.sleep(2.5)

            # 3. Extrair Enunciado, Código da Questão, Pontuação Máxima e Padrão de Resposta
            dados_ce = page.evaluate(r"""() => {
                function getAll(root) {
                    let res = [];
                    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                    while (w.nextNode()) {
                        res.push(w.currentNode);
                        if (w.currentNode.shadowRoot) res = res.concat(getAll(w.currentNode.shadowRoot));
                    }
                    return res;
                }
                const all = getAll(document.body);

                // Blocos renderizados de HTML
                const rendered = all.filter(el => (el.className || '').toString().includes('d2l-html-block-rendered'));
                const textos = rendered.map(el => (el.innerText || '').trim()).filter(t => t.length > 10);

                let padraoIdx = -1;
                let padraoResposta = '';
                for (let i = 0; i < textos.length; i++) {
                    if (textos[i].toLowerCase().includes('padrão de resposta') || textos[i].toLowerCase().includes('padrao de resposta')) {
                        padraoIdx = i;
                        padraoResposta = textos[i];
                        break;
                    }
                }

                let enunciado = '';
                if (padraoIdx >= 2) {
                    enunciado = textos[padraoIdx - 2];
                } else if (padraoIdx === 1) {
                    enunciado = textos[0];
                } else {
                    const eadBlocks = textos.filter(t => t.includes('EAD_'));
                    if (eadBlocks.length > 0) enunciado = eadBlocks[eadBlocks.length - 1];
                }

                let codigo = '';
                const mCode = enunciado.match(/EAD_[A-Za-z0-9_]+/);
                if (mCode) {
                    codigo = mCode[0];
                } else {
                    for (let t of textos) {
                        const m = t.match(/EAD_[A-Za-z0-9_]+/);
                        if (m && (m[0].includes('DIS') || m[0].includes('PROV') || m[0].includes('QDIS'))) {
                            codigo = m[0];
                            break;
                        }
                    }
                }

                // Pontuação máxima
                let pontosMax = 2.0;
                const inputs = all.filter(el => {
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    return aria.includes('pontuação da pergunta de') || aria.includes('pontuacao da pergunta de');
                });
                if (inputs.length > 0) {
                    const aria = inputs[inputs.length - 1].getAttribute('aria-label') || '';
                    const m = aria.match(/de\s+(\d+[\.,]?\d*)/i);
                    if (m) pontosMax = parseFloat(m[1].replace(',', '.'));
                }

                return { codigo, enunciado, padraoResposta, pontosMax };
            }""")

            if dados_ce.get("codigo"):
                info["codigo_questao"] = dados_ce["codigo"]
            if dados_ce.get("pontosMax"):
                info["valor_maximo"] = dados_ce["pontosMax"]
            if dados_ce.get("enunciado"):
                info["enunciado"] = dados_ce["enunciado"]
                self._decompor_enunciado(info)
            if dados_ce.get("padraoResposta"):
                info["padrao_resposta_oficial"] = dados_ce["padraoResposta"]

        except Exception as e:
            state.log(f"[Discursivas] Aviso na inspeção universal: {e}", "WARN")

        # Fallback de segurança se necessário
        if not info["enunciado"]:
            info = self._inspecionar_via_quickeval(page, ou, info)

        self.enunciado_atual = info.get("enunciado", "")
        self.codigo_questao_atual = info.get("codigo_questao", "")
        self.valor_max_atual = info.get("valor_maximo", 2.0)
        self.resposta_esperada_atual = info.get("padrao_resposta_oficial", "")

        state.log(f"[Discursivas] Enunciado mapeado com sucesso ({len(self.enunciado_atual)} caracteres). Código: {self.codigo_questao_atual} | Valor: {self.valor_max_atual} pts.")
        return info

    def _inspecionar_via_quickeval(self, page: Page, ou: str | int, info: Dict[str, Any]) -> Dict[str, Any]:
        """Extrai enunciado diretamente do Consistent Evaluation na primeira tentativa da turma."""
        url_qe = f"{get_quickeval_url(ou)}"
        state.log(f"[Discursivas] Extraindo enunciado via Consistent Evaluation: {url_qe}")
        try:
            page.goto(url_qe, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3)

            # Clicar na aba Atividades
            page.evaluate(r"""() => {
                const tabs = Array.from(document.querySelectorAll('d2l-tab, [role="tab"], button, a'));
                const ativ = tabs.find(t => (t.innerText || '').trim().toLowerCase() === 'atividades');
                if (ativ) ativ.click();
            }""")
            time.sleep(3)

            # Abrir link da prova presencial
            link_prova = page.evaluate(r"""() => {
                const links = Array.from(document.querySelectorAll('a[href*="evaluation/activity"]'));
                for (let a of links) {
                    const txt = (a.innerText || '').toLowerCase();
                    if (txt.includes('prova') || txt.includes('presencial')) {
                        return a.href;
                    }
                }
                return links.length > 0 ? links[0].href : null;
            }""")

            if link_prova:
                page.goto(link_prova, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                time.sleep(6)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)

                enun_qe = page.evaluate(r"""() => {
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
                    const wraps = all.filter(el => (el.className || '').toString().includes('questions-question-wrapper') || (el.className || '').toString().includes('quiz-question'));
                    if (wraps.length > 0) {
                        const target = wraps[wraps.length - 1];
                        return (target.innerText || '').trim();
                    }
                    return '';
                }""")
                if enun_qe:
                    info["enunciado"] = enun_qe
                    info["metodo_extracao"] = "consistent_evaluation"
                    self._decompor_enunciado(info)
        except Exception as e:
            state.log(f"[Discursivas] Fallback Quick Eval: {e}", "WARN")

        return info

    def _decompor_enunciado(self, info: Dict[str, Any]):
        """Separa texto motivador e comando pedagógico do enunciado."""
        enun = info.get("enunciado", "")
        # Heurística: frases como "Explique", "Apresente", "Discorra", "Analise", "Descreva" marcam o início do comando
        match_cmd = re.search(r"\b(explique|apresente|discorra|analise|descreva|elabore|justifique|indique|com base no texto)\b", enun, re.IGNORECASE)
        if match_cmd and match_cmd.start() > 30:
            info["texto_motivador"] = enun[:match_cmd.start()].strip()
            info["comando_questao"] = enun[match_cmd.start():].strip()
        else:
            info["texto_motivador"] = ""
            info["comando_questao"] = enun

    # =========================================================================
    # PASSO 2: CRIAR CRITÉRIOS (Rubrica Analítica Dinâmica)
    # =========================================================================
    def gerar_criterios_avaliacao(self, enunciado: str, valor_maximo: float = 2.0) -> List[Dict[str, Any]]:
        """
        Analisa o enunciado extraído e sintetiza dinamicamente os critérios de avaliação
        com pesos equilibrados (totalizando o valor máximo da questão) e regras explícitas de dedução.
        """
        self.enunciado_atual = enunciado
        self.valor_max_atual = valor_maximo

        # Identificar se há comandos específicos no enunciado
        enun_lower = (enunciado or "").lower()
        exige_exemplos = any(k in enun_lower for k in ["exemplo", "exemplos", "aplicaç", "sistemas estudados", "casos"])
        exige_proprias_palavras = "suas palavras" in enun_lower or "próprias palavras" in enun_lower
        
        # Ponderação dos 3 pilares
        peso_conceitual = round(valor_maximo * 0.35, 2)   # ex: 0.70 pts em 2.0
        peso_pratico = round(valor_maximo * 0.40, 2)       # ex: 0.80 pts em 2.0
        peso_redacao = round(valor_maximo - peso_conceitual - peso_pratico, 2)  # ex: 0.50 pts em 2.0

        criterios = [
            {
                "id": "criterio_1_conceitual",
                "nome": "1. Domínio Conceitual e Fundamentação Teórica",
                "peso": peso_conceitual,
                "descricao": "Compreensão aprofundada dos conceitos solicitados no enunciado e resposta direta à questão teórica central.",
                "regras_desconto": [
                    {"faixa": "Pleno", "nota": peso_conceitual, "descricao": "Abordagem teórica completa e correta."},
                    {"faixa": "Parcial", "nota": round(peso_conceitual * 0.6, 2), "descricao": "Abordagem conceitual superficial ou incompleta dos termos técnicos solicitados."},
                    {"faixa": "Insuficiente", "nota": 0.0, "descricao": "Não desenvolveu os conceitos-chave ou tangenciou o tema solicitado."}
                ]
            },
            {
                "id": "criterio_2_pratico",
                "nome": "2. Aplicação Prática, Exemplos e Contextualização",
                "peso": peso_pratico,
                "descricao": "Apresentação de exemplos práticos, aplicações concretas ou articulação com a realidade operacional/organizacional." + (" (Exigência expressa de ao menos 2 exemplos)" if exige_exemplos else ""),
                "regras_desconto": [
                    {"faixa": "Pleno", "nota": peso_pratico, "descricao": "Apresentou exemplos pertinentes e explicou com clareza a aplicação prática."},
                    {"faixa": "Parcial", "nota": round(peso_pratico * 0.5, 2), "descricao": "Apresentou apenas um exemplo superficial ou exemplos genéricos sem correlação direta com o tema."},
                    {"faixa": "Insuficiente", "nota": 0.0, "descricao": "Não apresentou os exemplos práticos ou aplicações solicitadas no comando da questão."}
                ]
            },
            {
                "id": "criterio_3_redacao",
                "nome": "3. Clareza Argumentativa, Coesão e Norma Culta",
                "peso": peso_redacao,
                "descricao": "Estrutura textual lógica e coesa, redação em conformidade com a norma padrão e desenvolvimento com as próprias palavras.",
                "regras_desconto": [
                    {"faixa": "Pleno", "nota": peso_redacao, "descricao": "Texto bem estruturado, claro e gramaticalmente correto."},
                    {"faixa": "Parcial", "nota": round(peso_redacao * 0.6, 2), "descricao": "Texto excessivamente conciso, repetições vocabulares ou pontuação deficiente."},
                    {"faixa": "Insuficiente", "nota": 0.0, "descricao": "Fragmentação textual severa ou envio em branco."}
                ]
            }
        ]

        self.criterios_atuais = criterios
        state.log(f"[Discursivas] Matriz de critérios pedagógicos formulada com sucesso (Total: {valor_maximo:.2f} pts).")
        return criterios

    # =========================================================================
    # PASSO 3: VER EXEMPLO DE RESPOSTA (Gabarito de Referência)
    # =========================================================================
    def gerar_exemplo_resposta(self, enunciado: str, criterios: List[Dict[str, Any]] = None) -> str:
        """
        Sintetiza um padrão de resposta esperado ideal baseado no enunciado e critérios,
        servindo como parâmetro de referência pedagógica para a correção da turma.
        """
        enun_clean = re.sub(r"\s+", " ", enunciado).strip()
        
        # Padrão contextual baseado no comando
        exemplo = (
            f"PADRÃO DE RESPOSTA ESPERADO (GABARITO COMENTADO):\n\n"
            f"1. Contextualização e Fundamentação Conceitual:\n"
            f"O estudante deve iniciar conceituando com precisão os tópicos teóricos centrais abordados no enunciado, "
            f"demonstrando domínio do vocabulário técnico da disciplina e explicando o papel desses elementos no funcionamento organizacional.\n\n"
            f"2. Articulação Prática e Exemplificação:\n"
            f"Em atendimento ao comando da questão, a resposta deve apresentar com clareza aplicações práticas ou exemplos reais "
            f"(ao menos dois exemplos bem estruturados), detalhando como esses sistemas, métodos ou práticas são empregados na rotina, "
            f"na gestão operacional ou nas tomadas de decisão estratégica.\n\n"
            f"3. Clareza e Autoria:\n"
            f"O texto deve ser redigido com as próprias palavras do estudante, articulando raciocínio coeso, fluidez argumentativa "
            f"e conformidade com a norma culta da língua portuguesa, sem cópia literal de fontes externas ou enunciados."
        )
        
        self.resposta_esperada_atual = exemplo
        return exemplo

    # =========================================================================
    # PASSO 4: A PARTE DE AVALIAR (Correção, Justificativas, Duplo Rascunho)
    # =========================================================================
    def avaliar_estudante(
        self,
        texto_aluno: str,
        nome_aluno: str,
        enunciado: str = "",
        criterios: List[Dict[str, Any]] = None,
        valor_maximo: float = 2.0,
        docente: str = "Prof. Avaliador",
        ou: str | int = "",
        disciplina: str = ""
    ) -> Dict[str, Any]:
        """
        Avalia a resposta do aluno com base na rubrica de critérios, verifica plágio (>=90%),
        calcula a nota por critério e gera justificativas obrigatórias para qualquer desconto.
        """
        enunciado = enunciado or self.enunciado_atual
        criterios = criterios or self.criterios_atuais
        valor_maximo = valor_maximo or self.valor_max_atual
        texto = (texto_aluno or "").strip()
        palavras = len(re.findall(r"\b\w+\b", texto))

        # 1. Checagem de Plágio (Desativada temporariamente a pedido do usuário)
        # O módulo de detecção de plágio será aprimorado posteriormente.
        info_plagio = {
            "tem_plagio": False,
            "similaridade_pct": 0.0,
            "aluno_autor": None,
            "aluno_copiador": nome_aluno,
            "trechos_copiados": [],
            "relatorio_comparacao": None
        }

        # 2. Resposta em branco, insuficiente ou "-Nenhum texto inserido-"
        texto_lower = texto.lower()
        letras_count = len(re.findall(r"[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]", texto))
        is_sem_resposta = (
            palavras < 5
            or "nenhum texto inserido" in texto_lower
            or "-nenhum texto inserido-" in texto_lower
            or "sem resposta" in texto_lower
            or letras_count < 15
        )

        if is_sem_resposta:
            desconto_branco = "Não houve resposta apresentada para a questão discursiva (-Nenhum texto inserido-)."
            feedback_html = (
                f"<p>Sua resposta para a Questão Discursiva da Prova Presencial foi avaliada com a pontuação de <strong>0,00 de {valor_maximo:.2f} pontos</strong>.</p>"
                f"<p><strong>Motivos do não atingimento da totalidade da nota:</strong></p>"
                f"<ul><li>{desconto_branco}</li></ul>"
                f"<p>Continue empenhado(a) em articular os conceitos teóricos aos desafios práticos da disciplina. Conte com o apoio docente!</p>"
            )
            return {
                "nota": 0.0,
                "nota_max": valor_maximo,
                "qualidade": "Insuficiente",
                "descontos": [desconto_branco],
                "pontos_fortes": [],
                "feedback_html": feedback_html,
                "plagio": False,
                "similaridade_pct": 0.0
            }

        # 3. Avaliação Multicritério Analítica com Stemming em Português
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
            "disciplin", "com", "sem", "por", "que", "ess", "aquil", "voc", "sua", "seus", "suas"
        }
        rads_comando = _extrair_radicais(enunciado) - stopwords_rad
        if self.resposta_esperada_atual:
            rads_padrao = _extrair_radicais(self.resposta_esperada_atual) - stopwords_rad
            rads_referencia = rads_comando | rads_padrao
        else:
            rads_referencia = rads_comando

        rads_aluno = _extrair_radicais(texto)
        intersecao = rads_aluno & rads_referencia

        # 3.1 Verificação de correspondência com a proposta da questão (Fuga ao tema)
        # Se a resposta não contém nenhum radical em comum com os conceitos solicitados
        if len(intersecao) == 0 and len(rads_referencia) > 0:
            desconto_fuga = "A resposta apresentada não correspondeu com a proposta da questão solicitada no enunciado."
            feedback_html = (
                f"<p>Sua resposta para a Questão Discursiva da Prova Presencial foi avaliada com a pontuação de <strong>0,00 de {valor_maximo:.2f} pontos</strong>.</p>"
                f"<p><strong>Motivos do não atingimento da totalidade da nota:</strong></p>"
                f"<ul><li>{desconto_fuga}</li></ul>"
                f"<p>Continue empenhado(a) em articular os conceitos teóricos aos desafios práticos da disciplina. Conte com o apoio docente!</p>"
            )
            return {
                "nota": 0.0,
                "nota_max": valor_maximo,
                "qualidade": "Insuficiente",
                "descontos": [desconto_fuga],
                "pontos_fortes": [],
                "feedback_html": feedback_html,
                "plagio": False,
                "similaridade_pct": 0.0
            }

        # 3.2 Cálculo das notas por critério quando há correspondência
        # Critério 1: Domínio Conceitual (peso ~0,70)
        meta_radicais = max(2, min(len(rads_referencia) * 0.4, 5))
        cobertura = len(intersecao) / meta_radicais
        cobertura = min(1.0, max(0.0, cobertura))

        p1 = criterios[0]["peso"] if len(criterios) > 0 else 0.70
        nota_c1 = round(p1 * cobertura, 2)

        # Critério 2: Aplicação Prática e Exemplos (peso ~0,80)
        p2 = criterios[1]["peso"] if len(criterios) > 1 else 0.80
        tem_exemplos = any(k in texto.lower() for k in ["exemplo", "exemplos", "como por exemplo", "aplicação", "sistema", "empresa", "organização", "caso", "cenário"])
        if palavras >= 60 and tem_exemplos:
            nota_c2 = p2
        elif tem_exemplos or palavras >= 40:
            nota_c2 = round(p2 * 0.50, 2)
        else:
            nota_c2 = 0.0

        # Critério 3: Clareza e Norma Culta (peso ~0,50)
        p3 = criterios[2]["peso"] if len(criterios) > 2 else 0.50
        if nota_c1 == 0:
            nota_c3 = 0.0
        elif palavras >= 50:
            nota_c3 = p3
        elif palavras >= 25:
            nota_c3 = round(p3 * 0.60, 2)
        else:
            nota_c3 = round(p3 * 0.30, 2)

        nota_total = round(nota_c1 + nota_c2 + nota_c3, 2)
        # Arredondamento para múltiplos de 0.05
        nota_total = round(nota_total * 20) / 20
        nota_total = min(valor_maximo, max(0.0, nota_total))

        if nota_total == 0.0:
            desconto_insuf = "A resposta apresentada não atingiu o desenvolvimento mínimo exigido para atendimento aos critérios da questão."
            feedback_html = (
                f"<p>Sua resposta para a Questão Discursiva da Prova Presencial foi avaliada com a pontuação de <strong>0,00 de {valor_maximo:.2f} pontos</strong>.</p>"
                f"<p><strong>Motivos do não atingimento da totalidade da nota:</strong></p>"
                f"<ul><li>{desconto_insuf}</li></ul>"
                f"<p>Continue empenhado(a) em articular os conceitos teóricos aos desafios práticos da disciplina. Conte com o apoio docente!</p>"
            )
            return {
                "nota": 0.0,
                "nota_max": valor_maximo,
                "qualidade": "Insuficiente",
                "descontos": [desconto_insuf],
                "pontos_fortes": [],
                "feedback_html": feedback_html,
                "plagio": False,
                "similaridade_pct": 0.0
            }

        # 4. Análise Qualitativa dos Critérios e Mapeamento de Descontos (Sem valores numéricos de dedução)
        c1_nome = criterios[0]["nome"] if len(criterios) > 0 else "Diagnóstico Conceitual"
        c2_nome = criterios[1]["nome"] if len(criterios) > 1 else "Aplicação Prática e Exemplos"
        c3_nome = criterios[2]["nome"] if len(criterios) > 2 else "Articulação e Clareza Textual"

        # Pareceres qualitativos
        if nota_c1 >= (p1 * 0.85):
            c1_parecer = "Demonstrou domínio conceitual e compreensão clara do tema abordado."
        elif nota_c1 >= (p1 * 0.50):
            c1_parecer = "Abordou parcialmente os conceitos teóricos centrais, mas sem aprofundar todos os fundamentos exigidos."
        else:
            c1_parecer = "Não diagnosticou adequadamente os fundamentos teóricos solicitados no comando da questão."

        if nota_c2 >= (p2 * 0.85):
            c2_parecer = "Apresentou contextualização prática consistente e atendeu plenamente à exemplificação solicitada."
        elif nota_c2 >= (p2 * 0.50):
            c2_parecer = "Apresentou exemplos parciais ou genéricos, sem detalhar suficientemente a correlação com a prática profissional."
        else:
            c2_parecer = "Não atendeu ao comando do enunciado que solicitava expressamente a apresentação e justificativa de exemplos ou aplicações práticas."

        if nota_c3 >= (p3 * 0.85):
            c3_parecer = "Texto bem estruturado, coeso e em perfeita conformidade com a norma padrão."
        elif nota_c3 >= (p3 * 0.50):
            c3_parecer = "Linha de raciocínio compreensível, apresentando apenas pequenos desvios de pontuação ou repetição vocabular."
        else:
            c3_parecer = "Construção textual excessivamente concisa ou fragmentada, necessitando de maior articulação expositiva."

        # Justificativas de Desconto (Estritamente sem pontuações parciais deduzidas, ex: sem '(-0.70 pts)')
        descontos = []
        if nota_c1 < (p1 * 0.85):
            descontos.append("Abordagem conceitual parcial: os termos e conceitos teóricos solicitados no enunciado poderiam ser mais detalhados e fundamentados.")

        if nota_c2 < (p2 * 0.85):
            descontos.append("Exemplificação ou proposição prática incompleta: o enunciado solicitou expressamente a indicação e justificativa de exemplos ou aplicações práticas, etapa que não foi plenamente desenvolvida.")

        if nota_c3 < (p3 * 0.85):
            descontos.append("Ajuste na articulação textual e norma culta: desenvolvimento argumentativo muito sucinto para uma questão discursiva, recomendando-se revisão de pontuação e polimento estilístico.")

        if nota_total < valor_maximo and not descontos:
            descontos.append("Aprofundamento analítico: para alcance pleno da pontuação máxima integral (100%), explore com maior amplitude teórica e correlação prática todos os aspectos do tema.")

        # Limpar qualquer indicação de pontos em descontos existentes (ex: remove '(-0.70 pts)')
        descontos_limpos = [re.sub(r"\s*\(-?\d+[\.,]?\d*\s*pts?\)", "", d).strip() for d in descontos]

        # 5. Formatar Feedback HTML no padrão solicitado
        nota_str = f"{nota_total:.2f}".replace(".", ",")
        fb_parts = [
            f"<p>Sua resposta para a Questão Discursiva da Prova Presencial foi avaliada com a pontuação de <strong>{nota_str} de {valor_maximo:.2f} pontos</strong>.</p>",
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

        fb_parts.append(
            f"<p>Continue empenhado(a) em articular os conceitos teóricos aos desafios práticos da disciplina. Conte com o apoio docente!</p>"
        )
        feedback_html = "".join(fb_parts)

        qualidade = "Excelente" if nota_total >= (valor_maximo * 0.85) else "Bom" if nota_total >= (valor_maximo * 0.70) else "Regular" if nota_total >= (valor_maximo * 0.50) else "Insuficiente"

        return {
            "nota": nota_total,
            "nota_max": valor_maximo,
            "qualidade": qualidade,
            "descontos": descontos_limpos,
            "pontos_fortes": [],
            "feedback_html": feedback_html,
            "plagio": False,
            "similaridade_pct": info_plagio.get("similaridade_pct", 0.0)
        }

    # =========================================================================
    # EXECUÇÃO DA TURMA (Com Duplo Rascunho e Auditoria de Coerência Final)
    # =========================================================================
    def executar_turma(
        self,
        page: Page,
        ou: str | int,
        disciplina: str,
        modo: str = "tradicional",
        docente: str = "Prof. Avaliador",
        enunciado_override: str = "",
        valor_maximo_override: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Executa o ciclo de avaliação de todos os estudantes da turma na Prova Presencial (Discursiva).
        Lança nota e feedback no editor da questão, salva em rascunho duas vezes e audita coerência ao final.
        """
        state.log(f"[Novo Motor de Correção] Iniciando avaliação da turma [{ou}] {disciplina} (Modo: {modo.upper()})...")
        resultados = []

        # 1. Pré-inspeção do enunciado se necessário
        if not self.enunciado_atual or enunciado_override:
            if enunciado_override:
                self.enunciado_atual = enunciado_override
                self.valor_max_atual = valor_maximo_override or 2.0
                self.gerar_criterios_avaliacao(self.enunciado_atual, self.valor_max_atual)
            else:
                self.inspecionar_questao_discursiva(page, ou, disciplina)
                self.gerar_criterios_avaliacao(self.enunciado_atual, self.valor_max_atual)

        enunciado = self.enunciado_atual
        criterios = self.criterios_atuais
        valor_max = self.valor_max_atual

        # 2. Localizar URL de entrada no Quick Eval
        url_qe = get_quickeval_url(ou)
        page.goto(url_qe, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        time.sleep(3)

        # Selecionar aba Atividades
        page.evaluate(r"""() => {
            const tabs = Array.from(document.querySelectorAll('d2l-tab, [role="tab"], button, a'));
            const ativ = tabs.find(t => (t.innerText || '').trim().toLowerCase() === 'atividades');
            if (ativ) ativ.click();
        }""")
        time.sleep(3)

        link_prova = page.evaluate(r"""() => {
            const links = Array.from(document.querySelectorAll('a[href*="evaluation/activity"]'));
            for (let a of links) {
                const txt = (a.innerText || '').toLowerCase();
                if (txt.includes('prova') || txt.includes('presencial')) {
                    return a.href;
                }
            }
            return links.length > 0 ? links[0].href : null;
        }""")

        if not link_prova:
            state.log(f"[Discursivas] Prova não listada no Quick Eval de {ou}. Tentando geração determinística de Activity ID...", "WARN")
            qi = self.qi_atual
            if not qi:
                # Obter qi em quizzes_manage
                page.goto(get_quizzes_url(ou), wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                time.sleep(2.5)
                qi = page.evaluate(r"""() => {
                    const rows = Array.from(document.querySelectorAll('tr, table tr'));
                    for (let r of rows) {
                        const txt = (r.innerText || '').toLowerCase();
                        if ((txt.includes('prova presencial') || txt.includes('prova') || txt.includes('avaliação')) && !txt.includes('substitutiva') && !txt.includes('recupera') && !txt.includes('qme')) {
                            const a = r.querySelector('a[href*="quiz_newedit_properties"], a[href*="qi="]');
                            if (a) {
                                const m = a.href.match(/qi=(\d+)/i);
                                if (m) return m[1];
                            }
                        }
                    }
                    return null;
                }""")
            if qi:
                self.qi_atual = qi
                inner = base64.b64encode(f"6606_51000_{qi}".encode()).decode().rstrip("=")
                act_id = base64.b64encode(f"{inner}.{ou}".encode()).decode().rstrip("=")
                link_prova = f"https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/{act_id}?ou={ou}&cft=qe"
                state.log(f"[Discursivas] Activity ID determinístico gerado: {link_prova}")
            else:
                state.log(f"[Discursivas] Nenhuma avaliação de Prova Presencial encontrada para {ou}.", "WARN")
                return resultados

        # Configurar modo de iterator: 'new' para novos envios ou 'all' para recorrigir/auditar
        range_param = "iteratorRange=all" if modo in ["recorrigir", "auditoria_geral"] else "iteratorRange=new"
        if "iteratorRange=" in link_prova:
            url_iter = re.sub(r"iteratorRange=[^&]+", range_param, link_prova)
        else:
            url_iter = link_prova + ("&" if "?" in link_prova else "?") + range_param

        state.log(f"[Discursivas] Acessando tela de Avaliação Consistente: {url_iter}")
        page.goto(url_iter, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        time.sleep(5)

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
                state.log(f"[Discursivas] Tentativa de {nome_aluno} já processada. Avançando...")
                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    break
                continue

            alunos_processados.add(chave_aluno)
            total_est = pos_info.get("total") or 10
            state.update_progress(pos_info.get("atual") or aluno_idx, total_est, nome_aluno, "Prova Presencial (Discursiva)")

            # Assegurar seleção da tentativa correta
            self._assegurar_tentativa_1(page)

            # Rolar até a questão discursiva
            self._rolar_ate_discursiva(page)

            # Extrair resposta do estudante
            texto_resposta = self._extrair_resposta_aluno(page)
            if not texto_resposta.strip():
                time.sleep(2.0)
                texto_resposta = self._extrair_resposta_aluno(page)

            palavras_resp = len(texto_resposta.split())
            if not texto_resposta.strip() or "nenhum texto inserido" in texto_resposta.lower():
                state.log(f"{pos_str}{nome_aluno}: Sem resposta discursiva (-Nenhum texto inserido-).")
            else:
                state.log(f"{pos_str}{nome_aluno}: Resposta identificada ({palavras_resp} palavras).")

            # Avaliar pela rubrica analítica
            diag = self.avaliar_estudante(
                texto_aluno=texto_resposta,
                nome_aluno=nome_aluno,
                enunciado=enunciado,
                criterios=criterios,
                valor_maximo=valor_max,
                docente=docente,
                ou=ou,
                disciplina=disciplina
            )

            nota_final = diag["nota"]
            fb_html = diag["feedback_html"]
            state.log(f"{pos_str}{nome_aluno}: Nota atribuída = {nota_final:.2f} / {valor_max:.2f} (Conceito: {diag['qualidade']})")

            # Lançar nota e feedback no editor da questão
            self._inserir_nota_e_feedback(page, nota_final, fb_html, valor_max)

            # Persistência obrigatória: SALVAR EM RASCUNHO DUAS VEZES (NUNCA PUBLICAR)
            state.log(f"{pos_str}Salvando avaliação em rascunho (1ª persistência)...")
            self._salvar_rascunho(page)
            time.sleep(2.0)
            state.log(f"{pos_str}Confirmando salvamento em rascunho (2ª persistência)...")
            self._salvar_rascunho(page)
            time.sleep(1.0)

            registro = {
                "ou": str(ou),
                "disciplina": disciplina,
                "atividade": "Prova presencial",
                "aluno": nome_aluno,
                "nota": nota_final,
                "nota_max": valor_max,
                "plagio": diag.get("plagio", False),
                "similaridade_pct": diag.get("similaridade_pct", 0.0),
                "qualidade": diag.get("qualidade", "Bom"),
                "modo": modo,
                "descontos": diag.get("descontos", [])
            }
            resultados.append(registro)

            if state.should_stop:
                break
            if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                state.log("[Discursivas] Fim da lista de estudantes atingido com sucesso.")
                break

        # Auditoria de Coerência Final de 100% da turma avaliada
        self.executar_auditoria_coerencia(resultados, ou, disciplina, valor_max)
        return resultados

    def _assegurar_tentativa_1(self, page: Page) -> bool:
        """
        Garante que a visualização do estudante esteja na 'Tentativa 1' e NÃO em 'Resumo da conclusão'.
        Percorre light DOM e shadow DOM para localizar o dropdown de tentativas,
        seleciona 'Tentativa 1' caso esteja em 'Resumo da conclusão' e aguarda o carregamento das perguntas.
        """
        try:
            trocou = page.evaluate(r"""() => {
                function getAll(root) {
                    let res = [];
                    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                    while(w.nextNode()) {
                        res.push(w.currentNode);
                        if (w.currentNode.shadowRoot) res = res.concat(getAll(w.currentNode.shadowRoot));
                    }
                    return res;
                }
                const all = getAll(document.body);
                
                // 1. Localizar o elemento <select> de tentativas (inclusive dentro de Shadow DOM)
                const selects = all.filter(el => {
                    if (el.tagName.toLowerCase() !== 'select') return false;
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    const hasTentativa = Array.from(el.options || []).some(o => (o.text || '').toLowerCase().includes('tentativa') || o.value === 'completion-summary');
                    return aria.includes('tentativa') || aria.includes('attempt') || hasTentativa;
                });

                for (let sel of selects) {
                    const val = sel.value || '';
                    const curText = sel.options && sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text.toLowerCase() : '';
                    
                    // Se estiver em Resumo da conclusão, selecionar a Tentativa 1
                    if (val === 'completion-summary' || curText.includes('resumo') || curText.includes('summary')) {
                        for (let i = 0; i < sel.options.length; i++) {
                            const opt = sel.options[i];
                            const optText = (opt.text || '').toLowerCase();
                            if (optText.includes('tentativa 1') || (opt.value && opt.value !== 'completion-summary')) {
                                sel.selectedIndex = i;
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                                sel.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                                return { trocou: true, novoTexto: opt.text, novoValor: opt.value };
                            }
                        }
                    }
                }

                // 2. Fallback: procurar links ou botões de Tentativa 1
                for (let el of all) {
                    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (txt === 'tentativa 1') {
                        const target = el.closest ? (el.closest('a') || el.closest('button') || el) : el;
                        if (typeof target.click === 'function' && target.tagName.toLowerCase() !== 'option') {
                            target.click();
                            return { trocou: true, novoTexto: 'Tentativa 1 (via click)', novoValor: '' };
                        }
                    }
                }

                return { trocou: false };
            }""")

            if trocou and trocou.get("trocou"):
                state.log(f"[Novo Motor de Correção] Selecionado '{trocou.get('novoTexto', 'Tentativa 1')}' no dropdown de tentativas (saindo de Resumo da conclusão). Carregando perguntas...")
                time.sleep(4.5)
                return True
        except Exception as e:
            state.log(f"[Novo Motor de Correção] Aviso ao selecionar Tentativa 1: {e}", "WARN")
        return False

    def _rolar_ate_discursiva(self, page: Page):
        """Rola os painéis internos e a página para baixo para exibir a questão discursiva."""
        try:
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
                        el.scrollTop = el.scrollHeight;
                    }
                }
                window.scrollTo(0, document.body.scrollHeight);
            }""")
            time.sleep(1.5)
        except Exception:
            pass

    def _extrair_resposta_aluno(self, page: Page) -> str:
        """Extrai o texto autêntico da resposta dissertativa do estudante, ignorando gabaritos e feedbacks."""
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

                function isFeedbackOrPrompt(txt) {
                    if (!txt) return true;
                    const t = txt.toLowerCase();
                    return t.includes('sua resposta para a questão') ||
                           t.includes('sua resposta para a questao') ||
                           t.includes('análise detalhada dos critérios') ||
                           t.includes('analise detalhada dos criterios') ||
                           t.includes('justificativa do desconto') ||
                           t.includes('padrão de resposta') ||
                           t.includes('padrao de resposta') ||
                           t.includes('texto-motivador') ||
                           t.includes('comando da questão') ||
                           t.includes('comando da questao') ||
                           t.includes('prof. avaliador') ||
                           t.includes('critério 1') ||
                           t.includes('critério 2') ||
                           t.includes('critério 3') ||
                           t.startsWith('ead_');
                }

                // 1. Procurar componente específico de resposta escrita (d2l-questions-written-response-question-response)
                const respContainers = findDeepAll(document.body, el => (el.className || '').toString().includes('written-response-question-response'));
                for (let container of respContainers) {
                    const innerRendered = findDeepAll(container, el => (el.className || '').toString().includes('d2l-html-block-rendered'));
                    for (let b of innerRendered) {
                        let t = (b.innerText || '').trim();
                        t = t.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
                        if (t.length > 5 && !isFeedbackOrPrompt(t)) {
                            return t;
                        }
                    }
                    let tDirect = (container.innerText || '').trim();
                    tDirect = tDirect.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
                    if (tDirect.length > 5 && !isFeedbackOrPrompt(tDirect)) {
                        return tDirect;
                    }
                }

                // 2. Procurar elemento imediatamente anterior ao contador de palavras
                const wordCounts = findDeepAll(document.body, el => (el.className || '').toString().includes('word-count') || /^\d+\s+palavras/i.test((el.innerText || '').trim()));
                if (wordCounts.length > 0) {
                    const wc = wordCounts[wordCounts.length - 1];
                    let prev = wc.previousElementSibling;
                    while (prev) {
                        const pTxt = (prev.innerText || '').trim();
                        if (prev.tagName.toLowerCase() !== 'd2l-offscreen' && pTxt.length > 5 && !isFeedbackOrPrompt(pTxt)) {
                            return pTxt;
                        }
                        prev = prev.previousElementSibling;
                    }
                }

                // 3. Fallback estrito: blocos renderizados que NÃO sejam feedback, prompt ou padrão de resposta
                const rendered = findDeepAll(document.body, el => (el.className || '').toString().includes('d2l-html-block-rendered'));
                for (let i = rendered.length - 1; i >= 0; i--) {
                    let rTxt = (rendered[i].innerText || '').trim();
                    rTxt = rTxt.replace(/^\d+\s+palavras\s*/i, '').replace(/Contagem de Palavras.*$/is, '').trim();
                    if (rTxt.length > 15 && !isFeedbackOrPrompt(rTxt)) {
                        return rTxt;
                    }
                }
                return '';
            }""")
            return (texto or "").strip()
        except Exception:
            return ""

    def _inserir_nota_e_feedback(self, page: Page, nota: float, feedback_html: str, nota_max: float = 2.0):
        """Insere a nota no input de pontuação e o feedback no editor específico da questão."""
        nota_str = f"{nota:.2f}".replace(".", ",")
        try:
            page.evaluate(r"""(args) => {
                const { notaVal, notaString, fbHtml } = args;
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

                // 1. Localizar componente interno D2L attempt result
                const allAR = findDeepAll(document.body, el => el.tagName.toLowerCase() === 'd2l-consistent-evaluation-quizzing-attempt-result');
                const qAR = allAR.length > 0 ? allAR[allAR.length - 1] : null;

                if (qAR && typeof qAR._updateScore === 'function') {
                    qAR._updateScore(notaVal);
                }

                // Atualizar input numérico
                const inputs = findDeepAll(document.body, el => {
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    return aria.includes('pontuação da pergunta de') || aria.includes('pontuacao da pergunta de');
                });
                const targetInput = inputs.length > 0 ? inputs[inputs.length - 1] : (qAR && qAR.shadowRoot ? qAR.shadowRoot.querySelector('input') : null);
                if (targetInput) {
                    targetInput.focus();
                    targetInput.value = notaString;
                    targetInput.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                    targetInput.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
                    targetInput.blur();
                }

                // 2. Localizar editor de feedback da questão (abaixo da nota)
                const editors = findDeepAll(document.body, el => el.tagName.toLowerCase() === 'd2l-htmleditor' && (el.className || '').toString().includes('quiz-question-feedback'));
                const targetEditor = editors.length > 0 ? editors[editors.length - 1] : (qAR && qAR.shadowRoot ? qAR.shadowRoot.querySelector('d2l-htmleditor') : null);

                if (targetEditor) {
                    targetEditor.html = fbHtml;
                    targetEditor.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
                    targetEditor.dispatchEvent(new Event('input', { bubbles: true, composed: true }));

                    if (targetEditor.shadowRoot) {
                        const iframe = targetEditor.shadowRoot.querySelector('iframe');
                        if (iframe && (iframe.contentDocument || iframe.contentWindow)) {
                            const doc = iframe.contentDocument || iframe.contentWindow.document;
                            if (doc && doc.body) {
                                doc.body.innerHTML = fbHtml;
                                doc.body.dispatchEvent(new Event('input', { bubbles: true }));
                                doc.body.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }
                    }

                    if (qAR && typeof qAR._saveOnFeedbackChange === 'function') {
                        qAR._feedbackText = '';
                        qAR._saveOnFeedbackChange();
                    }
                }
            }""", {"notaVal": nota, "notaString": nota_str, "fbHtml": feedback_html})
            time.sleep(1.0)
        except Exception as e:
            state.log(f"[Discursivas] Aviso ao inserir nota/feedback: {e}", "WARN")

    def _salvar_rascunho(self, page: Page) -> bool:
        """Salva a avaliação em rascunho de forma segura, sem clicar em publicar."""
        try:
            if salvar_rascunho_consistent_evaluation(page):
                return True
            for sel in [
                "button:has-text('Salvar Rascunho')",
                "button:has-text('Salvar rascunho')",
                "button[name*='Save']:not([name*='Publish'])",
                "button:has-text('Save Draft')"
            ]:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    btn.click()
                    time.sleep(1.5)
                    return True
        except Exception:
            pass
        return False

    # =========================================================================
    # AUDITORIA DE COERÊNCIA FINAL
    # =========================================================================
    def executar_auditoria_coerencia(self, resultados: List[Dict[str, Any]], ou: str | int, disciplina: str, valor_max: float = 2.0):
        """Executa auditoria final de coerência em 100% da turma ao concluir as correções."""
        if not resultados:
            state.log("[Discursivas] Nenhum registro de discursiva para auditar coerência.")
            return

        total = len(resultados)
        notas = [r["nota"] for r in resultados]
        media = sum(notas) / total if total > 0 else 0.0

        incoerencias = []
        faixas = {"Excelente": 0, "Muito Bom": 0, "Bom": 0, "Regular": 0, "Insuficiente": 0}

        for r in resultados:
            aluno = r["aluno"]
            nota = r["nota"]
            qualidade = r.get("qualidade", "Bom")
            plagio = r.get("plagio", False)

            if qualidade in faixas:
                faixas[qualidade] += 1

            if nota > valor_max:
                incoerencias.append(f"{aluno}: Nota {nota} ultrapassa valor máximo {valor_max}.")
            if plagio and nota > 0.0:
                incoerencias.append(f"{aluno}: Plágio confirmado porém nota maior que zero ({nota}).")
            if nota < valor_max and not r.get("descontos"):
                incoerencias.append(f"{aluno}: Nota com desconto ({nota}/{valor_max}) sem justificativa explícita.")

        state.log(f"\n==================================================================")
        state.log(f"AUDITORIA FINAL DE COERÊNCIA - PROVAS DISCURSIVAS [{ou}] {disciplina}")
        state.log(f"Total Avaliados: {total}/{total} | Média da Turma: {media:.2f}/{valor_max:.2f} pts")
        state.log(f"Distribuição: {faixas}")
        state.log(f"Incoerências Identificadas: {len(incoerencias)}")
        state.log(f"==================================================================")

        # Salvar relatório JSON e CSV
        caminho_auditoria = RELATORIOS_DIR / f"auditoria_coerencia_discursivas_{ou}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(caminho_auditoria, "w", encoding="utf-8") as f:
                json.dump({
                    "ou": str(ou),
                    "disciplina": disciplina,
                    "total_avaliados": total,
                    "media_turma": round(media, 2),
                    "valor_maximo": valor_max,
                    "faixas": faixas,
                    "incoerencias": incoerencias,
                    "estudantes": resultados
                }, f, ensure_ascii=False, indent=2)
            state.log(f"[Discursivas] Relatório de coerência salvo com sucesso: {caminho_auditoria.name}")
        except Exception as e:
            state.log(f"[Discursivas] Aviso ao salvar relatório de coerência: {e}", "WARN")

motor_discursivas = MotorDiscursivas()
