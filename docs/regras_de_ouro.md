Documento: Regras de Ouro
Versão: 2
Github: https://github.com/MarcusAbenAthar/Smart_Trader
Última atualização: 05/11/2025



***** Regras Gerais e Absolutas *****

    # Regras de OURO para programar o bot:

        1 - Autônomo nas decisões (TP, SL e alavancagem);
        2 - Criterioso;
        3 - Seguro;
        4 - Certeiro;
        5 - Eficiente;
        6 - Clareza;
        7 - Modular;
        8 - Composto por plugins;
        9 - Testável;
        10 - Documentado com Docstrings e comentários;
        11 - Evitar hardcoded;

    # Boas práticas ao programar o bot:

        1 - Todos os plugins produzem dados e análises. Os dados e análises são armazenados em Dicionários "dados_completos crus e analisados" e isso deve ser repassado para a posteridade. 
        2 - Evitar redundâncias;
        3 - Respeitar a responsabilidade de cada plugin;
        4 - Evitar importação circular;
        5 - Manter histórico de alterações no banco;
        6 - Sempre testar migrações em ambiente controlado;
        7 - Quanto mais inteligente e menos hardcoded, melhor será;
        8 - O arquivo `plugins_dependencias.json` é gerado pelo sistema, não deve ser alterado manualmente
        9 - Nenhum processo ou thread deve ser iniciado dentro de __init__.
        10 - Evite operações bloqueantes (use async quando possível).
        11 - Registre logs de início e fim da execução.
        12 - Trate exceções localmente, nunca deixe subir exceções não capturadas.
        13 - Utilizar blocos try/finally e métodos de contexto (__enter__, __exit__) para garantir limpeza mesmo em caso de falha.
        14. Centralizar tratamentos comuns (como reconexão, retentativas ou validação) em utilitários dentro de `utils/`.
        15. Evitar mensagens vagas como “Ocorreu um erro” — sempre incluir contexto técnico.
        16. Testar exceções nos testes unitários usando `pytest.raises`.
        17. Garantir que toda exceção crítica seja reportada ao GerenciadorLog antes da finalização.
        18. Usar enums para status de execução (StatusExecucao) em vez de strings soltas.
        19. Incluir metadados de plugin (autor, data, dependências) para classificação pela IA.
        20. Definir tipo de plugin (TipoPlugin) para hierarquia e organização automática.
        21. Implementar níveis de gravidade (NivelGravidade) com ações automáticas associadas.
        22. Configurar tolerância de erro temporal para monitoramento (padrão: 0.3s).
        23. Armazenar telemetria no banco após cada execução para estatísticas de aprendizado.

    # Cada plugin segue:

        * Herança da classe base Plugin
        * Responsabilidade única
        * Interface padronizada
        * Documentação completa
        * Finalização segura
        * Responsável por sua própria finalização
        * Metadados padrão (autor, data, dependências, tipo)
        * Suporte assíncrono nativo (executar_async)
        * Telemetria automática armazenada no banco
        * Níveis de gravidade com ações automáticas

    # Esta estrutura:

        * É modular
        * Evita dependências circulares
        * Facilita testes
        * Mantém organização clara
        * Separa responsabilidades

***** Padrão de plugins ***** 

        * Os plugins devem seguir o seguinte padrão (snake_case): plugin_nome.py
        * As classes devem seguir o seguinte padrão (CamelCase): PluginNome

    # Ciclo de vida dos Plugins 

        Cada plugin deve seguir um ciclo de vida bem definido, garantindo previsibilidade, segurança e rastreabilidade dentro do sistema.
        Esse ciclo é controlado pelo Gerenciador de Plugins, mas a responsabilidade de implementação correta cabe ao próprio plugin.

    1. Inicialização

        * O plugin é instanciado pelo GerenciadorPlugins, que injeta as dependências necessárias (ex: gerenciador_banco, gerenciador_log, etc.).
        * O método __init__ deve:
        * Definir self.PLUGIN_NAME de forma única e padronizada;
        * Registrar dependências internas (se houver);
        * Preparar estruturas internas (filas, caches, buffers);
        * Inicializar log específico via self.logger = gerenciador_log.get_logger(self.PLUGIN_NAME).
        * Use o método inicializar() para iniciar rotinas ou tarefas agendadas.

    2. Execução

        * Após a inicialização, o GerenciadorPlugins chama o método executar(), responsável por:
            Ler ou receber dados de entrada (de outros plugins ou de APIs externas);
            Processar, analisar e gerar resultados;
            Armazenar resultados intermediários em self.dados_completos (dividido entre crus e analisados);
            Retornar o status de execução usando enum StatusExecucao (OK, ERRO, AVISO, etc.);
        
        * Suporte assíncrono nativo:
            - Método executar_async() disponível para execução assíncrona
            - Útil quando threads forem substituídas por async workers
            - Por padrão, executa método síncrono em thread pool
        
        * Monitoramento de performance:
            - Tolerância de erro temporal configurável (padrão: 0.3s)
            - Aviso quando execução excede delay máximo aceitável
            - Telemetria armazenada automaticamente no banco após cada execução

    3. Persistência de Dados

        * Após a execução, o plugin deve persistir seus resultados (quando aplicável) via:

            self.gerenciador_banco.persistir_dados(
                plugin=self.PLUGIN_NAME,
                tabela="nome_da_tabela",
                dados=self.dados_completos["analisados"]
            )


        * O GerenciadorBanco valida, versiona e delega ao plugin BancoDados, que executa o CRUD real.
        * Nenhum plugin deve interagir diretamente com o banco.
        * Garantir desacoplamento e versionamento institucional de dados.

    4. Comunicação e Dependências

        * Caso o plugin dependa de dados de outro, ele deve declarar a dependência no plugins_dependencias.json, que é gerado automaticamente.
        * O GerenciadorPlugins se encarrega de garantir a ordem correta de execução e a entrega dos dados necessários.
        * Os dados recebidos devem ser tratados como somente leitura, evitando mutação de objetos compartilhados.

    5. Finalização Segura

        * Ao encerrar o sistema ou reiniciar o plugin, o método finalizar() é chamado.

            Esse método deve:
            Encerrar processos, threads ou tarefas assíncronas;
            Liberar recursos (arquivos, conexões, buffers);
            Registrar log de finalização (INFO);
            Garantir consistência dos dados persistidos.

    6. Auditoria e Rastreamento

        * Todos os eventos relevantes (inicialização, execução, persistência, erro e finalização) devem ser logados.

        * Logs devem conter, obrigatoriamente:
            [DD-MM-YYYY HH:MM:SS] [PLUGIN_NAME] [NÍVEL] Mensagem
        * O GerenciadorLog organiza os registros por tipo (bot, banco, sinais, etc.), conforme o diretório logs/.

        * Resumo do Ciclo de Vida

            | Etapa         | Responsável                 | Ação principal                        | Logs obrigatórios         |
            | ------------- | --------------------------- | ------------------------------------- | ------------------------- |
            | Inicialização | Plugin + GerenciadorPlugins | Criação e configuração de instância   | INFO: start               |
            | Execução      | Plugin                      | Processamento e análise de dados      | INFO: run start / run end |
            | Persistência  | Plugin + GerenciadorBanco   | Armazenamento institucional dos dados | INFO / ERROR              |
            | Comunicação   | Plugin + GerenciadorPlugins | Consumo de dependências               | DEBUG                     |
            | Finalização   | Plugin                      | Encerramento e liberação de recursos  | INFO: stop                |
            | Auditoria     | Todos                       | Registro completo de eventos          | INFO / ERROR              |


***** Banco de Dados *****

    # Regras para Banco de Dados:

        1 - Cada plugin declara suas tabelas via `plugin_tabelas`
        2 - Versionamento obrigatório (plugin_schema_versao)
        3 - Modos de acesso claros (own/write/read)
        4 - Validação automática na inicialização
        5 - Migração controlada entre versões
        6 - O schema.json é gerado e alimentado automaticamente
        7 - As tabelas são nomeadas usando o seguinte padrão: nome_plugin_tabela


    # Padrão mínimo esperado pelo schema_generator - cada plugin deve conter as suas próprias nuances:

        * O campo schema define as colunas da tabela conforme sintaxe SQL padrão PostgreSQL.
        * O campo modo_acesso informa se a tabela é exclusiva do plugin (own) ou compartilhada (shared).
        * O campo plugin serve para rastrear qual plugin é o responsável por criar/gerenciar essa tabela.
        * O campo descricao é opcional, mas ajuda na documentação e visualização futura.

    # Como usar:

        * nome_da_tabela: nome identificador da tabela no banco.
        * descricao (opcional, mas recomendado): explica o que essa tabela armazena.
        * modo_acesso: "own" se for só do plugin, "shared" se for comum entre vários.
        * plugin: use self.PLUGIN_NAME para manter rastreabilidade automática.
        * schema: dicionário onde a chave é o nome da coluna e o valor é o tipo SQL (pode conter constraints, ex: NOT NULL, DEFAULT, PRIMARY KEY).

        @property
        def plugin_tabelas(self) -> dict:
            return {
                "nome_da_tabela": {
                    "descricao": "Breve descrição do propósito da tabela.",
                    "modo_acesso": "own",  # ou 'shared'
                    "plugin": self.PLUGIN_NAME,
                    "schema": {
                        "coluna1": "TIPO_SQL [CONSTRAINTS]",
                        "coluna2": "TIPO_SQL [CONSTRAINTS]",
                        "coluna3": "TIPO_SQL [CONSTRAINTS]",
                        # ... adicione mais colunas conforme necessário
                    }
                }
            }



    # Padrão Institucional de Persistência de Dados entre Plugins e Banco

        * Fluxo recomendado para persistência de dados (CRUD):

        1. O plugin executa sua lógica e produz os dados a serem persistidos.
        2. O plugin envia os dados ao GerenciadorBanco (ou ao orquestrador institucional) através de um método padronizado, ex: `gerenciador_banco.persistir_dados(plugin, tabela, dados)`.
        3. O GerenciadorBanco valida, versiona e delega a operação ao plugin BancoDados (ou outro plugin de persistência), que executa o CRUD real.
        4. O BancoDados executa a operação, faz logging, versionamento e retorna o resultado ao GerenciadorBanco, que pode repassar ao plugin de origem.

        * Vantagens desse padrão:

            1. Desacoplamento total: plugins não dependem diretamente do BancoDados.
            2. Clareza e responsabilidade única: cada parte do sistema faz apenas o que lhe compete.
            3. Testabilidade: fácil mockar o gerenciador em testes.
            4. Evolução: backend de persistência pode mudar sem afetar plugins.
            5. Rastreabilidade e versionamento centralizados.

    * Exemplo de interface sugerida:

        python
        # No plugin:
        resultado = self.gerenciador_banco.persistir_dados(
            plugin=self.PLUGIN_NAME,
            tabela="minha_tabela",
            dados=meus_dados
        )

    # No GerenciadorBanco:
        def persistir_dados(self, plugin, tabela, dados):
            # Valida, versiona, loga e delega ao BancoDados
            return self._banco_dados.inserir(tabela, dados)
    

    # Observações:
        * O plugin nunca deve acessar diretamente o BancoDados.
        * O GerenciadorBanco pode implementar lógica adicional de versionamento, auditoria, fallback, etc.
        * O padrão deve ser seguido por todos os plugins que produzem dados a serem persistidos.


***** Estrutura do Projeto *****

    Smart_Trader/
    ├── main.py
    ├── .env
    ├── regras_de_ouro.txt
    │
    ├── plugins/
    │   ├── __init__.py
    │   │
    │   ├── indicadores/
    │   │    ├── __init__.py
    │   │    └── 
    │   │
    │   └── gerenciadores/
    │         ├── __init__.py
    │         ├── gerenciador.py
    │         ├── gerenciador_banco.py
    │         ├── gerenciador_bot.py
    │         ├── gerenciador_log.py
    │         └── gerenciador_plugins.py
    │
    ├── utils/
    │   ├── __init__.py
    │   └── config.py
    │
    └── logs/
        ├── bot/
        │   └── bot_DD-MM-YYYY.log
        ├── dados/
        │   └── dados_DD-MM-YYYY.log
        ├── banco/
        │   └── banco_DD-MM-YYYY.log
        ├── rastreamento/
        │   └── rastreamento_DD-MM-YYYY.log
        ├── sinais/
        │   └── sinais_DD-MM-YYYY.log
        └── erros/
            └── erros_DD-MM-YYYY.log


***** Erros e Exceções *****

    # Regra única: A manipulação de erros e exceções deve seguir um **padrão institucional** para garantir a **confiabilidade, rastreabilidade e isolamento de falhas** dentro do sistema. Cada plugin é responsável por tratar seus próprios erros, evitando que falhas locais afetem outros módulos.

    1. Princípios Gerais

        1. **Nunca deixar exceções não tratadas** atingirem o `GerenciadorPlugins` ou o `GerenciadorBot`.
        2. **Tratar exceções o mais próximo possível da origem**, dentro do escopo funcional onde o erro ocorreu.
        3. **Usar logging estruturado** para registrar qualquer evento inesperado.
        4. **Nunca silenciar exceções sem registro** — toda falha deve ser logada.
        5. **Evitar o uso genérico de `except Exception:`** sem controle; prefira capturas específicas (ex: `except ValueError`, `except ConnectionError`, etc.).

    2. Estrutura Padrão de Tratamento

        # Todo bloco de execução crítica deve seguir o formato abaixo:

        python
        try:
            # Operação crítica (ex: cálculo, requisição, persistência)
            resultado = self.executar_analise(dados)
            self.logger.info(f"[{self.PLUGIN_NAME}] Execução concluída com sucesso.")
        except (ConnectionError, TimeoutError) as e:
            self.logger.warning(f"[{self.PLUGIN_NAME}] Problema de conexão: {e}")
            self.tratar_retentativa()
        except ValueError as e:
            self.logger.error(f"[{self.PLUGIN_NAME}] Erro de valor: {e}")
            self.tratar_dado_invalido()
        except Exception as e:
            self.logger.critical(f"[{self.PLUGIN_NAME}] Erro inesperado: {e}", exc_info=True)
        finally:
            self.finalizar_operacao()
        

        > Sempre use `exc_info=True` nos logs de erro inesperado para capturar o *stack trace* completo.


    3. Uso de `try/finally` e Context Managers

        O uso de blocos `try/finally` e métodos de contexto (`__enter__`, `__exit__`) é **obrigatório** para garantir limpeza de recursos, mesmo em caso de falha.

        
        try:
            self.conexao = self.abrir_conexao()
            # Processar dados
        finally:
            if self.conexao:
                self.conexao.close()
                self.logger.info(f"[{self.PLUGIN_NAME}] Conexão encerrada com segurança.")
        

        > Exemplo com contexto:
        >
        > python
        > with self.gerenciador_banco.sessao() as sessao:
        >     sessao.salvar(dados)
        > 
        >
        > Isso garante que o fechamento da sessão ocorra automaticamente, mesmo se ocorrer erro.

    4. Classificação de Logs de Erro e Níveis de Gravidade

        O sistema utiliza enum `NivelGravidade` com ações automáticas associadas:

        | Nível de Gravidade | Ação Automática                           | Quando Usar                                  |
        |-------------------|-------------------------------------------|----------------------------------------------|
        | `INFO`            | Nenhuma ação                              | Operação normal, informativo                 |
        | `WARNING`         | Log de aviso                              | Algo inesperado, mas resolvido automaticamente |
        | `ERROR`           | Tentativa de recuperação automática       | Erro recuperável, tentar corrigir            |
        | `CRITICAL`        | Reinicialização do plugin                 | Erro crítico, requer reinicialização        |

        **Ações Automáticas:**
        - **ERROR**: Chama método `_tentar_recuperacao()` (pode ser sobrescrito em plugins filhos)
        - **CRITICAL**: Reinicializa plugin automaticamente (finalizar → inicializar)

        **Status de Execução:**
        - Use enum `StatusExecucao` (OK, ERRO, AVISO, PENDENTE, CANCELADO) em vez de strings
        - Melhora legibilidade e facilita classificação pela IA

        | Tipo de erro                                              | Nível de log | Ação recomendada                           |
        | --------------------------------------------------------- | ------------ | ------------------------------------------ |
        | Erros previstos (ex: dados inválidos)                     | `ERROR`      | Corrigir entrada ou validação              |
        | Erros externos (ex: API, rede)                            | `WARNING`    | Retentar ou adiar execução                 |
        | Erros críticos (ex: falha de lógica, exceção não tratada) | `CRITICAL`   | Reinicialização automática do plugin       |
        | Erros durante finalização                                 | `ERROR`      | Logar e garantir limpeza manual            |
        | Falhas de persistência                                    | `ERROR`      | Logar e ativar fallback se possível        |

    5. Integração com o Sistema de Logs

        * Todos os erros devem ser registrados em `logs/erros/erros_DD-MM-YYYY.log`.
        * Use prefixos claros para rastreabilidade:
        
        [PLUGIN_NAME] [TIPO_DE_ERRO] Mensagem detalhada
        
        * Exemplo:

        
        [IndicadorRSI] [CRITICAL] Erro inesperado ao processar candle: list index out of range
        
***** VERSIONAMENTO E DEPLOY *****
        1. Versionamento de Plugins  
            * Campo obrigatório: `plugin_versao = "vX.Y.Z"` (SemVer)  
            * `MAJOR`: quebra de compatibilidade  
            * `MINOR`: novas features  
            * `PATCH`: correções  

        2. Registro de Alterações  
            * `CHANGELOG.md` institucional (raiz do projeto)  
            * Formato:  
                ```
                    ## [v1.3.2] - 01/11/2025
                    ### PluginIndicadorRSI
                    - Corrigido cálculo em 1m
                    - Adicionado fallback
                ```

        3. Migração de Schema  
            1. GerenciadorBanco compara `plugin_schema_versao`  
            2. Scripts em `plugins/migracoes/vX_to_vY_plugin.py`  
            3. Execução automática na inicialização  
            4. Teste obrigatório em staging  
            5. Log: `[GerenciadorBanco] Migração v1.2 → v1.3 OK`
            6. Histórico de versões registrado automaticamente na tabela `schema_versoes`
            7. Cada mudança de schema é rastreada com timestamp, descrição e migração SQL

***** PADRÃO DE OPERAÇÕES CRUD *****

    # Estrutura de Métodos do PluginBancoDados

        O PluginBancoDados segue um padrão específico para organização de código:

        * **Métodos Internos (com underscore)**:
            - `_inserir_velas()` - Lógica específica para inserção de velas
            - `_inserir_telemetria()` - Lógica específica para inserção de telemetria
            - `_inserir_generico()` - Lógica genérica para inserção
            - `_consultar()` - Lógica de consulta
            - `_atualizar()` - Lógica de atualização
            - `_deletar()` - Lógica de exclusão
            - `_formatar_retorno()` - Formata retorno padronizado
            - `_obter_conexao()` - Obtém conexão do pool
            - `_devolver_conexao()` - Devolve conexão ao pool

        * **Métodos Públicos (sem underscore)**:
            - `inserir()` - Interface pública para inserção
            - `consultar()` - Interface pública para consulta
            - `atualizar()` - Interface pública para atualização
            - `deletar()` - Interface pública para exclusão
            - `atualizar_view_materializada()` - Atualiza view materializada

    # Logs Padronizados

        Todas as operações CRUD geram logs padronizados:

        ```
        [BancoDados][INSERT] Inserindo dados na tabela 'velas'
        [BancoDados][INSERT] 1 registro(s) inserido(s) na tabela 'velas'
        
        [BancoDados][SELECT] Consultando tabela 'velas'
        [BancoDados][SELECT] 60 registro(s) encontrado(s) na tabela 'velas'
        
        [BancoDados][UPDATE] Atualizando tabela 'velas'
        [BancoDados][UPDATE] 1 registro(s) atualizado(s) na tabela 'velas'
        
        [BancoDados][DELETE] Deletando da tabela 'velas'
        [BancoDados][DELETE] 1 registro(s) deletado(s) da tabela 'velas'
        ```

    # Retorno Padronizado

        Todas as operações CRUD retornam um dicionário padronizado para facilitar integração com IA:

        ```python
        {
            "sucesso": bool,              # True se operação foi bem-sucedida
            "operacao": str,               # INSERT, UPDATE, SELECT, DELETE, REFRESH
            "tabela": str,                 # Nome da tabela
            "dados": Any,                  # Dados retornados (SELECT) ou inseridos/atualizados
            "mensagem": str,               # Mensagem descritiva
            "linhas_afetadas": int,        # Número de linhas afetadas
            "erro": Optional[str],         # Mensagem de erro (se houver)
            "timestamp": str               # Timestamp ISO da operação
        }
        ```

        **Benefícios:**
        - Facilita integração com IA (estrutura consistente)
        - Facilita depuração (sempre sabe o que esperar)
        - Facilita auditoria (timestamp em todas as operações)
        - Facilita tratamento de erros (campo erro padronizado)

    # Segurança em Operações CRUD

        * **SQL Injection Prevention**:
            - Uso de `sql.Identifier` para tabelas e colunas
            - Uso de placeholders `%s` para valores
            - Validação de tipos antes de inserção

        * **Validação de Filtros**:
            - UPDATE e DELETE **requerem filtros obrigatórios**
            - Previne atualizações/deleções acidentais em toda a tabela
            - Exemplo de erro: "Filtros não fornecidos (atualização sem filtros é perigosa)"

        * **Validação de Dados**:
            - Verificação de estrutura antes de inserção
            - Validação de tipos e valores
            - Rollback automático em caso de erro

    * RESPONSABILIDADES DOS GERENCIADORES – TABELA EXECUTIVA

        | Gerenciador           | Responsabilidade Principal                            | Não Faz                             |
        |-----------------------|-------------------------------------------------------|-------------------------------------|
        | GerenciadorPlugins| Orquestra ciclo de vida, dependências, ordem          | Não acessa banco ou API                 |
        | GerenciadorBanco  | Valida, versiona, migra, delega persistência          | Não executa CRUD real                   |
        | GerenciadorBot    | Controle de trades, risco, TP/SL, alavancagem         | Não processa indicadores                |
        | GerenciadorLog    | Centraliza logs, formatação, rotação, níveis          | Não filtra lógica de negócio            |

***** METADADOS E TIPOS DE PLUGIN *****

    # Metadados Padrão de Plugin

        Cada plugin deve incluir metadados padrão para classificação pela IA:

        - **autor**: Autor do plugin (padrão: "SmartTrader Team")
        - **data_criacao**: Data de criação do plugin (ISO format)
        - **data_atualizacao**: Data da última atualização (atualizado automaticamente)
        - **dependencias**: Lista de dependências explícitas do plugin
        - **tipo**: Tipo do plugin na hierarquia (TipoPlugin enum)
        - **descricao**: Descrição do propósito do plugin

        Estes metadados são acessíveis via `self.plugin_metadados` e são úteis para:
        - Classificação automática de módulos pela IA
        - Rastreamento de dependências
        - Documentação e introspecção

    # Hierarquia de Tipos de Plugin

        O sistema utiliza enum `TipoPlugin` para hierarquia e organização:

        - **INDICADOR**: Plugins que calculam indicadores técnicos (RSI, MACD, etc.)
        - **GERENCIADOR**: Gerenciadores do sistema (Log, Banco, Plugins, Bot)
        - **CONEXAO**: Plugins de conexão com APIs externas (Bybit, etc.)
        - **DADOS**: Plugins que processam dados brutos (velas, dados de mercado)
        - **IA**: Plugins de inteligência artificial (Llama, análise preditiva)
        - **AUXILIAR**: Plugins auxiliares (utilitários, helpers)

        Útil para IA classificar e organizar módulos automaticamente.

***** MONITORAMENTO E TELEMETRIA *****

    # Tolerância de Erro Temporal

        Cada plugin possui `monitoramento_delay_maximo` (padrão: 0.3s):
        - Aviso quando execução excede delay máximo aceitável
        - Útil para IA avaliar sincronização entre plugins
        - Configurável via config ou no __init__ do plugin

    # Armazenamento de Telemetria

        Telemetria é armazenada automaticamente no banco após cada execução:
        - Tabela `telemetria_plugins` armazena todas as métricas
        - Gera estatísticas de aprendizado para IA
        - Permite análise de performance e estabilidade ao longo do tempo

        Métricas coletadas:
        - Total de execuções, sucessos, erros
        - Falhas consecutivas (alerta de instabilidade)
        - Tempos médio, mínimo, máximo
        - Taxa de sucesso
        - Última execução e status
        - Nível de gravidade atual

***** SUPORTE ASSÍNCRONO *****

    # Execução Assíncrona Nativa

        Todos os plugins suportam execução assíncrona nativa:
        - Método `executar_async()` disponível na classe base
        - Por padrão, executa método síncrono em thread pool
        - Plugins filhos podem sobrescrever para implementar lógica assíncrona real
        - Útil quando threads forem substituídas por async workers

        Exemplo de uso:
        ```python
        resultado = await plugin.executar_async(dados)
        ```