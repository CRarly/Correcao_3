# Brightspace Grader v3.0 - Motor Especialista Integrado

Plataforma avançada e integrada de avaliação pedagógica, correção analítica, auditoria de coerência e conformidade acadêmica para o AVA Brightspace (Católica / UBEC).

---

## Destaques da Versão 3.0:

### 1. Módulos Especialistas de Provas Discursivas
- **Prova Presencial (Discursiva - Pergunta 8):**
  - Rubrica Analítica: Diagnóstico Cascata (0,70 pts), Solução Ágil/Scrum (0,80 pts), Articulação Textual e Norma Culta (0,50 pts) = 2,00 pts.
  - Lançamento de nota via `qAR._updateScore(...)` e feedback formativo abaixo da nota em `d2l-htmleditor.d2l-consistent-eval-quiz-question-feedback`.
- **Prova Substitutiva (Discursiva - Pergunta 8):**
  - Código Oficial: `EAD_EdS_2026_3_PROREC_QDIS`.
  - Rubrica Analítica: Diagnóstico das Decisões (0,70 pts), Proposição Ágil Integrada (0,80 pts), Articulação Conceitual e Coesão (0,50 pts) = 2,00 pts.
  - Feedback estrito sem saudação `{FirstName}`, duplo salvamento em rascunho e auditoria de coerência da turma.
- **Motor Universal de Discursivas:**
  - Fluxo em 4 passos (Ver Enunciado, Criar Critérios, Exemplo de Resposta, Avaliar).
  - Suporte flexível para alternar entre Prova Presencial e Prova Substitutiva diretamente na interface.

### 2. Motor Especialista de Atividades Abertas (5 Fluxos Pedagógicos)
- **Fluxo 1:** Entendimento do comando e tipologia dinâmica (Fichamento, Podcast, Mapa Mental, Relatório Técnico).
- **Fluxo 2:** Construção da matriz analítica (3 critérios com pesos exatos e gabarito comentado).
- **Fluxo 3:** Ingestão de múltiplos arquivos (.docx, .doc OLE legados com extração binária UTF-16LE, .pdf, .zip, código).
- **Fluxo 4:** Feedback formativo qualitativo sem subtrações numéricas no texto.
- **Fluxo 5:** Execução em turma com duplo rascunho e auditoria analítica.

### 3. Motor Especialista de Fóruns de Discussão
- Critérios calibrados conforme exigência do comando: 50% postagem principal + 50% réplicas aos colegas (se solicitado) ou 100% postagem principal.
- Feedback humanizado, persistência dupla e auditoria.

### 4. Dashboard Web 3.0 Completo (4 Abas)
- **Aba 1 (Operações):** Mapeamento dinâmico de turmas por período letivo (2026/1, 2026/2, 2026/3, Fixado, Todas as Disciplinas), pré-inspeção com plano de apoio e execução em lote de turmas e atividades (Fóruns, Atividades Abertas, Prova Presencial e Prova Substitutiva).
- **Aba 2 (Discursivas):** Workflow especialista com inspeção dinâmica, gabarito de calibração, seleção entre Prova Presencial e Substitutiva, e modal de auditoria de coerência.
- **Aba 3 (Atividades Abertas):** Workflow especialista de atividades práticas, detecção de tipologia, visualização de templates e auditoria.
- **Aba 4 (Relatórios):** Histórico completo de sessões, filtros, visualização detalhada de correções e download de CSVs.

### 5. Protocolos Estritos de Segurança e Persistência
- **NUNCA Publicar:** Todas as notas e pareceres são salvos com **"Salvar Rascunho"** (`salvar_rascunho_duplo`).
- Feedback da tentativa na sidebar direita mantido intocado/em branco nas provas discursivas.
- Navegação resiliente pelo mostrador do Consistent Evaluation (`1 de N`), com avanço seguro e transição confirmada.
- Gravação de checkpoints incrementais em JSON e auditoria pós-execução.

---

## Como Executar:

### Interface Web Dashboard (Padrão):
Execute o script batch:
```cmd
iniciar.bat
```
Ou diretamente pelo Python:
```bash
python main.py
```
O servidor inicializará e abrirá automaticamente o navegador em `http://127.0.0.1:8080`.

### Modo Terminal Interativo (CLI):
```bash
python main.py --cli
```

### Dados locais e segurança:
- Credenciais, cookies/sessões do Brightspace, estado de execução, relatórios e capturas de tela são dados locais e não devem ser versionados.
- Configure os dados de autenticação localmente; nunca grave senhas ou tokens em arquivos de código.
- Os arquivos de execução pontual que contêm credenciais ou referências específicas a estudantes não fazem parte desta distribuição.
