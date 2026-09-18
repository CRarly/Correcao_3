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
    contar_anexos_submissao
)

class MotorAtividades:
    """
    Motor especialista de avaliação e auditoria para a Atividade Aberta.
    Faz o download temporário dos arquivos de envio, extrai texto com profundidade,
    analisa plágio cruzado e lança nota e feedback humanizado de 1 a N na turma.
    """

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

            # Pular estudantes apenas se comprovadamente não houver qualquer envio após o carregamento completo
            if total_arqs == 0 and not texto_submissoes.strip():
                if not tem_submissao:
                    state.log(f"{pos_str}{nome_aluno}: Sem envios na Atividade Aberta confirmados após carregamento. Pulando...")
                    if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                        state.log("Fim da lista de estudantes da Atividade alcançado.")
                        break
                    continue
                else:
                    # Havia indicador de envio mas download retornou vazio: dar mais 2s e tentar novamente
                    time.sleep(2.0)
                    total_arqs, texto_submissoes = self._baixar_e_extrair_arquivos(page, temp_dir, aluno_idx)
                    if total_arqs == 0 and not texto_submissoes.strip():
                        state.log(f"{pos_str}{nome_aluno}: Sem envios na Atividade Aberta confirmados após nova tentativa. Pulando...")
                        if not avancar_proximo_estudante_seguro(page, nome_anterior=nome_aluno, posicao_anterior=pos_info):
                            state.log("Fim da lista de estudantes da Atividade alcançado.")
                            break
                        continue

            state.log(f"{pos_str}{nome_aluno}: Submissão identificada e analisada ({total_arqs} anexo(s)). Temporários excluídos.")

            # Detecção de plágio cruzado (estritamente >= 90%, avaliando conteúdo textual e gerando comparação)
            info_plagio = detector_plagio.registrar_e_comparar(
                ou=ou,
                disciplina=disciplina,
                atividade="Atividade aberta",
                aluno_nome=nome_aluno,
                texto_submissao=texto_submissoes
            )
            if info_plagio.get("tem_plagio", False):
                state.log(f"ALERTA DE PLÁGIO (≥ 90%): {nome_aluno} possui {info_plagio['similaridade_pct']}% de similaridade com {info_plagio['aluno_autor']}!", "WARN")
                if info_plagio.get("relatorio_comparacao"):
                    state.log(f"Comparação de arquivos gerada: {info_plagio['relatorio_comparacao']}")
                state.increment_stat("plagios_detectados")

            # Avaliação pedagógica
            metadados = {
                "arquivos_count": total_arqs,
                "tem_anexos": total_arqs > 0 or bool(texto_submissoes.strip())
            }
            diagnostico = analisador_pedagogico.avaliar_submissao(
                tipo_atividade="atividade_aberta",
                texto_aluno=texto_submissoes,
                comando_oficial=instrucoes,
                nota_maxima=nota_maxima,
                metadados_envio=metadados,
                info_plagio=info_plagio
            )

            nota_calculada = diagnostico["nota_sugerida"]
            feedback_html = construtor_feedback.gerar_feedback(
                nome_estudante=nome_aluno,
                tipo_atividade="atividade_aberta",
                diagnostico_pedagogico=diagnostico,
                nome_docente=docente,
                info_plagio=info_plagio
            )

            # Execução segundo o Modo Efetivo
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

            registro = {
                "ou": str(ou),
                "disciplina": disciplina,
                "atividade": "Atividade aberta",
                "aluno": nome_aluno,
                "nota": nota_calculada,
                "nota_max": nota_maxima,
                "plagio": info_plagio.get("tem_plagio", False),
                "similaridade_pct": info_plagio.get("similaridade_pct", 0.0),
                "qualidade": diagnostico.get("qualidade_geral", "Bom"),
                "modo": modo
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
