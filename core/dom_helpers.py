import time
from typing import Dict, Any, Optional, List
from playwright.sync_api import Page
from engine_state import state

def inserir_nota_consistent_evaluation(page: Page, nota: float) -> bool:
    """
    Localiza e insere a nota no componente d2l-input-number do Consistent Evaluation,
    atravessando confiavelmente múltiplos níveis de Shadow DOM e disparando
    os eventos de input e change nos componentes interno e externo.
    """
    nota_float = float(nota)
    nota_br = f"{nota_float:.2f}".replace(".", ",").rstrip("0").rstrip(",")
    if not nota_br:
        nota_br = "0"

    res = page.evaluate(r"""(args) => {
        const { notaFloat, notaBr } = args;

        function findElementDeep(root, matchFn) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                if (matchFn(el)) return el;
                if (el.shadowRoot) {
                    const found = findElementDeep(el.shadowRoot, matchFn);
                    if (found) return found;
                }
            }
            return null;
        }

        // 1. Procurar d2l-input-number na página principal e shadow DOMs
        const inputNum = findElementDeep(document.body, el => {
            const tag = el.tagName.toLowerCase();
            return tag === 'd2l-input-number' || tag.includes('input-number');
        });

        if (inputNum) {
            // Atualizar propriedade do componente LitElement
            inputNum.value = notaFloat;
            inputNum.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
            inputNum.dispatchEvent(new CustomEvent('input', { bubbles: true, composed: true }));

            // Atualizar o input HTML nativo dentro do shadow root do d2l-input-number
            const innerInput = inputNum.shadowRoot ? inputNum.shadowRoot.querySelector('input') : null;
            if (innerInput) {
                innerInput.value = notaBr;
                innerInput.dispatchEvent(new Event('input', { bubbles: true }));
                innerInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
            return { success: true, method: 'd2l-input-number', value: inputNum.value };
        }

        // 2. Fallback: procurar input nativo por aria-label ou id
        const nativeInput = findElementDeep(document.body, el => {
            if (el.tagName.toLowerCase() !== 'input') return false;
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            const id = (el.id || '').toLowerCase();
            return aria.includes('nota') || aria.includes('grade') || aria.includes('score') || id.includes('grade') || id.includes('score');
        });

        if (nativeInput) {
            nativeInput.value = notaBr;
            nativeInput.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
            nativeInput.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            return { success: true, method: 'nativeInput', value: nativeInput.value };
        }

        return { success: false, reason: 'Nenhum campo de nota localizado' };
    }""", {"notaFloat": nota_float, "notaBr": nota_br})

    if res.get("success"):
        return True
    
    # Fallback Playwright Locator
    try:
        loc = page.locator("d2l-input-number input, input[aria-label*='Nota Geral'], input[aria-label*='Nota']").first
        if loc.count() > 0:
            loc.click()
            loc.fill(nota_br)
            loc.press("Tab")
            return True
    except Exception:
        pass

    return False


def inserir_feedback_consistent_evaluation(page: Page, feedback_html: str) -> bool:
    """
    Insere o feedback formativo no editor HTML do Consistent Evaluation (d2l-htmleditor / TinyMCE / Feedback Geral),
    atravessando todo o Shadow DOM recursivamente e garantindo persistência no modelo de dados do Brightspace.
    """
    res = page.evaluate(r"""(html) => {
        function getAllDeep(root) {
            let elements = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                elements.push(el);
                if (el.shadowRoot) {
                    elements = elements.concat(getAllDeep(el.shadowRoot));
                }
            }
            return elements;
        }

        let inserido = false;
        const allElements = getAllDeep(document.body);

        // 1. Localizar painel de feedback do Consistent Evaluation (d2l-consistent-evaluation-right-panel-feedback)
        const feedbackPanels = allElements.filter(el => {
            const tag = el.tagName.toLowerCase();
            return tag.includes('feedback') && tag.includes('panel');
        });

        for (let panel of feedbackPanels) {
            try {
                if ('feedbackText' in panel) panel.feedbackText = html;
                if ('_feedbackText' in panel) panel._feedbackText = html;
                inserido = true;
            } catch(e) {}
        }

        // 2. Localizar d2l-htmleditor em qualquer nível de Shadow DOM
        const editors = allElements.filter(el => el.tagName.toLowerCase() === 'd2l-htmleditor');
        for (let ed of editors) {
            try {
                ed.html = html;
                ed.initialValue = html;
                if ('value' in ed) ed.value = html;
                if ('_html' in ed) ed._html = html;
                ed.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true, detail: { html: html } }));
                ed.dispatchEvent(new CustomEvent('input', { bubbles: true, composed: true, detail: { html: html } }));
                ed.dispatchEvent(new CustomEvent('d2l-htmleditor-change', { bubbles: true, composed: true, detail: { html: html } }));
                ed.dispatchEvent(new CustomEvent('d2l-htmleditor-input', { bubbles: true, composed: true, detail: { html: html } }));
                inserido = true;
            } catch(e) {}
        }

        // 3. Localizar iframes do TinyMCE (Feedback Geral)
        const iframes = allElements.filter(el => el.tagName.toLowerCase() === 'iframe');
        for (let ifr of iframes) {
            try {
                const title = (ifr.title || '').toLowerCase();
                const id = (ifr.id || '').toLowerCase();
                const doc = ifr.contentDocument || ifr.contentWindow.document;
                if (doc && doc.body) {
                    const isFeedbackIframe = title.includes('feedback') || id.includes('_ifr') || doc.body.contentEditable === 'true' || (doc.body.className || '').includes('mce');
                    if (isFeedbackIframe) {
                        doc.body.innerHTML = html;
                        doc.body.dispatchEvent(new Event('input', { bubbles: true }));
                        doc.body.dispatchEvent(new Event('change', { bubbles: true }));

                        if (ifr.contentWindow && ifr.contentWindow.tinymce) {
                            try {
                                if (ifr.contentWindow.tinymce.activeEditor) {
                                    ifr.contentWindow.tinymce.activeEditor.setContent(html);
                                    ifr.contentWindow.tinymce.activeEditor.fire('change');
                                    ifr.contentWindow.tinymce.activeEditor.save();
                                }
                            } catch(e) {}
                        }
                        inserido = true;
                    }
                }
            } catch(e) {}
        }

        // 4. Atualizar instâncias globais do TinyMCE se houver
        if (window.tinymce && window.tinymce.editors && window.tinymce.editors.length > 0) {
            for (let ed of window.tinymce.editors) {
                try {
                    ed.setContent(html);
                    ed.fire('change');
                    ed.save();
                    inserido = true;
                } catch(e) {}
            }
        }

        // 5. Fallback para textareas
        const textareas = allElements.filter(el => {
            const tag = el.tagName.toLowerCase();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            const id = (el.id || '').toLowerCase();
            return tag === 'textarea' && (aria.includes('feedback') || id.includes('feedback'));
        });
        for (let ta of textareas) {
            try {
                ta.value = html.replace(/<[^>]+>/g, '\n').replace(/\n\s*\n/g, '\n').trim();
                ta.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                inserido = true;
            } catch(e) {}
        }

        // 6. Notificar o painel de feedback para sincronizar com o Consistent Evaluation
        for (let panel of feedbackPanels) {
            try {
                if (typeof panel._saveFeedback === 'function') {
                    panel._saveFeedback();
                } else if (typeof panel._saveOnFeedbackChange === 'function') {
                    panel._saveOnFeedbackChange();
                } else if (typeof panel._forceFeedbackSave === 'function') {
                    panel._forceFeedbackSave();
                }
                if (typeof panel._emitFeedbackEditEvent === 'function') {
                    panel._emitFeedbackEditEvent();
                }
            } catch(e) {}
        }

        return { success: inserido };
    }""", feedback_html)

    time.sleep(1.0)

    # Fallback adicional com frames do Playwright
    for frame in page.frames:
        try:
            body = frame.locator("body[contenteditable='true'], body.mce-content-body").first
            if body.count() > 0:
                body.evaluate(f"(el) => {{ el.innerHTML = {repr(feedback_html)}; el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}")
                return True
        except Exception:
            pass

    return res.get("success", False)


def salvar_rascunho_consistent_evaluation(page: Page) -> bool:
    """
    Aciona com segurança o salvamento de rascunho no Consistent Evaluation.
    Localiza o botão d2l-button#consistent-evaluation-footer-save-draft atravessando Shadow DOMs
    e aciona o clique no elemento interno <button> para disparar a mutação e persistência no D2L.
    """
    res = page.evaluate(r"""() => {
        function findElementDeep(root, matchFn) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                if (matchFn(el)) return el;
                if (el.shadowRoot) {
                    const found = findElementDeep(el.shadowRoot, matchFn);
                    if (found) return found;
                }
            }
            return null;
        }

        // 1. Localizar d2l-button específico de salvar rascunho
        const saveDraftBtn = findElementDeep(document.body, el => {
            const tag = el.tagName.toLowerCase();
            const id = el.id || '';
            const txt = (el.innerText || el.textContent || '').toLowerCase();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            const textAttr = (el.getAttribute('text') || '').toLowerCase();

            if (id === 'consistent-evaluation-footer-save-draft') return true;
            if (tag.startsWith('d2l-button') || tag === 'button') {
                return (txt.includes('salvar rascunho') || txt.includes('save draft') ||
                        aria.includes('salvar rascunho') || textAttr.includes('salvar rascunho')) &&
                       !txt.includes('publicar');
            }
            return false;
        });

        if (saveDraftBtn) {
            const innerBtn = saveDraftBtn.shadowRoot ? saveDraftBtn.shadowRoot.querySelector('button') : null;
            if (innerBtn && !innerBtn.disabled) {
                innerBtn.click();
                return { success: true, target: 'innerBtn' };
            } else if (!saveDraftBtn.disabled) {
                saveDraftBtn.click();
                return { success: true, target: 'hostElement' };
            }
        }

        return { success: false, reason: 'Botão de salvar rascunho não encontrado ou desabilitado' };
    }""")

    time.sleep(1.8)
    return res.get("success", False)


def salvar_rascunho_duplo(page: Page) -> bool:
    """
    Salva em rascunho duas vezes consecutivas para garantir persistência plena no Brightspace.
    Não publica em nenhuma hipótese.
    """
    ok1 = salvar_rascunho_consistent_evaluation(page)
    time.sleep(1.5)
    ok2 = salvar_rascunho_consistent_evaluation(page)
    return ok1 or ok2


def remover_nota_e_feedback_consistent_evaluation(page: Page) -> bool:
    """
    Limpa e remove qualquer nota e feedback inseridos no Consistent Evaluation,
    restaurando os campos para o estado em branco antes de salvar como rascunho.
    """
    res = page.evaluate(r"""() => {
        function getAllDeep(root) {
            let elements = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                elements.push(el);
                if (el.shadowRoot) {
                    elements = elements.concat(getAllDeep(el.shadowRoot));
                }
            }
            return elements;
        }

        const all = getAllDeep(document.body);
        let alterado = false;

        // 1. Limpar campo de nota (d2l-input-number e inputs nativos)
        const inputNums = all.filter(el => {
            const tag = el.tagName.toLowerCase();
            return tag === 'd2l-input-number' || tag.includes('input-number');
        });

        for (let inp of inputNums) {
            inp.value = '';
            inp.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
            inp.dispatchEvent(new CustomEvent('input', { bubbles: true, composed: true }));
            if (inp.shadowRoot) {
                const inner = inp.shadowRoot.querySelector('input');
                if (inner) {
                    inner.value = '';
                    inner.dispatchEvent(new Event('input', { bubbles: true }));
                    inner.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
            alterado = true;
        }

        const nativeInputs = all.filter(el => {
            if (el.tagName.toLowerCase() !== 'input') return false;
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            const id = (el.id || '').toLowerCase();
            return aria.includes('nota') || aria.includes('grade') || aria.includes('score') || id.includes('grade') || id.includes('score');
        });

        for (let nat of nativeInputs) {
            nat.value = '';
            nat.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
            nat.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            alterado = true;
        }

        // 2. Limpar feedback panels e editors
        const feedbackPanels = all.filter(el => {
            const tag = el.tagName.toLowerCase();
            return tag.includes('feedback') && tag.includes('panel');
        });

        for (let panel of feedbackPanels) {
            if ('feedbackText' in panel) panel.feedbackText = '';
            if ('_feedbackText' in panel) panel._feedbackText = '';
            panel.dispatchEvent(new CustomEvent('d2l-consistent-evaluation-feedback-text-change', {
                bubbles: true,
                composed: true,
                detail: { feedbackText: '' }
            }));
            alterado = true;
        }

        // Limpar d2l-htmleditor
        const editors = all.filter(el => el.tagName.toLowerCase() === 'd2l-htmleditor');
        for (let ed of editors) {
            if ('html' in ed) ed.html = '';
            if ('value' in ed) ed.value = '';
            ed.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
            alterado = true;
        }

        // Limpar iframes TinyMCE
        const iframes = all.filter(el => el.tagName.toLowerCase() === 'iframe');
        for (let ifr of iframes) {
            try {
                const doc = ifr.contentDocument || ifr.contentWindow.document;
                if (doc && doc.body && doc.body.contentEditable === 'true') {
                    doc.body.innerHTML = '';
                    doc.dispatchEvent(new Event('input', { bubbles: true }));
                    doc.dispatchEvent(new Event('change', { bubbles: true }));
                    alterado = true;
                }
            } catch(e) {}
        }

        return alterado;
    }""")
    return bool(res)


def obter_nota_e_feedback_consistent_evaluation(page: Page) -> Dict[str, Any]:
    """
    Extrai a nota e o feedback atualmente presentes no Consistent Evaluation para auditoria e verificação.
    """
    return page.evaluate(r"""() => {
        function getAllDeep(root) {
            let elements = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            while (walker.nextNode()) {
                const el = walker.currentNode;
                elements.push(el);
                if (el.shadowRoot) {
                    elements = elements.concat(getAllDeep(el.shadowRoot));
                }
            }
            return elements;
        }

        const allElements = getAllDeep(document.body);

        let nota = null;
        const inputNum = allElements.find(el => el.tagName.toLowerCase() === 'd2l-input-number');
        if (inputNum) {
            nota = inputNum.value;
            if (nota === null || nota === undefined) {
                const innerInput = inputNum.shadowRoot ? inputNum.shadowRoot.querySelector('input') : null;
                if (innerInput) nota = innerInput.value;
            }
        }

        let feedback = '';
        const feedbackPanel = allElements.find(el => el.tagName.toLowerCase().includes('feedback') && el.tagName.toLowerCase().includes('panel'));
        if (feedbackPanel && (feedbackPanel.feedbackText || feedbackPanel._feedbackText)) {
            feedback = (feedbackPanel.feedbackText || feedbackPanel._feedbackText || '').trim();
        }

        if (!feedback) {
            const htmleditor = allElements.find(el => el.tagName.toLowerCase() === 'd2l-htmleditor');
            if (htmleditor) {
                feedback = (htmleditor.html || htmleditor.value || htmleditor.innerText || '').trim();
            }
        }

        if (!feedback) {
            const iframes = allElements.filter(el => el.tagName.toLowerCase() === 'iframe');
            for (let ifr of iframes) {
                try {
                    const title = (ifr.title || '').toLowerCase();
                    const id = (ifr.id || '').toLowerCase();
                    const doc = ifr.contentDocument || ifr.contentWindow.document;
                    if (doc && doc.body) {
                        const isFeedbackIframe = title.includes('feedback') || id.includes('_ifr') || doc.body.contentEditable === 'true';
                        if (isFeedbackIframe) {
                            const t = (doc.body.innerHTML || '').trim();
                            if (t && !t.includes('data-mce-bogus')) {
                                feedback = t;
                                break;
                            }
                        }
                    }
                } catch(e) {}
            }
        }

        return { nota, feedback };
    }""")


def contar_anexos_submissao(page: Page) -> List[str]:
    """
    Identifica com precisão na interface e Shadow DOM os anexos reais submetidos pelo estudante,
    retornando os nomes dos arquivos anexados e garantindo contagem exata (sem duplicar com zip temporário).
    """
    try:
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
            const anexos = [];

            // 1. Procurar elementos com aria-label indicando anexo específico
            for (let el of all) {
                const aria = (el.getAttribute('aria-label') || '').trim();
                const ariaLow = aria.toLowerCase();
                const txt = (el.innerText || el.textContent || '').trim();

                if (ariaLow.includes('para baixar o anexo') || ariaLow.includes('clique para baixar') || 
                    (ariaLow.includes('baixar o anexo') && !ariaLow.includes('todos'))) {
                    let nome = txt;
                    if (!nome || nome.length < 3) {
                        const m = aria.match(/anexo\s+(.+)$/i);
                        nome = m ? m[1].trim() : aria;
                    }
                    if (nome && !anexos.includes(nome)) {
                        anexos.push(nome);
                    }
                }
            }

            // 2. Procurar links com href de anexo individual
            if (anexos.length === 0) {
                for (let el of all) {
                    const href = (el.getAttribute('href') || '').toLowerCase();
                    const txt = (el.innerText || el.textContent || '').trim();
                    if ((href.includes('downloadattachment') || href.includes('download_submission_file')) && 
                        !href.includes('downloadall') && txt.length > 2) {
                        if (!anexos.includes(txt)) anexos.push(txt);
                    }
                }
            }

            return anexos;
        }""")
    except Exception:
        return []

