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
    Insere o feedback formativo no editor HTML do Consistent Evaluation (d2l-htmleditor / TinyMCE),
    atravessando todo o Shadow DOM recursivamente e garantindo persistência no modelo de dados.
    """
    res = page.evaluate(r"""(html) => {
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

        let inserido = false;

        // 1. Localizar d2l-htmleditor em qualquer nível de Shadow DOM
        const htmleditor = findElementDeep(document.body, el => el.tagName.toLowerCase() === 'd2l-htmleditor');
        if (htmleditor) {
            try {
                htmleditor.html = html;
                htmleditor.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
                htmleditor.dispatchEvent(new CustomEvent('input', { bubbles: true, composed: true }));
                inserido = true;
            } catch(e) {}
        }

        // 2. Atualizar instâncias do TinyMCE no window global se houver
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

        // 3. Procurar textarea de feedback
        const textarea = findElementDeep(document.body, el => {
            const tag = el.tagName.toLowerCase();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            const id = (el.id || '').toLowerCase();
            return tag === 'textarea' && (aria.includes('feedback') || id.includes('feedback'));
        });
        if (textarea) {
            textarea.value = html.replace(/<[^>]+>/g, '\n').replace(/\n\s*\n/g, '\n').trim();
            textarea.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
            textarea.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
            inserido = true;
        }

        return { success: inserido };
    }""", feedback_html)

    # Verificar também em frames filhos
    for frame in page.frames:
        if "ifr" in frame.name or frame.url == "about:srcdoc":
            try:
                body = frame.locator("body")
                if body.count() > 0:
                    body.evaluate(f"(el) => {{ el.innerHTML = {repr(feedback_html)}; }}")
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


def obter_nota_e_feedback_consistent_evaluation(page: Page) -> Dict[str, Any]:
    """
    Extrai a nota e o feedback atualmente presentes no Consistent Evaluation para auditoria e verificação.
    """
    return page.evaluate(r"""() => {
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

        let nota = null;
        const inputNum = findElementDeep(document.body, el => el.tagName.toLowerCase() === 'd2l-input-number');
        if (inputNum) {
            nota = inputNum.value;
            if (nota === null || nota === undefined) {
                const innerInput = inputNum.shadowRoot ? inputNum.shadowRoot.querySelector('input') : null;
                if (innerInput) nota = innerInput.value;
            }
        }

        let feedback = '';
        const htmleditor = findElementDeep(document.body, el => el.tagName.toLowerCase() === 'd2l-htmleditor');
        if (htmleditor) {
            feedback = (htmleditor.html || htmleditor.innerText || '').trim();
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

