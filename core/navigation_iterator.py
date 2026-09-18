import time
import re
from typing import Dict, Any, Optional
from playwright.sync_api import Page

def extrair_posicao_mostrador_iterator(page: Page) -> Dict[str, Any]:
    """
    Extrai a posição atual e total do mostrador no Consistent Evaluation.
    Ex: 'Usuário 1 de 36', '1 de 36', 'User 1 of 36'.
    Prioriza o container oficial d2l-navigation-iterator, ignorando contadores de página de documentos.
    """
    try:
        return page.evaluate(r"""() => {
            function getAllElements(root) {
                let elements = [];
                const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                while (walker.nextNode()) {
                    const el = walker.currentNode;
                    elements.push(el);
                    if (el.shadowRoot) {
                        elements = elements.concat(getAllElements(el.shadowRoot));
                    }
                }
                return elements;
            }
            const all = getAllElements(document.body);

            // 1. Prioridade máxima: Dentro do componente d2l-navigation-iterator
            const navIterators = all.filter(el => el.tagName.toLowerCase().includes('navigation-iterator') || (el.className && el.className.toString().includes('navigation-iterator')));
            for (let nav of navIterators) {
                const navElements = getAllElements(nav);
                for (let el of navElements) {
                    const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
                    const aria = (el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
                    for (let t of [txt, aria]) {
                        if (!t) continue;
                        let m = t.match(/(\d+)\s*(?:de|of|\/)\s*(\d+)/i);
                        if (m) {
                            return { atual: parseInt(m[1], 10), total: parseInt(m[2], 10), texto: t };
                        }
                    }
                }
            }

            // 2. Busca por texto explícito de Usuário X de Y
            for (let el of all) {
                const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
                const aria = (el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
                for (let t of [txt, aria]) {
                    if (!t) continue;
                    let m = t.match(/(?:usu[áa]rio|user)\s*(\d+)\s*(?:de|of|\/)\s*(\d+)/i);
                    if (m) {
                        return { atual: parseInt(m[1], 10), total: parseInt(m[2], 10), texto: t };
                    }
                }
            }

            // 3. Fallback genérico em containers com classe ou tag iterator
            for (let el of all) {
                const tag = el.tagName.toLowerCase();
                const cls = (el.className ? el.className.toString() : '').toLowerCase();
                if ((tag.includes('iterator') || cls.includes('iterator')) && !tag.includes('document')) {
                    const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
                    let m2 = txt.match(/(\d+)\s*(?:de|of|\/)\s*(\d+)/i);
                    if (m2) {
                        return { atual: parseInt(m2[1], 10), total: parseInt(m2[2], 10), texto: txt };
                    }
                }
            }
            return { atual: null, total: null, texto: "" };
        }""")
    except Exception:
        return {"atual": None, "total": None, "texto": ""}

def extrair_nome_estudante_atual(page: Page) -> str:
    """
    Extrai confiavelmente o nome do estudante atualmente exibido no Consistent Evaluation.
    Prioriza o componente de perfil (.d2l-profile-card-name) e regex estrita em cabeçalhos,
    eliminando títulos de atividade como 'Avaliação: Atividade aberta'.
    """
    try:
        nome = page.evaluate(r"""() => {
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

            // 1. Procurar na classe do perfil do aluno (.d2l-profile-card-name)
            for (let el of all) {
                if (el.classList && el.classList.contains('d2l-profile-card-name')) {
                    const t = (el.innerText || el.textContent || '').trim();
                    if (t && t.length > 2 && !t.toLowerCase().includes('avaliação') && !t.toLowerCase().includes('atividade')) {
                        return t;
                    }
                }
            }

            // 2. Procurar em cabeçalhos imersivos com regex: 'Avaliação de [NOME] em [ATIVIDADE]'
            for (let el of all) {
                const txt = (el.innerText || el.textContent || '').trim();
                const aria = (el.getAttribute('aria-label') || '').trim();
                for (let t of [txt, aria]) {
                    if (!t) continue;
                    let m = t.match(/avalia[çc][ãa]o\s+de\s+(.*?)\s+(?:em|para|\-)\s+/i);
                    if (m && m[1].trim()) {
                        const cand = m[1].trim();
                        if (!cand.toLowerCase().includes('avaliação') && !cand.toLowerCase().includes('atividade') && !cand.toLowerCase().includes('discussão')) {
                            return cand;
                        }
                    }
                }
            }

            // 3. Fallback seletores comuns
            const profile = document.querySelector('.d2l-profile-card-name, [class*="user-name"]');
            if (profile) {
                const t = (profile.innerText || '').trim();
                if (t && !t.toLowerCase().includes('avaliação') && !t.toLowerCase().includes('atividade')) {
                    return t;
                }
            }
            return '';
        }""")

        if not nome or not nome.strip():
            return "Estudante"

        # Limpeza final de qualquer prefixo residual
        limpo = re.sub(r'^(avalia[çc][ãa]o\s+de|discuss[ãa]o\s+de|envios?\s+de|painel\s+de)\s*:?\s*', '', nome, flags=re.IGNORECASE).strip()
        limpo = limpo.split('\n')[0].strip()
        if limpo.lower().startswith('avaliação') or limpo.lower().startswith('atividade'):
            return "Estudante"
        return limpo if limpo else "Estudante"
    except Exception:
        return "Estudante"

def disparar_clique_proximo(page: Page) -> Dict[str, Any]:
    """
    Aciona um clique direto no botão Próximo (>) do Consistent Evaluation navegando em múltiplos níveis de Shadow DOM.
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

            // 1. Procurar componente específico d2l-navigation-iterator-next
            const nextComponents = all.filter(el => {
                const tag = el.tagName.toLowerCase();
                return tag.includes('iterator-next') || el.id === 'consistent-evaluation-footer-next-student';
            });

            for (let comp of nextComponents) {
                const isDisabled = comp.hasAttribute('disabled') || comp.getAttribute('aria-disabled') === 'true' || comp.classList.contains('disabled');
                if (isDisabled) {
                    return { clicked: false, disabled: true, source: 'iterator_next_component_disabled' };
                }
                // Encontrar o botão clicável real dentro do Shadow DOM do componente
                const innerElements = getAllElements(comp);
                const btn = innerElements.find(e => e.tagName.toLowerCase() === 'button' || e.getAttribute('role') === 'button');
                if (btn) {
                    if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') {
                        return { clicked: false, disabled: true, source: 'iterator_next_button_disabled' };
                    }
                    btn.click();
                    return { clicked: true, disabled: false, source: 'iterator_next_inner_button' };
                }
                if (typeof comp.click === 'function') {
                    comp.click();
                    return { clicked: true, disabled: false, source: 'iterator_next_component_click' };
                }
            }

            // 2. Procurar dentro de containers de iterator
            const iteratorContainers = all.filter(el => {
                const tag = el.tagName.toLowerCase();
                const cls = (el.className ? el.className.toString() : '').toLowerCase();
                return tag.includes('navigation-iterator') || cls.includes('navigation-iterator');
            });

            for (let container of iteratorContainers) {
                const cElements = getAllElements(container);
                for (let el of cElements) {
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    const icon = (el.getAttribute('icon') || '').toLowerCase();
                    const tag = el.tagName.toLowerCase();
                    const isBtn = tag === 'button' || tag.includes('button') || el.getAttribute('role') === 'button';
                    
                    if ((isBtn || icon.includes('chevron')) && (aria.includes('próximo') || aria.includes('proximo') || aria.includes('next') || aria.includes('avançar') || icon.includes('chevron-right') || icon.includes('right'))) {
                        const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true' || el.classList.contains('disabled');
                        if (!disabled) {
                            if (el.shadowRoot) {
                                const inner = el.shadowRoot.querySelector('button, [role="button"]');
                                if (inner && !inner.disabled) {
                                    inner.click();
                                    return { clicked: true, disabled: false, source: 'iterator_container_inner' };
                                }
                            }
                            if (typeof el.click === 'function') {
                                el.click();
                                return { clicked: true, disabled: false, source: 'iterator_container_target' };
                            }
                        } else {
                            return { clicked: false, disabled: true, source: 'iterator_container_target_disabled' };
                        }
                    }
                }
            }

            // 3. Busca global por botão com chevron-right ou Próximo
            for (let el of all) {
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                const icon = (el.getAttribute('icon') || '').toLowerCase();
                if (aria.includes('próximo') || aria.includes('proximo') || aria.includes('next') || aria.includes('avançar') || icon.includes('chevron-right')) {
                    const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true' || el.classList.contains('disabled');
                    if (!disabled) {
                        if (el.shadowRoot) {
                            const inner = el.shadowRoot.querySelector('button, [role="button"]');
                            if (inner && !inner.disabled) {
                                inner.click();
                                return { clicked: true, disabled: false, source: 'global_inner' };
                            }
                        }
                        if (typeof el.click === 'function') {
                            el.click();
                            return { clicked: true, disabled: false, source: 'global_next' };
                        }
                    }
                }
            }

            return { clicked: false, disabled: false, source: 'not_found' };
        }""")
    except Exception:
        return {"clicked": False, "disabled": False, "source": "error"}

def verificar_botao_proximo_desabilitado(page: Page) -> bool:
    """Verifica com certeza se o botão de avançar para o próximo estudante está desabilitado (fim de lista)."""
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
            const nextEls = all.filter(el => {
                const tag = el.tagName.toLowerCase();
                const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                const icon = (el.getAttribute('icon') || '').toLowerCase();
                return tag.includes('iterator-next') || 
                       aria.includes('próximo') || 
                       aria.includes('proximo') || 
                       aria.includes('next') || 
                       icon.includes('chevron-right');
            });
            for (let el of nextEls) {
                if (el.hasAttribute('disabled') || el.disabled === true || el.getAttribute('aria-disabled') === 'true' || el.classList.contains('disabled')) {
                    return true;
                }
                const btn = el.querySelector ? el.querySelector('button') : null;
                if (btn && (btn.disabled || btn.getAttribute('aria-disabled') === 'true')) {
                    return true;
                }
            }
            return false;
        }""")
    except Exception:
        return False

def avancar_proximo_estudante_seguro(page: Page, nome_anterior: str = "", posicao_anterior: Optional[Dict[str, Any]] = None, timeout_sec: int = 15) -> bool:
    """
    Avança confiavelmente para o próximo estudante no Consistent Evaluation.
    Garante que só finaliza quando o final real da turma for atingido,
    com retries automáticos para evitar perda de clique por transições ou salvamento de rascunhos.
    """
    from engine_state import state
    if state.should_stop:
        return False

    pos_antes = posicao_anterior if (posicao_anterior and posicao_anterior.get("atual") is not None) else extrair_posicao_mostrador_iterator(page)
    if not nome_anterior or nome_anterior == "Estudante":
        nome_anterior = extrair_nome_estudante_atual(page)

    # 1. Se estamos comprovadamente no último aluno (ex: 35 de 35) e o botão está desabilitado, encerra com certeza
    if pos_antes.get("atual") and pos_antes.get("total") and pos_antes["total"] > 1 and pos_antes["atual"] >= pos_antes["total"]:
        if verificar_botao_proximo_desabilitado(page):
            return False

    # 2. Esperar acomodação rápida de save draft anterior se necessário
    time.sleep(1.0)

    # 3. Disparar clique com retries ativos (até 3 tentativas caso não mude de aluno)
    t0 = time.time()
    tentativa = 0
    ultimo_clique = 0

    while (time.time() - t0) < timeout_sec:
        if state.should_stop:
            return False

        agora = time.time()
        if agora - ultimo_clique >= 2.5:
            tentativa += 1
            res_clique = disparar_clique_proximo(page)
            ultimo_clique = agora

            if res_clique.get("disabled") and pos_antes.get("total") and pos_antes.get("total") > 1 and pos_antes.get("atual") and pos_antes["atual"] >= pos_antes["total"]:
                return False

            # Fallback seletores Playwright
            if not res_clique.get("clicked"):
                for sel in [
                    "d2l-navigation-iterator-next button",
                    "d2l-navigation-iterator [icon*='chevron-right']",
                    "d2l-labs-navigation-button-icon[icon*='chevron-right']",
                    "#consistent-evaluation-footer-next-student",
                    "button[aria-label*='Próximo']",
                    "button[aria-label*='proximo']"
                ]:
                    b = page.locator(sel).first
                    if b.count() > 0:
                        try:
                            if not b.is_disabled():
                                b.click(timeout=1500)
                                break
                        except Exception:
                            pass

        time.sleep(0.4)
        pos_novo = extrair_posicao_mostrador_iterator(page)
        nome_novo = extrair_nome_estudante_atual(page)

        # Confirmado por avanço numérico no mostrador
        if pos_novo.get("atual") and pos_antes.get("atual"):
            if pos_novo["atual"] > pos_antes["atual"]:
                time.sleep(2.0)
                return True

        # Confirmado por mudança de nome do aluno
        if nome_novo and nome_anterior and nome_novo != nome_anterior and nome_novo != "Estudante":
            time.sleep(2.0)
            return True

    # Se esgotou o timeout e o botão está desabilitado, atingiu o fim
    if verificar_botao_proximo_desabilitado(page):
        return False

    return False

