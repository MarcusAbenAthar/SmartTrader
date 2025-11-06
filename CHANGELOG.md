# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

## [v1.2.0] - 2025-11-05

### PluginBancoDados - Refatoração Completa

#### Adicionado
- ✅ **CRUD Completo Implementado**
  - Método `inserir()` - Inserção de dados com upsert para velas
  - Método `consultar()` - Consulta com filtros, campos e ordenação
  - Método `atualizar()` - Atualização com filtros e validação
  - Método `deletar()` - Exclusão com filtros obrigatórios (segurança)
  
- ✅ **Estrutura de Métodos**
  - Métodos internos com underscore (_inserir_velas, _consultar, etc.)
  - Métodos públicos sem underscore (inserir, consultar, atualizar, deletar)
  - Separação clara entre lógica interna e interface pública
  
- ✅ **Logs Padronizados**
  - Formato: `[BancoDados][INSERT]`, `[UPDATE]`, `[SELECT]`, `[DELETE]`
  - Facilita depuração e auditoria
  - Logs informativos por operação com detalhes
  
- ✅ **Retorno Padronizado**
  - Dicionário padronizado para todas as operações CRUD
  - Facilita integração com IA
  - Estrutura:
    ```python
    {
        "sucesso": bool,
        "operacao": str,  # INSERT, UPDATE, SELECT, DELETE
        "tabela": str,
        "dados": Any,
        "mensagem": str,
        "linhas_afetadas": int,
        "erro": Optional[str],
        "timestamp": str
    }
    ```
  
- ✅ **Melhorias de Segurança**
  - Uso de `sql.Identifier` para prevenir SQL injection
  - Validação de filtros obrigatórios em UPDATE e DELETE
  - Validação de dados antes de inserção
  
- ✅ **Métodos Auxiliares**
  - `_formatar_retorno()` - Formata retorno padronizado
  - `_inserir_generico()` - Inserção genérica para qualquer tabela
  - `atualizar_view_materializada()` - Atualiza view materializada
  
- ✅ **Documentação Completa**
  - Docstrings em todos os métodos
  - Exemplos de uso na documentação
  - Tipagem completa com type hints

#### Melhorado
- ✅ Estrutura de código mais organizada
- ✅ Tratamento de erros mais robusto
- ✅ Logs mais informativos e padronizados
- ✅ Retorno padronizado para facilitar integração com IA

#### Versão
- PluginBancoDados: v1.0.0 → v1.2.0
- Schema versão: v1.0.0 → v1.2.0

---

## [v1.1.0] - 2025-11-05

### Melhorias e Robustez

#### Adicionado
- ✅ Enums para Status e Tipos (StatusExecucao, TipoPlugin, NivelGravidade)
- ✅ Metadados de Plugin (autor, data, dependências)
- ✅ Monitoramento e Telemetria (tolerância de erro temporal, armazenamento)
- ✅ Ações Automáticas (ERROR → recuperação, CRITICAL → reinicialização)
- ✅ Suporte Assíncrono (executar_async())
- ✅ GerenciadorBot Melhorado (tratamento de empates)
- ✅ Banco de Dados Expandido (campo exchange, view materializada, histórico de schema)

---

## [v1.0.0] - 2025-01-XX

### Adicionado
- Estrutura base do projeto conforme regras de ouro
- Classe base `Plugin` com ciclo de vida completo
- `GerenciadorLog` com sistema de logs estruturado por tipo
- `GerenciadorBanco` para persistência de dados com validação
- `GerenciadorPlugins` para orquestração de plugins
- `GerenciadorBot` para controle de trades (Sistema 6/8)
- `ConfigManager` com suporte a testnet/mainnet Bybit
- `main.py` como ponto de entrada do sistema
- Sistema de diretórios de logs organizados por tipo

### Estrutura
- `plugins/base_plugin.py`: Classe base para todos os plugins
- `plugins/gerenciadores/`: Gerenciadores principais do sistema
- `plugins/indicadores/`: Preparado para 8 plugins de indicadores
- `utils/config.py`: Configuração centralizada
- `utils/logging_config.py`: Helpers de logging

