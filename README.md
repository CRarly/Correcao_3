# Brightspace Grader 2.0 (Motor Especialista)

Nova geração da plataforma de avaliação, auditoria e detecção de plágio para o AVA Brightspace (Católica / UBEC).

## Destaques da Versão 2.0:
1. **Pré-Inspeção Curricular e Planos de Apoio:**
   - Detecção automática de 2 Unidades (Fórum 2,5 pts) vs 4 Unidades (Fórum 1,0 pt + Atividade Aberta 1,5 pts).
   - Extração do comando temático oficial na thread do fórum e instruções detalhadas da atividade.
2. **Motor Cognitivo Multicritério:**
   - Avaliação por profundidade conceitual, coesão, conformidade às regras e gramática (notas justas e não apenas por volume).
3. **Detecção Cruzada de Plágio e Cópias:**
   - Compara textos e arquivos de todos os estudantes da turma, apontando autor original, estudante que copiou, porcentagem de similaridade e trechos idênticos.
4. **Avaliação Especialista da Prova Presencial:**
   - Identifica a Questão Discursiva (até 2,0 pts), lança nota e parecer formativo individualizado sem alterar as questões objetivas.
5. **Quatro Modos Operacionais:**
   - **Tradicional:** Novos envios pendentes.
   - **Auditoria:** Verificação de notas e citação nominal `{FirstName}` nos já corrigidos.
   - **Recorrigir:** Reavaliação completa de 1 a N na turma.
   - **Auditoria Geral:** Auditoria integral de 1 a N sem omissões.
6. **Expurgo Automático de Temporários:**
   - Pasta `temp_downloads_{ou}/` e arquivos de apoio são excluídos ao final de cada disciplina.
7. **Explorador Histórico de Relatórios no Dashboard:**
   - Interface interativa para consultar relatórios anteriores, buscar por aluno, disciplina e baixar CSVs.

## Como Executar:
- **Interface Web (Padrão):**
  Execute `iniciar.bat` ou digite no terminal:
  ```bash
  python main.py
  ```
- **Modo Terminal Interativo:**
  ```bash
  python main.py --cli
  ```

