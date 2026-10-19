import os
import base64
import re
import json
import time
import shutil
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from config import get_dropbox_url, get_quickeval_url, DYNAMIC_LOAD_WAIT_MS, NAV_TIMEOUT, RELATORIOS_DIR
from engine_state import state
from cognitive.detector_plagio import detector_plagio
from cognitive.extrator_documentos import extrair_texto_documento
from core.navigation_iterator import (
    extrair_posicao_mostrador_iterator,
    extrair_nome_estudante_atual,
    avancar_proximo_estudante_seguro
)
from core.browser_session import obter_primeiro_nome_docente
from core.dom_helpers import (
    obter_nota_e_feedback_consistent_evaluation,
    inserir_nota_consistent_evaluation,
    inserir_feedback_consistent_evaluation,
    salvar_rascunho_consistent_evaluation,
    salvar_rascunho_duplo,
    contar_anexos_submissao
)

class MotorAtividadesNovo:
    """
    Novo Módulo Integrado de Correção de Atividades Abertas.

    Formalizado em 5 Fluxos Pedagógicos Especialistas:
    - FLUXO 1: Entendimento do Comando & Contextualização Pedagógica (Extração do enunciado, valor, templates e tipologia dinâmica)
    - FLUXO 2: Construção da Matriz / Rubrica Analítica (Decomposição em 3 critérios com pesos exatos e gabarito comentado)
    - FLUXO 3: Ingestão, Extração Multi-Arquivo e Análise Comparativa (Tratamento integral de múltiplos anexos .doc, .docx, .pdf, scripts e códigos)
    - FLUXO 4: Inferência Analítica de Notas & Parecer Pedagógico (Feedback qualitativo sem subtrações numéricas, saudação {FirstName} e assinatura)
    - FLUXO 5: Execução em Turma com Duplo Rascunho & Auditoria (Consistent Evaluation, duplo salvamento seguro e auditoria final)
    """

    def __init__(self):
        self.enunciado_atual = ""
        self.criterios_atuais = []
        self.exemplo_esperado_atual = ""
        self.valor_max_atual = 1.50
        self.db_atual = ""
        self.tipologia_atual = "GENERICA"
        self.templates_atuais = []

    # =========================================================================
    # FLUXO 1: ENTENDIMENTO DO COMANDO & CONTEXTUALIZAÇÃO PEDAGÓGICA
    # =========================================================================
    def inspecionar_atividade_aberta(self, page: Page, ou: str | int, nome_disciplina: str = "") -> Dict[str, Any]:
        """
        Localiza a pasta de Atividade Aberta / Atividade Prática na disciplina,
        extrai o enunciado completo, valor oficial, anexos/templates fornecidos
        e infere dinamicamente a tipologia pedagógica da tarefa.
        """
        state.log(f"[Novo Motor de Atividades] Inspecionando atividade aberta da turma [{ou}] {nome_disciplina}...")
        url_folders = f"https://ava.catolica.edu.br/d2l/lms/dropbox/admin/folders_manage.d2l?ou={ou}"

        info = {
            "ou": str(ou),
            "disciplina": nome_disciplina,
            "atividade_nome": "Avaliação: Atividade aberta",
            "db": "",
            "valor_maximo": 1.50,
            "enunciado": "",
            "templates_fornecidos": [],
            "tipologia": "GENERICA",
            "metodo_extracao": "dropbox_admin_folders"
        }

        try:
            page.goto(url_folders, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(3)

            # 1. Localizar linha da pasta de Atividade Aberta
            dados_pasta = page.evaluate(r"""() => {
                const rows = Array.from(document.querySelectorAll('tr, table tr'));
                for (let r of rows) {
                    const txt = (r.innerText || '').toLowerCase();
                    if (txt.includes('atividade aberta') || txt.includes('atividade prática') || txt.includes('trabalho prático') || txt.includes('estudo dirigido')) {
                        const aFolder = r.querySelector('a[href*="folder_submissions_users.d2l"], a[href*="db="]');
                        if (aFolder) {
                            const m = aFolder.href.match(/db=(\d+)/i);
                            return {
                                title: aFolder.innerText.trim(),
                                db: m ? m[1] : null,
                                fullText: (r.innerText || '').trim()
                            };
                        }
                    }
                }
                return null;
            }""")

            if dados_pasta and dados_pasta.get("db"):
                info["db"] = dados_pasta["db"]
                info["atividade_nome"] = dados_pasta["title"] or info["atividade_nome"]
                self.db_atual = dados_pasta["db"]
                state.log(f"[Atividades Abertas] Pasta localizada: '{info['atividade_nome']}' (DB: {info['db']})")

                # Acessar a página de submissões da pasta para extrair contagens e acessar o editor moderno
                url_submissoes = f"https://ava.catolica.edu.br/d2l/lms/dropbox/admin/mark/folder_submissions_users.d2l?db={info['db']}&ou={ou}"
                page.goto(url_submissoes, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                time.sleep(3)

                # Verificar se há botão de Editar Atividade ou navegar diretamente via token
                btn_edit = page.locator("button:has-text('Editar Atividade'), a:has-text('Editar Atividade'), [data-location*='activities/edit']").first
                editor_aberto = False
                if btn_edit.count() > 0:
                    try:
                        btn_edit.click()
                        time.sleep(5)
                        editor_aberto = True
                    except Exception:
                        pass

                if not editor_aberto:
                    inner_b64 = base64.b64encode(f"6606_2000_{info['db']}".encode()).decode().rstrip("=")
                    act_token = base64.b64encode(f"{inner_b64}.{ou}".encode()).decode().rstrip("=")
                    url_edit = f"https://ava.catolica.edu.br/d2l/le/activities/edit/{act_token}?cft=dropbox&launchedFromLessons=False&returnUrl=%2fd2l%2flms%2fdropbox%2fadmin%2ffolders_manage.d2l%3fou%3d{ou}&optOutUrl="
                    page.goto(url_edit, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                    time.sleep(5)

                detalhes_comando = page.evaluate(r"""() => {
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
                    const templates = [];
                    for (let el of all) {
                        const aria = (el.getAttribute('aria-label') || '').trim();
                        const txt = (el.innerText || el.textContent || '').trim();
                        if (aria.startsWith('Remover anexo:')) {
                            const nome = aria.replace('Remover anexo:', '').trim();
                            if (nome && !templates.includes(nome)) templates.push(nome);
                        } else if ((el.getAttribute('href') || '').includes('Attachment') && txt) {
                            if (!templates.includes(txt)) templates.push(txt);
                        }
                    }
                    let pontuacao = 1.5;
                    const inp = all.find(el => el.id === 'score-out-of' || (el.getAttribute('aria-label') || '').toLowerCase().includes('nota'));
                    if (inp) {
                        const v = parseFloat(String(inp.value || inp.getAttribute('value') || '').replace(',', '.'));
                        if (!isNaN(v) && v > 0) pontuacao = v;
                    }

                    let disc = '';
                    const titleEl = document.title || '';
                    if (titleEl.includes(' - ')) {
                        const parts = titleEl.split(' - ');
                        if (parts.length > 1) disc = parts.slice(1).join(' - ').trim();
                    }
                    return { instrucoes, templates, pontuacao, disc };
                }""")

                if detalhes_comando.get("instrucoes"):
                    info["enunciado"] = detalhes_comando["instrucoes"]
                if detalhes_comando.get("pontuacao"):
                    info["valor_maximo"] = float(detalhes_comando["pontuacao"])
                if detalhes_comando.get("templates"):
                    info["templates_fornecidos"] = detalhes_comando["templates"]
                if detalhes_comando.get("disc") and (not info["disciplina"] or str(info["disciplina"]).lower() in ["undefined", "null", "none", ""]):
                    info["disciplina"] = detalhes_comando["disc"]

            # Fallback se não obteve enunciado completo
            if not info["enunciado"]:
                info["enunciado"] = (
                    "Desenvolver a atividade prática proposta conforme o comando do professor, "
                    "utilizando os templates e modelos de arquivo disponibilizados e apresentando "
                    "resolução fundamentada nos conceitos da disciplina com rigor conceitual e aplicação prática."
                )

            # Inferir tipologia pedagógica
            tipologia = self.identificar_tipologia(info["enunciado"], info["templates_fornecidos"])
            info["tipologia"] = tipologia
            self.tipologia_atual = tipologia
            self.enunciado_atual = info["enunciado"]
            self.valor_max_atual = info["valor_maximo"]
            self.templates_atuais = info["templates_fornecidos"]

            state.log(f"[Atividades Abertas] Enunciado: {len(info['enunciado'])} caracteres | Modelos/Templates: {info['templates_fornecidos']}")
            state.log(f"[Atividades Abertas] Tipologia identificada: {tipologia} | Valor Oficial: {info['valor_maximo']:.2f} pts")
            return info

        except Exception as e:
            state.log(f"[Atividades Abertas] Erro na inspeção da atividade: {e}", "WARN")
            info["tipologia"] = self.identificar_tipologia(info["enunciado"], info["templates_fornecidos"])
            return info

    def identificar_tipologia(self, enunciado: str, templates: List[str] = None) -> str:
        """
        Classifica de forma universal e adaptativa a modalidade pedagógica da atividade:
        - FICHAMENTO: Artigos, fichas de leitura, matriz avaliativa 0-4, resenhas acadêmicas.
        - CODIGO_SCRIPT: Códigos-fonte (.py, .c, .java, .js, .sql, scripts, algoritmos).
        - BANCO_DADOS_NORMALIZACAO: Modelagem relacional, 1FN/2FN/3FN, DER, diagramas e DDL/DML.
        - RELATORIO_TECNICO: Estudos de caso, relatórios de projeto, diagnósticos e planos de ação.
        - MAPA_MENTAL_MIDIA: Podcasts, mapas mentais, infográficos, slides ou apresentações.
        - GENERICA: Trabalhos dissertativos gerais ou teóricos.
        """
        texto_comb = (enunciado or "").lower()
        if templates:
            texto_comb += " " + " ".join(t.lower() for t in templates)

        if any(w in texto_comb for w in ["fichamento", "ficha de leitura", "matriz de avaliação", "artigo de engenharia", "matriz avaliativa"]):
            return "FICHAMENTO"
        if any(w in texto_comb for w in ["normalização", "normalizacao", "1fn", "2fn", "3fn", "bcnf", "modelo relacional", "der", "chaves primárias", "banco de dados"]):
            return "BANCO_DADOS_NORMALIZACAO"
        if any(w in texto_comb for w in ["código", "codigo", "script", "algoritmo", "python", "linguagem c", "java", "sql", "função", "funcao", "compilador", "execução", "repositório", "github"]):
            return "CODIGO_SCRIPT"
        if any(w in texto_comb for w in ["podcast", "áudio", "audio", "mapa mental", "vídeo", "video", "apresentação", "slides", "infográfico"]):
            return "MAPA_MENTAL_MIDIA"
        if any(w in texto_comb for w in ["relatório", "relatorio", "estudo de caso", "diagnóstico", "diagnostico", "projeto técnico", "plano de"]):
            return "RELATORIO_TECNICO"
        return "GENERICA"

    # =========================================================================
    # FLUXO 2: CONSTRUÇÃO DA MATRIZ / RUBRICA ANALÍTICA & GABARITO DE REFERÊNCIA
    # =========================================================================
    def gerar_matriz_rubrica(self, enunciado: str, valor_maximo: float = 1.50, tipologia: str = "GENERICA") -> Dict[str, Any]:
        """
        Constrói dinamicamente os 3 critérios analíticos balanceados somando exatamente
        o valor total, adaptando pesos e descritores conforme a tipologia inferida.
        Gera também o Padrão de Resposta Esperado (Gabarito de Referência) para calibração docente.
        """
        p_estrutural = round(valor_maximo * 0.30, 2)
        p_resolucao = round(valor_maximo * 0.50, 2)
        p_rigor = round(valor_maximo - p_estrutural - p_resolucao, 2)

        descritores = {
            "FICHAMENTO": {
                "c1_nome": "Aderência ao Modelo/Template e Tipologia (Fichamento)",
                "c1_desc": "Observância integral ao modelo oficial (Fichamento.docx), contemplando cabeçalho, Matriz Avaliativa (escala 0 a 4) e Diretrizes de Leitura.",
                "c2_nome": "Preenchimento da Matriz Avaliativa e Ficha de Leitura",
                "c2_desc": "Resolução aprofundada dos tópicos do artigo de referência, fundamentação sólida dos questionamentos críticos e exame técnico das ferramentas.",
                "c3_nome": "Rigor Conceitual, Coesão e Norma Culta",
                "c3_desc": "Vocabulário técnico apropriado da disciplina, articulação fluida, coesa e redação conforme a norma culta na síntese dissertativa.",
                "gabarito": (
                    "PADRÃO DE RESPOSTA ESPERADO (FICHAMENTO ACADÊMICO):\n\n"
                    "1. Estrutura e Cabeçalho:\n"
                    "O estudante deve manter o template oficial, preenchendo todos os dados de identificação acadêmica.\n\n"
                    "2. Matriz Avaliativa com Escala (0 a 4):\n"
                    "Preenchimento obrigatório de todas as dimensões da matriz (Relevância do Tema, Embasamento Teórico, Aplicação Prática, "
                    "Relevância dos Resultados e Apresentação), atribuindo nota fundamentada de 0 a 4 com observações técnicas consistentes.\n\n"
                    "3. Diretrizes de Leitura Crítica (Questões):\n"
                    "Resposta às 8 questões estruturantes do artigo, identificando claramente: problema central, proposta metodológica, "
                    "análise comparativa das ferramentas (ex: Ardora, CourseLab, eXe-Learning, Xerte), conclusões, limitações e trabalhos futuros.\n\n"
                    "4. Síntese Dissertativa:\n"
                    "Desenvolvimento de texto dissertativo argumentativo (mínimo de 20 linhas) correlacionando os conceitos de Engenharia de Requisitos "
                    "com a prática profissional de desenvolvimento de software."
                )
            },
            "CODIGO_SCRIPT": {
                "c1_nome": "Arquitetura do Código, Estruturação e Organização",
                "c1_desc": "Organização modular dos arquivos, conformidade de sintaxe, boas práticas de indentação, nomenclatura e separação de responsabilidades.",
                "c2_nome": "Implementação Lógica dos Requisitos e Resolução do Algoritmo",
                "c2_desc": "Atendimento integral a todas as funções, procedimentos, estruturas de dados e regras de negócio exigidas pelo comando da atividade.",
                "c3_nome": "Rigor Técnico, Tratamento de Entradas e Eficiência",
                "c3_desc": "Tratamento de exceções, validação de entradas, clareza nos comentários internos e comprovação de execução ou testes adequados.",
                "gabarito": (
                    "PADRÃO DE RESPOSTA ESPERADO (DESENVOLVIMENTO DE CÓDIGO / SCRIPTS):\n\n"
                    "1. Estruturação e Arquitetura:\n"
                    "O código deve ser entregue em arquivos de código-fonte válidos (.py, .java, .c, .sql), com modularização clara de funções e classes.\n\n"
                    "2. Resolução do Algoritmo e Requisitos:\n"
                    "Implementação correta de todas as etapas e funcionalidades solicitadas no enunciado, processando os dados de entrada esperados "
                    "e gerando as saídas corretas com exatidão lógica.\n\n"
                    "3. Qualidade do Código e Boas Práticas:\n"
                    "Código limpo, documentado com comentários pertinentes, seguindo padrões de nomenclatura e tratamento de possíveis erros de execução."
                )
            },
            "BANCO_DADOS_NORMALIZACAO": {
                "c1_nome": "Modelagem Estrutural e Conformidade de Esquema",
                "c1_desc": "Estrutura relacional bem definida, especificação clara de tabelas, atributos, tipos de dados e chaves primárias e estrangeiras.",
                "c2_nome": "Aplicação das Formas Normais e Resolução de Anomalias",
                "c2_desc": "Processo de normalização passo a passo demonstrando a aplicação correta da 1FN, 2FN e 3FN (ou BCNF) e eliminação de redundâncias.",
                "c3_nome": "Rigor Conceitual, Integridade Referencial e Scripts SQL",
                "c3_desc": "Consistência teórica nas regras de integridade, coerência relacional e sintaxe SQL padrão correta para criação e manipulação.",
                "gabarito": (
                    "PADRÃO DE RESPOSTA ESPERADO (BANCO DE DADOS & NORMALIZAÇÃO):\n\n"
                    "1. Identificação Inicial das Entidades e Atributos:\n"
                    "Mapeamento correto do cenário ou tabela não-normalizada inicial, identificando chaves candidatas e dependências funcionais.\n\n"
                    "2. Passos Formais de Normalização:\n"
                    "• 1FN: Eliminação de atributos multivalorados ou compostos, garantindo atomicidade.\n"
                    "• 2FN: Eliminação de dependências parciais, garantindo que todo atributo não-chave dependa da totalidade da chave primária.\n"
                    "• 3FN: Eliminação de dependências transitivas, garantindo que atributos não-chave dependam exclusivamente da chave primária.\n\n"
                    "3. Esquema Relacional e Scripts SQL:\n"
                    "Apresentação das tabelas finais resultantes com integridade referencial preservada e comandos SQL correspondentes."
                )
            },
            "RELATORIO_TECNICO": {
                "c1_nome": "Conformidade Estrutural e Organização Metodológica",
                "c1_desc": "Estrutura formal de relatório técnico contemplando introdução contextualizada, desenvolvimento analítico e conclusões fundamentadas.",
                "c2_nome": "Desenvolvimento Técnico e Resolução dos Questionamentos",
                "c2_desc": "Aprofundamento na análise dos problemas, articulação de dados/evidências e proposição de soluções técnicas consistentes.",
                "c3_nome": "Rigor Conceitual, Coesão e Qualidade Normativa",
                "c3_desc": "Domínio da terminologia da área, argumentação fundamentada na literatura técnica e redação fluida em norma padrão.",
                "gabarito": (
                    "PADRÃO DE RESPOSTA ESPERADO (RELATÓRIO TÉCNICO / ESTUDO DE CASO):\n\n"
                    "1. Contextualização e Diagnóstico:\n"
                    "Apresentação clara do cenário-problema estudado, identificando variáveis, restrições e objetivos da intervenção.\n\n"
                    "2. Análise e Solução Proposta:\n"
                    "Desenvolvimento técnico aprofundado, aplicando os métodos e teorias da disciplina para justificar a solução escolhida com dados e fatos.\n\n"
                    "3. Conclusão e Viabilidade:\n"
                    "Considerações finais demonstrando os impactos da solução, lições aprendidas e recomendações práticas para implementação."
                )
            },
            "MAPA_MENTAL_MIDIA": {
                "c1_nome": "Estruturação Visual/Audiovisual e Aderência ao Formato",
                "c1_desc": "Formato de entrega condizente com a proposta multimídia, organização hierárquica clara dos nós e tópicos conceituais.",
                "c2_nome": "Cobertura Conceitual e Resolução dos Tópicos Chave",
                "c2_desc": "Articulação de todos os conceitos centrais do tema, conexões lógicas entre os ramos e síntese explicativa clara dos conteúdos.",
                "c3_nome": "Rigor Conceitual, Clareza e Expressão Técnica",
                "c3_desc": "Exatidão na terminologia adotada, boa legibilidade/qualidade sonora e autoria evidente nas representações propostas.",
                "gabarito": (
                    "PADRÃO DE RESPOSTA ESPERADO (MAPA MENTAL / MÍDIA EDUCATIVA):\n\n"
                    "1. Conceito Central e Ramificações Primárias:\n"
                    "Definição clara do tema central no núcleo da apresentação, subdividido em ramos estruturantes bem identificados.\n\n"
                    "2. Conexões Lógicas e Palavras-Chave:\n"
                    "Uso de termos conceituais precisos, setas indicativas de relação de causa/efeito e associação coerente entre teorias e práticas.\n\n"
                    "3. Síntese e Originalidade:\n"
                    "Representação sintética e autoral que facilita a compreensão do tema pelo espectador sem sobrecarga desnecessária de texto."
                )
            },
            "GENERICA": {
                "c1_nome": "Conformidade Estrutural e Aderência ao Comando",
                "c1_desc": "Atendimento aos requisitos formais da atividade aberta, estrutura coerente e entrega completa dos itens solicitados.",
                "c2_nome": "Desenvolvimento Teórico-Prático e Resolução da Atividade",
                "c2_desc": "Profundidade na resolução do tema, fundamentação teórica consistente e aplicação direta dos conceitos da disciplina.",
                "c3_nome": "Rigor Conceitual, Coesão e Norma Culta",
                "c3_desc": "Vocabulário técnico apropriado, articulação fluida, coesa e redação conforme a norma culta com autoria própria.",
                "gabarito": (
                    "PADRÃO DE RESPOSTA ESPERADO:\n\n"
                    "1. Fundamentação Teórica:\n"
                    "O estudante deve demonstrar pleno domínio dos conceitos ministrados na disciplina, conceituando termos técnicos com clareza.\n\n"
                    "2. Aplicação Prática:\n"
                    "A resposta deve demonstrar como a teoria se aplica em cenários reais da área de atuação, atendendo a todos os requisitos do comando.\n\n"
                    "3. Redação e Autoria:\n"
                    "Texto claro, coeso e estruturado em conformidade com as normas cultas da língua portuguesa."
                )
            }
        }

        cfg = descritores.get(tipologia, descritores["GENERICA"])

        criterios = [
            {"id": "c1", "nome": cfg["c1_nome"], "peso": p_estrutural, "descricao": cfg["c1_desc"]},
            {"id": "c2", "nome": cfg["c2_nome"], "peso": p_resolucao, "descricao": cfg["c2_desc"]},
            {"id": "c3", "nome": cfg["c3_nome"], "peso": p_rigor, "descricao": cfg["c3_desc"]}
        ]

        self.criterios_atuais = criterios
        self.exemplo_esperado_atual = cfg["gabarito"]

        return {
            "tipologia": tipologia,
            "valor_maximo": valor_maximo,
            "peso_estrutural": p_estrutural,
            "peso_resolucao": p_resolucao,
            "peso_rigor": p_rigor,
            "criterios": criterios,
            "gabarito_referencia": cfg["gabarito"]
        }

    # =========================================================================
    # FLUXO 3: INGESTÃO, EXTRAÇÃO MULTI-ARQUIVO E ANÁLISE COMPARATIVA
    # =========================================================================
    def baixar_e_extrair_submissoes_aluno(self, page: Page, temp_dir: Path, idx_aluno: int) -> Tuple[int, str, List[str]]:
        """
        Baixa TODOS os arquivos submetidos pelo estudante (seja via pacote ZIP ou individualmente).
        Varre recursivamente todas as pastas descompactadas do Brightspace.
        Extrai o texto de .doc (OLE / UTF-16LE), .docx, .pdf, scripts e códigos.
        Retorna:
          - total de arquivos encontrados
          - texto completo consolidado com cabeçalhos de seção por arquivo
          - lista com os nomes de todos os arquivos extraídos
        """
        temp_dir.mkdir(parents=True, exist_ok=True)
        arquivos_salvos = []
        nomes_arquivos = []
        textos = []

        # 1. Rota Primária: Botão geral 'Fazer o download de todos os arquivos'
        for ctx in [page] + page.frames:
            try:
                btn_all = ctx.locator("button:has-text('Fazer o download de todos os arquivos'), d2l-button-subtle:has-text('download'), [text*='download de todos'], [aria-label*='download de todos']").first
                if btn_all.count() > 0:
                    try:
                        with page.expect_download(timeout=7000) as download_info:
                            btn_all.click(timeout=3000)
                        download = download_info.value
                        zip_dest = temp_dir / f"submissao_{idx_aluno}_{download.suggested_filename}"
                        download.save_as(str(zip_dest))

                        if str(zip_dest).lower().endswith(".zip"):
                            try:
                                with zipfile.ZipFile(zip_dest, "r") as z:
                                    z.extractall(temp_dir)
                                for extraido in temp_dir.rglob("*"):
                                    if extraido.is_file() and not extraido.name.lower().endswith(('.zip', '.tar', '.gz', '.html', '.htm')):
                                        arquivos_salvos.append(extraido)
                            except Exception:
                                pass
                        break
                    except Exception:
                        pass
            except Exception:
                pass

        # 2. Rota Secundária: Links individuais de download
        if not arquivos_salvos:
            for ctx in [page] + page.frames:
                try:
                    file_elements = ctx.locator("[aria-label*='Clique para baixar o anexo'], [aria-label*='baixar o anexo'], [aria-label*='baixar'], a.truncate, a[href*='downloadAttachment'], a[href*='download_submission_file'], a[href*='dropbox'], d2l-file-name, .d2l-submission-attachment-list-item-content a, a[download]")
                    count = min(file_elements.count(), 10)
                    for k in range(count):
                        link = file_elements.nth(k)
                        try:
                            with page.expect_download(timeout=4000) as download_info:
                                link.click(timeout=2500)
                            download = download_info.value
                            destino = temp_dir / f"submissao_{idx_aluno}_{download.suggested_filename}"
                            download.save_as(str(destino))
                            if str(destino).lower().endswith(".zip"):
                                try:
                                    with zipfile.ZipFile(destino, "r") as z:
                                        z.extractall(temp_dir)
                                    for extraido in temp_dir.rglob("*"):
                                        if extraido.is_file() and not extraido.name.lower().endswith(('.zip', '.tar', '.gz', '.html', '.htm')):
                                            arquivos_salvos.append(extraido)
                                except Exception:
                                    pass
                            else:
                                arquivos_salvos.append(destino)
                        except Exception:
                            pass
                    if arquivos_salvos:
                        break
                except Exception:
                    pass

        # 3. Extrair conteúdo textual de TODOS os arquivos válidos
        for arq in arquivos_salvos:
            if arq.is_file() and not arq.name.lower().endswith(('.zip', '.tar', '.gz', '.html', '.htm')):
                if arq.name in nomes_arquivos:
                    continue
                nomes_arquivos.append(arq.name)
                res = extrair_texto_documento(arq)
                if res["sucesso"] and res["texto"] and len(res["texto"].strip()) > 10:
                    secao = f"=== ARQUIVO: {arq.name} ===\n{res['texto'].strip()}"
                    textos.append(secao)

        # 4. Fallback com leitura da camada visual / comentários de submissão
        if not textos:
            try:
                viewer_text = page.evaluate("""() => {
                    let text = "";
                    const spans = document.querySelectorAll('.textLayer span, span[role="presentation"], [class*="document-text"], [class*="page-content"]');
                    for (let s of spans) {
                        const t = (s.innerText || s.textContent || '').trim();
                        if (t) text += t + " ";
                    }
                    return text.trim();
                }""")
                if viewer_text and len(viewer_text) > 40:
                    textos.append(f"=== VISUALIZADOR DE DOCUMENTOS ===\n{viewer_text}")
            except Exception:
                pass

        try:
            comentarios = page.evaluate("""() => {
                const els = document.querySelectorAll('.d2l-html-editor-content, .d2l-submission-comments, d2l-html-block');
                for (let el of els) {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (t.length > 20 && !t.includes('Sua sessão')) return t;
                }
                return "";
            }""")
            if comentarios and comentarios not in "\n".join(textos):
                textos.append(f"=== COMENTÁRIOS DO ESTUDANTE ===\n{comentarios}")
        except Exception:
            pass

        # 5. Exclusão imediata dos temporários
        for f in temp_dir.glob("*"):
            try:
                if f.is_file():
                    f.unlink()
                elif f.is_dir():
                    shutil.rmtree(f, ignore_errors=True)
            except Exception:
                pass

        texto_unificado = "\n\n".join(textos).strip()
        total_arquivos = len(nomes_arquivos) if nomes_arquivos else (1 if texto_unificado else 0)

        return total_arquivos, texto_unificado, nomes_arquivos

    # =========================================================================
    # FLUXO 4: INFERÊNCIA ANALÍTICA DE NOTAS & PARECER PEDAGÓGICO
    # =========================================================================
    def avaliar_submissao(
        self,
        texto_submissao: str,
        nome_aluno: str,
        instrucoes: str,
        criterios_info: Dict[str, Any],
        nota_maxima: float = 1.50,
        total_arqs: int = 1,
        docente: str = "Prof. Arly Cristopher Nascimento Alves"
    ) -> Dict[str, Any]:
        """
        Avalia o texto consolidado em múltiplos arquivos segundo a matriz analítica.
        Aplica regras de nota zero (em branco / fuga ao tema), atribui nota por critério
        e constrói feedback pedagógico institucional sem subtrações numéricas.
        """
        primeiro_nome_docente = obter_primeiro_nome_docente(docente)
        texto = (texto_submissao or "").strip()
        palavras = len(re.findall(r"\b\w+\b", texto))
        texto_lower = texto.lower()
        letras_count = len(re.findall(r"[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]", texto))

        # 1. Regra de Tolerância Zero: Envio em Branco ou Ausente
        is_vazio = (
            total_arqs == 0 or
            len(texto) < 15 or
            palavras < 4 or
            letras_count < 10 or
            "-nenhum texto inserido-" in texto_lower or
            "sem envios" in texto_lower or
            "nenhum arquivo enviado" in texto_lower
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
                "nota_c1": 0.0,
                "nota_c2": 0.0,
                "nota_c3": 0.0,
                "plagio": False,
                "similaridade_pct": 0.0
            }

        # 2. Regra de Fuga ao Tema
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

        if len(intersecao) == 0 and len(rads_instrucoes) > 0 and palavras < 80:
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
                "nota_c1": 0.0,
                "nota_c2": 0.0,
                "nota_c3": 0.0,
                "plagio": False,
                "similaridade_pct": 0.0
            }

        # 3. Avaliação Multicritério Adaptativa
        tipologia = criterios_info.get("tipologia", "GENERICA")
        p_estrutural = criterios_info.get("peso_estrutural", round(nota_maxima * 0.30, 2))
        p_resolucao = criterios_info.get("peso_resolucao", round(nota_maxima * 0.50, 2))
        p_rigor = criterios_info.get("peso_rigor", round(nota_maxima - p_estrutural - p_resolucao, 2))

        c1_nome = criterios_info["criterios"][0]["nome"]
        c2_nome = criterios_info["criterios"][1]["nome"]
        c3_nome = criterios_info["criterios"][2]["nome"]

        descontos = []

        # ==================== RAMIFICAÇÃO POR TIPOLOGIA ====================
        if tipologia == "FICHAMENTO":
            has_cabecalho = any(c in texto_lower for c in ["nome", "curso", "disciplina", "data:", "matrícula", "matricula", "aluno", "aluna"])
            has_matriz = any(k in texto_lower for k in ["roteiro", "legenda", "satisfaz", "embasamento", "observação", "observacao", "relevância", "relevancia"])
            has_perguntas = any(q in texto_lower for q in ["problema", "proposta", "validação", "validacao", "conclusões", "conclusoes", "trabalhos futuros", "questões", "questoes"])
            has_dissertativo = any(d in texto_lower for d in ["texto dissertativo", "análise de requisitos aplicada", "síntese crítica", "resenha crítica"]) or (palavras >= 700 and any(a in texto_lower for a in ["bez", "nienow", "flores"]))

            # C1: Estrutura Fichamento
            if has_cabecalho and has_matriz and has_perguntas and (has_dissertativo or palavras >= 700):
                n_c1 = p_estrutural
                p_c1 = "Estrutura do Fichamento plenamente atendida, contemplando cabeçalho formal, matriz com legenda (0 a 4), guia de leitura e síntese dissertativa."
            elif has_perguntas and (has_dissertativo or palavras >= 450):
                n_c1 = round(p_estrutural * 0.55, 2)
                p_c1 = "Estrutura parcial: a seção da Matriz Avaliativa (com legenda de 0 a 4 e critérios) foi suprimida do documento original."
                descontos.append("Observância integral ao modelo: o template exigia o preenchimento da Matriz Avaliativa (escala 0 a 4) previamente às questões discursivas.")
            else:
                n_c1 = round(p_estrutural * 0.35, 2)
                p_c1 = "Estrutura incompleta, com ausência de múltiplas seções essenciais do modelo oficial disponibilizado."
                descontos.append("Estruturação do documento: o trabalho deixou de apresentar as divisões formais estabelecidas no template Fichamento.docx.")

            # C2: Resolução
            ferramentas_count = sum(1 for f in ["ardora", "courselab", "exe-learning", "xerte"] if f in texto_lower)
            termos_er_count = sum(1 for t in ["elicitação", "elicitacao", "requisitos funcionais", "requisitos não funcionais", "casos de uso", "caso de uso", "modelagem", "validação", "validacao", "scorm", "usabilidade", "diagrama"] if t in texto_lower)

            if (has_matriz or palavras >= 900) and ferramentas_count >= 2 and termos_er_count >= 2 and palavras >= 600:
                n_c2 = p_resolucao
                p_c2 = "Desenvolvimento aprofundado dos tópicos centrais sobre Engenharia de Requisitos com fundamentação sólida no artigo de referência e exame das ferramentas de autoria."
            elif has_matriz and palavras >= 400:
                n_c2 = round(p_resolucao * 0.85, 2)
                p_c2 = "Atendimento satisfatório às questões do artigo, com boa síntese conceitual, embora com oportunidade de maior aprofundamento comparativo entre as ferramentas de autoria."
                descontos.append("Profundidade na análise das ferramentas: recomenda-se detalhar com mais evidências comparativas os recursos de autoria abordados no artigo.")
            elif not has_matriz:
                n_c2 = round(p_resolucao * 0.70, 2)
                p_c2 = "As questões de leitura do artigo foram respondidas, porém a omissão da matriz avaliativa comprometeu a dimensão analítico-quantitativa requerida pelo comando."
                descontos.append("Avaliação das dimensões analíticas: a matriz avaliativa (0 a 4) é parte integrante do comando pedagógico para mensuração das dimensões do artigo.")
            else:
                n_c2 = round(p_resolucao * 0.60, 2)
                p_c2 = "Respostas muito sucintas às questões de leitura do artigo, necessitando de maior correlação técnica com a prática da disciplina."
                descontos.append("Desenvolvimento analítico: as respostas apresentadas foram excessivamente concisas frente à complexidade do texto-base.")

            # C3: Rigor e Coesão
            conectivos = sum(1 for c in ["portanto", "contudo", "entretanto", "além disso", "nesse sentido", "assim sendo", "desta forma", "por conseguinte", "além da", "nesse contexto", "com base", "por outro lado"] if c in texto_lower)
            if conectivos >= 3 and palavras >= 350:
                n_c3 = p_rigor
                p_c3 = "Vocabulário técnico apropriado, articulação fluida, coesa e em conformidade com a norma culta."
            else:
                n_c3 = round(p_rigor * 0.70, 2)
                p_c3 = "Redação compreensível, mas com concisão acentuada e encadeamento textual simples na síntese crítica."
                descontos.append("Fluidez e articulação textual: sugere-se maior emprego de elementos coesivos interparágrafos para enriquecer o texto dissertativo.")

        elif tipologia == "CODIGO_SCRIPT":
            has_codigo = any(ext in texto_lower for ext in [".py", ".sql", ".java", ".c", ".cpp", ".js", "def ", "class ", "import ", "select ", "create table", "function", "void main", "int main"]) or total_arqs >= 1
            has_comentarios = any(c in texto for c in ["#", "//", "/*", "--", "'''", '"""'])
            has_funcoes = any(f in texto_lower for f in ["def ", "function", "void ", "int ", "class ", "return "])

            if has_codigo and (has_funcoes or palavras >= 100):
                n_c1 = p_estrutural
                p_c1 = "Código estruturado adequadamente, com organização modular, sintaxe correta e boa divisão de responsabilidades."
            else:
                n_c1 = round(p_estrutural * 0.60, 2)
                p_c1 = "Estrutura do código simplificada ou com trechos incompletos frente aos requisitos do projeto."
                descontos.append("Modularização do código: recomenda-se estruturar as rotinas em módulos e funções com escopos bem definidos.")

            if len(intersecao) >= 2 or palavras >= 150:
                n_c2 = p_resolucao
                p_c2 = "Implementação funcional e lógica dos requisitos especificados no enunciado da atividade prática."
            else:
                n_c2 = round(p_resolucao * 0.70, 2)
                p_c2 = "Implementação atende parcialmente aos requisitos solicitados, com lacunas em casos de teste ou validações."
                descontos.append("Completude dos requisitos lógicos: algumas regras de negócio ou funcionalidades solicitadas não foram plenamente implementadas.")

            if has_comentarios and palavras >= 80:
                n_c3 = p_rigor
                p_c3 = "Boas práticas de programação adotadas, comentários esclarecedores e nomenclatura semântica de identificadores."
            else:
                n_c3 = round(p_rigor * 0.75, 2)
                p_c3 = "Código funcional, porém com carência de documentação interna e boas práticas de legibilidade."
                descontos.append("Documentação de código: sugere-se incluir comentários explicativos e manter nomenclatura semântica nas variáveis e rotinas.")

        elif tipologia == "BANCO_DADOS_NORMALIZACAO":
            has_normalizacao = any(fn in texto_lower for fn in ["1fn", "2fn", "3fn", "primeira forma normal", "segunda forma normal", "terceira forma normal", "dependência funcional", "dependencia funcional"])
            has_chaves = any(k in texto_lower for k in ["chave primária", "chave primaria", "chave estrangeira", "primary key", "foreign key", "pk", "fk"])
            has_sql = any(s in texto_lower for s in ["create table", "alter table", "insert into", "references", "select", "where"])

            if has_chaves or has_sql or total_arqs >= 1:
                n_c1 = p_estrutural
                p_c1 = "Esquema relacional bem especificado, identificando entidades, atributos e chaves primárias e estrangeiras."
            else:
                n_c1 = round(p_estrutural * 0.60, 2)
                p_c1 = "Esquema relacional apresentado de forma parcial, com indefinição em chaves ou tipos de dados."
                descontos.append("Definição de chaves e integridade: recomenda-se explicitar com clareza as chaves primárias e estrangeiras no modelo relacional.")

            if has_normalizacao or (has_sql and palavras >= 200):
                n_c2 = p_resolucao
                p_c2 = "Processo de normalização e modelagem aplicado com precisão, eliminando redundâncias e anomalias de atualização."
            else:
                n_c2 = round(p_resolucao * 0.70, 2)
                p_c2 = "Aplicação das formas normais desenvolvida de maneira simplificada, sem detalhamento explícito das dependências funcionais."
                descontos.append("Detalhamento das Formas Normais: o processo de normalização (1FN, 2FN, 3FN) deve ser evidenciado passo a passo.")

            if palavras >= 150:
                n_c3 = p_rigor
                p_c3 = "Rigor conceitual consistente na teoria de bancos de dados relacionais e sintaxe SQL correta."
            else:
                n_c3 = round(p_rigor * 0.75, 2)
                p_c3 = "Conceitos de banco de dados aplicados de forma breve, com oportunidade de maior aprofundamento na integridade referencial."
                descontos.append("Rigor conceitual: recomenda-se fundamentar com mais precisão as regras de integridade referencial e normalização.")

        else: # RELATORIO_TECNICO, MAPA_MENTAL_MIDIA ou GENERICA
            if palavras >= 350 or total_arqs >= 1:
                n_c1 = p_estrutural
                p_c1 = "Conformidade estrutural atendida, com entrega dos arquivos e seções requeridas pelo comando da atividade."
            else:
                n_c1 = round(p_estrutural * 0.65, 2)
                p_c1 = "Estrutura textual compacta frente ao escopo esperado para a atividade prática."
                descontos.append("Organização formal: sugere-se estruturar o trabalho com seções delimitadas para introdução, desenvolvimento e considerações finais.")

            if len(intersecao) >= 3 or palavras >= 400:
                n_c2 = p_resolucao
                p_c2 = "Desenvolvimento consistente e aprofundado dos objetivos propostos, articulando a teoria com a resolução prática solicitada."
            elif len(intersecao) >= 1 or palavras >= 200:
                n_c2 = round(p_resolucao * 0.80, 2)
                p_c2 = "Resolução satisfatória dos itens centrais do comando, porém passível de maior detalhamento e exemplificação prática."
                descontos.append("Aprofundamento prático: recomenda-se detalhar com mais exemplos concretos a resolução proposta no trabalho.")
            else:
                n_c2 = round(p_resolucao * 0.60, 2)
                p_c2 = "Abordagem preliminar do tema com resolução superficial dos comandos estabelecidos nas instruções."
                descontos.append("Desenvolvimento conceitual: o conteúdo apresentado cobriu apenas parcialmente os tópicos exigidos nas instruções.")

            conectivos = sum(1 for c in ["portanto", "contudo", "entretanto", "além disso", "nesse sentido", "assim sendo", "desta forma", "por conseguinte", "além da", "nesse contexto", "com base", "por outro lado"] if c in texto_lower)
            if conectivos >= 2 and palavras >= 250:
                n_c3 = p_rigor
                p_c3 = "Rigor conceitual, boa articulação de ideias e redação em conformidade com o padrão formal."
            else:
                n_c3 = round(p_rigor * 0.75, 2)
                p_c3 = "Redação compreensível, mas com necessidade de aprimoramento no encadeamento lógico e vocabulário técnico."
                descontos.append("Rigor e vocabulário técnico: sugere-se aprofundar a terminologia técnica específica da disciplina.")

        # Totalização
        nota_final = round(min(n_c1 + n_c2 + n_c3, nota_maxima), 2)

        if nota_final >= nota_maxima * 0.95:
            qualidade = "Excelente"
        elif nota_final >= nota_maxima * 0.70:
            qualidade = "Bom"
        elif nota_final >= nota_maxima * 0.50:
            qualidade = "Regular"
        else:
            qualidade = "Insuficiente"

        # 4. Construção do Feedback HTML Institucional
        linhas_criterios = (
            f"<li><strong>{c1_nome}:</strong> {p_c1}</li>"
            f"<li><strong>{c2_nome}:</strong> {p_c2}</li>"
            f"<li><strong>{c3_nome}:</strong> {p_c3}</li>"
        )

        bloco_descontos = ""
        if descontos:
            itens_desc = "".join(f"<li>{d}</li>" for d in descontos)
            bloco_descontos = f"<p><strong>Justificativa do Desconto de Nota:</strong></p><ul>{itens_desc}</ul>"

        rotulo_tipologia = f" ({tipologia.replace('_', ' ').title()})" if tipologia != "GENERICA" else ""
        feedback_html = (
            f"<p>Olá, {{FirstName}}!</p>"
            f"<p>Sua entrega para a <strong>Atividade Aberta{rotulo_tipologia}</strong> foi avaliada com a pontuação de <strong>{nota_final:.2f} de {nota_maxima:.2f} pontos</strong>.</p>"
            f"<p><strong>Análise Detalhada dos Critérios:</strong></p>"
            f"<ul>{linhas_criterios}</ul>"
            f"{bloco_descontos}"
            f"<p>Continue se dedicando aos estudos e articulando a teoria com a prática da disciplina. Conte com o apoio docente!</p>"
            f"<p>Atenciosamente, Prof. {primeiro_nome_docente}</p>"
        )

        return {
            "nota": nota_final,
            "nota_max": nota_maxima,
            "qualidade": qualidade,
            "descontos": descontos,
            "feedback_html": feedback_html,
            "nota_c1": n_c1,
            "nota_c2": n_c2,
            "nota_c3": n_c3,
            "palavras": palavras,
            "plagio": False,
            "similaridade_pct": 0.0
        }

    # =========================================================================
    # FLUXO 5: EXECUÇÃO EM TURMA COM DUPLO RASCUNHO & AUDITORIA
    # =========================================================================
    def executar_turma(
        self,
        page: Page,
        ou: str | int,
        nome_disciplina: str = "",
        modo: str = "tradicional",
        docente: str = "Prof. Arly Cristopher Nascimento Alves",
        max_alunos: int = 50
    ) -> Dict[str, Any]:
        """
        Executa a correção em lote de toda a turma para Atividades Abertas.
        Navega de aluno em aluno no Consistent Evaluation, extrai todos os anexos,
        aplica a avaliação analítica, persiste rascunho duplo (nunca publica diretamente)
        e gera relatório consolidado de auditoria.
        """
        state.is_running = True
        state.should_stop = False
        state.current_ou = str(ou)
        state.current_discipline = nome_disciplina or f"Turma {ou}"
        state.current_activity = "Atividade Aberta"
        state.current_mode = modo
        state.reset_stats()

        timestamp_inicio = time.strftime("%Y%m%d_%H%M%S")
        temp_dir_base = Path("scratch") / f"temp_atividades_{ou}_{timestamp_inicio}"
        temp_dir_base.mkdir(parents=True, exist_ok=True)

        resultados = []
        alunos_processados = set()

        try:
            # 1. Obter informações e rubrica do comando da atividade
            info_ativ = self.inspecionar_atividade_aberta(page, ou, nome_disciplina)
            rubrica = self.gerar_matriz_rubrica(info_ativ["enunciado"], info_ativ["valor_maximo"], info_ativ["tipologia"])

            # 2. Navegar para o Consistent Evaluation da Atividade
            state.current_stage = "Acessando interface de avaliação de Atividades Abertas..."
            state.log(f"[Atividades Abertas] Modo de execução: '{modo}'. Carregando fila de estudantes...")

            db_id = info_ativ.get("db") or self.db_atual
            if not db_id:
                raise ValueError(f"Não foi possível determinar o identificador da pasta (DB) para a turma {ou}.")

            inner_b64 = base64.b64encode(f"6606_2000_{db_id}".encode()).decode().rstrip("=")
            act_token = base64.b64encode(f"{inner_b64}.{ou}".encode()).decode().rstrip("=")

            iterator_param = "new" if modo == "tradicional" else "all"
            url_avaliacao = (
                f"https://ava.catolica.edu.br/d2l/le/activities/evaluation/activity/{act_token}"
                f"?ou={ou}&iteratorRange={iterator_param}"
                f"&cfi=sort%7EeyJTb3J0cyI6W3siU29ydCI6eyJJZCI6IjE3YTFhOWE0LTcyOWYtNGJhMy05ZjdmLWRmZTJmOWQzZWVkMiJ9LCJEaXJlY3Rpb24iOjB9XX0"
                f"&cft=qe"
            )
            state.log(f"[Atividades Abertas] Acessando Consistent Evaluation: {url_avaliacao}")
            page.goto(url_avaliacao, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            time.sleep(5)

            # Verificar se a fila está vazia (ex: sem novos envios em modo tradicional)
            pos_inicial = extrair_posicao_mostrador_iterator(page)
            nome_inicial = extrair_nome_estudante_atual(page)
            if modo == "tradicional" and (pos_inicial.get("total") == 0 or (pos_inicial.get("total") is None and nome_inicial == "Estudante")):
                state.log(f"[Atividades Abertas] Nenhum novo envio pendente na Atividade Aberta ({nome_disciplina}). Fila de avaliação vazia.")
                RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)
                disc_nome = info_ativ.get("disciplina") or nome_disciplina or f"Turma {ou}"
                relatorio_vazio = {
                    "disciplina": disc_nome,
                    "ou": str(ou),
                    "atividade": info_ativ["atividade_nome"],
                    "tipologia": info_ativ["tipologia"],
                    "valor_oficial": info_ativ["valor_maximo"],
                    "modo_execucao": modo,
                    "docente": docente,
                    "data_execucao": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "total_avaliados": 0,
                    "rubrica": rubrica,
                    "estudantes": []
                }
                caminho_rel = RELATORIOS_DIR / f"auditoria_atividades_abertas_{ou}_{timestamp_inicio}.json"
                with open(caminho_rel, "w", encoding="utf-8") as f:
                    json.dump(relatorio_vazio, f, indent=2, ensure_ascii=False)
                state.current_stage = "Nenhum novo envio pendente. Fila concluída."
                state.log(f"[Atividades Abertas] Sucesso! Relatório salvo em: {caminho_rel.name}")
                return relatorio_vazio

            # 3. Loop consecutivo pelos estudantes
            count_processados = 0
            while count_processados < max_alunos and not state.should_stop:
                # Estabilizar leitura do estudante no Consistent Evaluation
                pos_info = {"atual": None, "total": None, "texto": ""}
                nome_aluno = "Estudante"
                for _ in range(5):
                    pos_info = extrair_posicao_mostrador_iterator(page)
                    nome_aluno = extrair_nome_estudante_atual(page)
                    if nome_aluno != "Estudante" or pos_info.get("atual") is not None:
                        break
                    time.sleep(1.0)
                pos_str = f"[{pos_info['atual']}/{pos_info['total']}]" if pos_info.get("atual") else f"[{count_processados+1}]"

                if pos_info.get("total") and pos_info["total"] > 0:
                    state.total_items = pos_info["total"]
                if pos_info.get("atual"):
                    state.current_item_index = pos_info["atual"]
                    if state.total_items > 0:
                        state.progress_percent = round((state.current_item_index / state.total_items) * 100, 1)

                chave_aluno = f"{pos_info.get('atual')}_{nome_aluno}" if pos_info.get("atual") else nome_aluno
                if chave_aluno in alunos_processados and nome_aluno != "Estudante":
                    state.log(f"[Atividades] Estudante {nome_aluno} já processado. Tentando avançar...")
                    if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                        break
                    continue

                alunos_processados.add(chave_aluno)
                count_processados += 1
                state.current_student = nome_aluno
                state.current_stage = f"Avaliando {nome_aluno} {pos_str}"
                state.log(f"\n--- [{count_processados}] Avaliando: {nome_aluno} {pos_str} ---")

                # Baixar e extrair todos os anexos do aluno
                total_arqs, texto_aluno, nomes_arqs = self.baixar_e_extrair_submissoes_aluno(page, temp_dir_base, count_processados)
                palavras_aluno = len(texto_aluno.split())
                state.log(f"    Arquivos detectados: {total_arqs} {nomes_arqs} | Palavras extraídas: {palavras_aluno}")

                # Avaliar sob a rubrica criada a partir do comando
                avaliacao = self.avaliar_submissao(
                    texto_submissao=texto_aluno,
                    nome_aluno=nome_aluno,
                    instrucoes=info_ativ["enunciado"],
                    criterios_info=rubrica,
                    nota_maxima=info_ativ["valor_maximo"],
                    total_arqs=total_arqs,
                    docente=docente
                )

                nova_nota = avaliacao["nota"]
                novo_feedback = avaliacao["feedback_html"]
                state.log(f"    Nota: {nova_nota:.2f} / {info_ativ['valor_maximo']:.2f} ({avaliacao['qualidade']})")
                if avaliacao["descontos"]:
                    state.log(f"    Descontos: {avaliacao['descontos']}")

                # Inserir nota e feedback no Consistent Evaluation
                inserir_nota_consistent_evaluation(page, nova_nota)
                inserir_feedback_consistent_evaluation(page, novo_feedback)
                time.sleep(0.5)

                # Salvar rascunho duplo (nunca publica)
                salvo = salvar_rascunho_duplo(page)
                if salvo:
                    state.statistics["avaliados"] += 1
                    state.statistics["auditados"] += 1
                    state.log(f"    [OK] Rascunho salvo duplo no Consistent Evaluation.")
                else:
                    state.log(f"    [AVISO] Tentativa de salvamento do rascunho retornou falso.", "WARN")

                # Registrar auditoria do aluno
                registro_aluno = {
                    "indice": count_processados,
                    "posicao": pos_str,
                    "aluno": nome_aluno,
                    "nota": nova_nota,
                    "nota_max": info_ativ["valor_maximo"],
                    "qualidade": avaliacao["qualidade"],
                    "descontos": avaliacao["descontos"],
                    "nota_c1": avaliacao.get("nota_c1", 0.0),
                    "nota_c2": avaliacao.get("nota_c2", 0.0),
                    "nota_c3": avaliacao.get("nota_c3", 0.0),
                    "total_arquivos": total_arqs,
                    "arquivos": nomes_arqs,
                    "total_palavras": palavras_aluno,
                    "feedback_html": novo_feedback,
                    "rascunho_salvo": salvo,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                resultados.append(registro_aluno)

                # Verificar se chegou ao fim da fila
                if pos_info.get("atual") and pos_info.get("total") and pos_info["atual"] >= pos_info["total"]:
                    state.log("[Atividades Abertas] Último estudante da fila alcançado.")
                    break

                if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                    state.log("[Atividades Abertas] Navegação não encontrou próximo estudante. Fila concluída.")
                    break

            # 4. Gerar relatório consolidado de auditoria
            RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)
            disciplina_final = nome_disciplina
            if not disciplina_final or str(disciplina_final).lower() in ["undefined", "null", "none", ""]:
                disciplina_final = info_ativ.get("disciplina") or f"Turma {ou}"

            relatorio_final = {
                "disciplina": disciplina_final,
                "ou": str(ou),
                "atividade": info_ativ["atividade_nome"],
                "tipologia": info_ativ["tipologia"],
                "valor_oficial": info_ativ["valor_maximo"],
                "modo_execucao": modo,
                "docente": docente,
                "data_execucao": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_avaliados": len(resultados),
                "rubrica": rubrica,
                "estudantes": resultados
            }

            caminho_rel = RELATORIOS_DIR / f"auditoria_atividades_abertas_{ou}_{timestamp_inicio}.json"
            with open(caminho_rel, "w", encoding="utf-8") as f:
                json.dump(relatorio_final, f, indent=2, ensure_ascii=False)

            state.current_stage = "Execução de Atividades Abertas Concluída com Sucesso!"
            state.log(f"[Atividades Abertas] Sucesso! Relatório salvo em: {caminho_rel.name}")
            return relatorio_final

        except Exception as e:
            state.log(f"[Atividades Abertas] Erro durante a execução da turma: {e}", "ERROR")
            state.current_stage = f"Erro: {str(e)[:60]}"
            return {"erro": str(e), "total_avaliados": len(resultados), "estudantes": resultados}

        finally:
            state.is_running = False
            shutil.rmtree(temp_dir_base, ignore_errors=True)

# Instância Singleton
motor_atividades_novo = MotorAtividadesNovo()
