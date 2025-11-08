"""
Plugin de Banco de Dados PostgreSQL - Sistema Smart Trader.

Gerencia conexão e operações CRUD com PostgreSQL.
Conforme instrucao-velas.md: salva velas com upsert para evitar duplicatas.

__institucional__ = "Smart_Trader Plugin Banco Dados - Sistema 6/8 Unificado"

Estrutura:
- Métodos internos com underscore (_inserir, _atualizar, _consultar, _deletar)
- Métodos públicos sem underscore expostos (inserir, atualizar, consultar, deletar)
- Logs padronizados: [BancoDados][INSERT], [UPDATE], [SELECT], [DELETE]
- Retorno padronizado em dicionário para facilitar integração com IA
"""

import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor, execute_values
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from plugins.base_plugin import Plugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol, StatusExecucao, TipoPlugin


class PluginBancoDados(Plugin):
    """
    Plugin que gerencia conexão e operações CRUD com PostgreSQL.
    
    Responsabilidades:
    - Gerenciar pool de conexões PostgreSQL
    - Executar operações CRUD (INSERT, UPDATE, SELECT, DELETE)
    - Implementar upsert para evitar duplicatas (velas)
    - Criar tabelas automaticamente se não existirem
    - Gerenciar transações e rollback
    - Fornecer retorno padronizado para integração com IA
    
    Características:
    - Pool de conexões para performance
    - Upsert com ON CONFLICT DO UPDATE
    - Validação de schema antes de inserir
    - Timeout de conexão configurável
    - Logs padronizados por operação
    - Retorno padronizado em dicionário
    
    Uso:
        plugin = PluginBancoDados(gerenciador_log, gerenciador_banco, config)
        plugin.inicializar()
        
        # Inserir
        resultado = plugin.inserir("velas", dados)
        
        # Consultar
        resultado = plugin.consultar("velas", {"ativo": "BTCUSDT"})
        
        # Atualizar
        resultado = plugin.atualizar("velas", {"ativo": "BTCUSDT"}, {"volume": 1000})
        
        # Deletar
        resultado = plugin.deletar("velas", {"ativo": "BTCUSDT"})
    """
    
    __institucional__ = "Smart_Trader Plugin Banco Dados - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginBancoDados"
    plugin_versao = "v1.3.0"
    plugin_schema_versao = "v1.3.0"
    plugin_tipo = TipoPlugin.GERENCIADOR
    
    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLogProtocol] = None,
        gerenciador_banco: Optional[GerenciadorBancoProtocol] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o PluginBancoDados.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            gerenciador_banco: Instância do GerenciadorBanco
            config: Configuração do sistema (deve conter credenciais do banco)
        """
        super().__init__(gerenciador_log, gerenciador_banco, config)
        
        # Configurações do banco (do config)
        db_config = self.config.get("db", {})
        
        # Normaliza credenciais para garantir codificação UTF-8 correta
        def _normalizar_string(valor):
            """Normaliza string para garantir codificação UTF-8."""
            if valor is None:
                return None
            if isinstance(valor, bytes):
                # Se for bytes, tenta decodificar como UTF-8, fallback para latin-1
                try:
                    return valor.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        return valor.decode("latin-1")
                    except UnicodeDecodeError:
                        # Último fallback: ignora caracteres inválidos
                        return valor.decode("utf-8", errors="ignore")
            if isinstance(valor, str):
                # Se for string, garante que está em UTF-8 válido
                # Remove caracteres de controle e normaliza
                try:
                    # Tenta codificar/decodificar para garantir UTF-8 válido
                    valor_limpo = valor.encode("utf-8", errors="replace").decode("utf-8")
                    # Remove caracteres de controle não imprimíveis
                    valor_limpo = "".join(char for char in valor_limpo if ord(char) >= 32 or char in "\n\r\t")
                    return valor_limpo
                except Exception:
                    # Fallback: retorna string original se der erro
                    return valor
            return str(valor)
        
        self.db_host = _normalizar_string(db_config.get("host", "localhost"))
        self.db_name = _normalizar_string(db_config.get("database", "smarttrader"))
        self.db_user = _normalizar_string(db_config.get("user"))
        self.db_password = _normalizar_string(db_config.get("password"))
        self.db_port = db_config.get("port", 5432)
        
        # Pool de conexões
        self.connection_pool: Optional[pool.ThreadedConnectionPool] = None
        self.min_connections = 1
        self.max_connections = 5
        
        # Timeout de conexão (em segundos)
        self.connection_timeout = 10
    
    def _inicializar_interno(self) -> bool:
        """
        Inicializa conexão com PostgreSQL e cria pool de conexões.
        
        Returns:
            bool: True se conexão estabelecida com sucesso
        """
        try:
            # Valida credenciais
            if not all([self.db_host, self.db_name, self.db_user, self.db_password]):
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}] Credenciais do banco não encontradas na configuração"
                    )
                return False
            
            # Cria pool de conexões
            # Garante que todos os parâmetros sejam strings válidas antes de passar para psycopg2
            try:
                # Função robusta para garantir UTF-8 válido
                def _garantir_utf8_seguro(valor):
                    """Converte valor para string UTF-8 válida de forma segura."""
                    if valor is None:
                        return None
                    
                    # Converte para string se necessário
                    if not isinstance(valor, (str, bytes)):
                        valor = str(valor)
                    
                    # Se for bytes, primeiro decodifica
                    if isinstance(valor, bytes):
                        try:
                            valor = valor.decode('utf-8')
                        except UnicodeDecodeError:
                            try:
                                valor = valor.decode('latin-1')
                            except UnicodeDecodeError:
                                valor = valor.decode('utf-8', errors='replace')
                    
                    # Agora valor é string - limpa completamente
                    if isinstance(valor, str):
                        # Remove caracteres de controle e normaliza
                        # Primeiro, tenta garantir que é UTF-8 válido
                        try:
                            # Força codificação/decodificação para limpar bytes inválidos
                            valor_bytes = valor.encode('utf-8', errors='replace')
                            valor_limpo = valor_bytes.decode('utf-8', errors='replace')
                            
                            # Remove caracteres de controle não imprimíveis (exceto espaços, tabs, newlines)
                            valor_limpo = ''.join(
                                char for char in valor_limpo 
                                if char.isprintable() or char in '\n\r\t'
                            )
                            
                            # Remove espaços no início e fim
                            valor_limpo = valor_limpo.strip()
                            
                            return valor_limpo
                        except Exception:
                            # Último recurso: remove tudo que não for ASCII imprimível
                            return ''.join(
                                char for char in str(valor) 
                                if 32 <= ord(char) <= 126 or char in '\n\r\t'
                            ).strip()
                    
                    return str(valor).strip()
                
                # Normaliza todos os parâmetros
                host = _garantir_utf8_seguro(self.db_host) or "localhost"
                database = _garantir_utf8_seguro(self.db_name) or "smarttrader"
                user = _garantir_utf8_seguro(self.db_user)
                password = _garantir_utf8_seguro(self.db_password)
                port = int(self.db_port) if self.db_port else 5432
                
                # Valida que não há None em campos obrigatórios
                if not all([host, database, user, password]):
                    if self.logger:
                        self.logger.error(
                            f"[{self.PLUGIN_NAME}] Credenciais inválidas após normalização"
                        )
                    return False
                
                # Garante que todos os valores são strings válidas (não bytes)
                # e que não contêm caracteres problemáticos
                host = str(host) if host else "localhost"
                database = str(database) if database else "smarttrader"
                user = str(user) if user else None
                password = str(password) if password else None
                
                # Valida novamente após conversão
                if not all([host, database, user, password]):
                    if self.logger:
                        self.logger.error(
                            f"[{self.PLUGIN_NAME}] Credenciais inválidas após conversão para string"
                        )
                    return False
                
                # Cria o banco de dados se não existir
                self._criar_banco_se_necessario(host, user, password, port, database)
                
                # Tenta criar o pool de conexões
                # Usa parâmetros individuais (mais seguro para encoding)
                # Garante que todos os valores são strings Python válidas
                try:
                    self.connection_pool = pool.ThreadedConnectionPool(
                        minconn=self.min_connections,
                        maxconn=self.max_connections,
                        host=str(host),
                        database=str(database),
                        user=str(user),
                        password=str(password),
                        port=int(port),
                        connect_timeout=self.connection_timeout,
                    )
                except (UnicodeDecodeError, UnicodeEncodeError) as e:
                    # Se ainda houver erro de encoding, tenta usar DSN string
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Erro de encoding com parâmetros individuais, "
                            f"tentando DSN string: {e}"
                        )
                    # Constrói DSN string manualmente (mais controle sobre encoding)
                    dsn = f"host={host} dbname={database} user={user} password={password} port={port} connect_timeout={self.connection_timeout}"
                    # Garante que DSN é UTF-8 válido
                    dsn = dsn.encode('utf-8', errors='replace').decode('utf-8')
                    self.connection_pool = pool.ThreadedConnectionPool(
                        minconn=self.min_connections,
                        maxconn=self.max_connections,
                        dsn=dsn,
                    )
                
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Pool de conexões criado com sucesso "
                        f"(host={self.db_host}, database={self.db_name})"
                    )
                
                # Testa conexão criando tabelas se não existirem
                self._criar_tabelas_se_necessario()
                
                return True
                
            except psycopg2.Error as e:
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}] Erro ao criar pool de conexões: {e}",
                        exc_info=True,
                    )
                return False
                
        except Exception as e:
            if self.logger:
                self.logger.critical(
                    f"[{self.PLUGIN_NAME}] Erro ao inicializar conexão: {e}",
                    exc_info=True,
                )
            return False
    
    def _criar_banco_se_necessario(self, host: str, user: str, password: str, port: int, database: str):
        """
        Cria o banco de dados se não existir.
        
        Conecta ao banco padrão 'postgres' para criar o banco 'smarttrader'.
        
        Args:
            host: Host do PostgreSQL
            user: Usuário do PostgreSQL
            password: Senha do PostgreSQL
            port: Porta do PostgreSQL
            database: Nome do banco de dados a criar
        """
        try:
            # Conecta ao banco padrão 'postgres' para criar o banco
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Verificando se banco de dados '{database}' existe..."
                )
            
            # Conecta ao banco padrão 'postgres'
            conn_postgres = psycopg2.connect(
                host=host,
                database="postgres",  # Banco padrão do PostgreSQL
                user=user,
                password=password,
                port=port,
                connect_timeout=self.connection_timeout,
            )
            
            # Desabilita autocommit para poder executar CREATE DATABASE
            conn_postgres.autocommit = True
            cursor = conn_postgres.cursor()
            
            # Verifica se o banco existe
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (database,)
            )
            
            existe = cursor.fetchone()
            
            if not existe:
                # Cria o banco de dados
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Banco de dados '{database}' não existe. Criando..."
                    )
                
                # Usa sql.Identifier para segurança (evita SQL injection)
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(
                        sql.Identifier(database)
                    )
                )
                
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Banco de dados '{database}' criado com sucesso"
                    )
            else:
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Banco de dados '{database}' já existe"
                    )
            
            cursor.close()
            conn_postgres.close()
            
        except psycopg2.Error as e:
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Erro ao verificar/criar banco de dados '{database}': {e}. "
                    f"Tentando conectar mesmo assim (banco pode já existir)..."
                )
            # Não falha completamente - pode ser que o banco já exista
            # ou que não tenhamos permissão para criar
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Erro inesperado ao verificar/criar banco de dados: {e}. "
                    f"Tentando conectar mesmo assim..."
                )
    
    def _criar_tabelas_se_necessario(self):
        """
        Cria tabelas necessárias se não existirem.
        
        Conforme instrucao-velas.md: cria tabela 'velas' com estrutura otimizada.
        """
        try:
            conn = self._obter_conexao()
            if not conn:
                return False
            
            cursor = conn.cursor()
            
            # Cria tabela velas conforme instrucao-velas.md
            # Adicionado campo exchange para suporte multi-exchange futuro
            # Adicionado campo testnet para distinguir dados de testnet e mainnet
            create_velas_table = """
            CREATE TABLE IF NOT EXISTS velas (
                id SERIAL PRIMARY KEY,
                exchange VARCHAR(20) DEFAULT 'bybit',  -- Campo exchange para multi-exchange
                ativo VARCHAR(20) NOT NULL,
                timeframe VARCHAR(5) NOT NULL,
                open_time TIMESTAMP NOT NULL,
                close_time TIMESTAMP NOT NULL,
                open NUMERIC(20,8) NOT NULL,
                high NUMERIC(20,8) NOT NULL,
                low NUMERIC(20,8) NOT NULL,
                close NUMERIC(20,8) NOT NULL,
                volume NUMERIC(20,8) NOT NULL,
                fechada BOOLEAN DEFAULT TRUE,
                testnet BOOLEAN DEFAULT FALSE,  -- Campo para distinguir testnet/mainnet
                criado_em TIMESTAMP DEFAULT NOW(),
                atualizado_em TIMESTAMP DEFAULT NOW(),
                
                -- Chave única para evitar duplicatas (inclui exchange e testnet)
                CONSTRAINT unique_vela UNIQUE (exchange, ativo, timeframe, open_time, testnet)
            );
            
            -- Adiciona coluna testnet se não existir (para migração de tabelas existentes)
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'velas' AND column_name = 'testnet'
                ) THEN
                    ALTER TABLE velas ADD COLUMN testnet BOOLEAN DEFAULT FALSE;
                    -- Atualiza constraint única para incluir testnet
                    ALTER TABLE velas DROP CONSTRAINT IF EXISTS unique_vela;
                    ALTER TABLE velas ADD CONSTRAINT unique_vela 
                        UNIQUE (exchange, ativo, timeframe, open_time, testnet);
                END IF;
            END $$;
            
            -- Ãndice composto para consultas rÃ¡pidas
            CREATE INDEX IF NOT EXISTS idx_vela_lookup 
            ON velas(ativo, timeframe, open_time);
            
            -- Ãndice para consultas por ativo
            CREATE INDEX IF NOT EXISTS idx_vela_ativo 
            ON velas(ativo);
            
            -- Ãndice para consultas por timeframe
            CREATE INDEX IF NOT EXISTS idx_vela_timeframe 
            ON velas(timeframe);
            
            -- Ãndice para consultas por data
            CREATE INDEX IF NOT EXISTS idx_vela_open_time 
            ON velas(open_time);
            
            -- Índice para consultas por exchange
            CREATE INDEX IF NOT EXISTS idx_vela_exchange 
            ON velas(exchange);
            
            -- Índice para consultas por testnet (filtrar testnet/mainnet)
            CREATE INDEX IF NOT EXISTS idx_vela_testnet 
            ON velas(testnet);
            
            -- Tabela de telemetria de plugins (para estatísticas de aprendizado para IA)
            CREATE TABLE IF NOT EXISTS telemetria_plugins (
                id SERIAL PRIMARY KEY,
                plugin VARCHAR(100) NOT NULL,
                timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
                total_execucoes INTEGER DEFAULT 0,
                execucoes_sucesso INTEGER DEFAULT 0,
                execucoes_erro INTEGER DEFAULT 0,
                falhas_consecutivas INTEGER DEFAULT 0,
                tempo_medio NUMERIC(10,6) DEFAULT 0.0,
                tempo_minimo NUMERIC(10,6) DEFAULT 0.0,
                tempo_maximo NUMERIC(10,6) DEFAULT 0.0,
                taxa_sucesso NUMERIC(5,4) DEFAULT 0.0,
                ultima_execucao TIMESTAMP,
                ultimo_status VARCHAR(20),
                nivel_gravidade VARCHAR(20) DEFAULT 'info',
                criado_em TIMESTAMP DEFAULT NOW()
            );
            
            -- Ãndice para consultas de telemetria por plugin
            CREATE INDEX IF NOT EXISTS idx_telemetria_plugin 
            ON telemetria_plugins(plugin, timestamp);
            
            -- Tabela de histórico de versões de schema (útil quando migrar tabelas)
            CREATE TABLE IF NOT EXISTS schema_versoes (
                id SERIAL PRIMARY KEY,
                tabela VARCHAR(100) NOT NULL,
                versao VARCHAR(20) NOT NULL,
                descricao TEXT,
                migracao_sql TEXT,
                aplicado_em TIMESTAMP DEFAULT NOW(),
                aplicado_por VARCHAR(100),
                CONSTRAINT unique_schema_versao UNIQUE (tabela, versao)
            );
            
            -- Ãndice para consultas de histÃ³rico de schema
            CREATE INDEX IF NOT EXISTS idx_schema_versoes_tabela 
            ON schema_versoes(tabela, versao);
            
            -- View materializada para médias e indicadores agregados
            -- Acelera análises da IA sem recalcular tudo
            -- Remove view antiga se existir (para atualizar estrutura)
            DROP MATERIALIZED VIEW IF EXISTS mv_velas_agregadas;
            
            CREATE MATERIALIZED VIEW mv_velas_agregadas AS
            SELECT 
                exchange,
                ativo,
                timeframe,
                testnet,
                DATE_TRUNC('hour', open_time) as hora,
                COUNT(*) as total_velas,
                AVG(close) as media_close,
                AVG(high) as media_high,
                AVG(low) as media_low,
                AVG(volume) as media_volume,
                MAX(high) as max_high,
                MIN(low) as min_low,
                SUM(volume) as volume_total,
                STDDEV(close) as desvio_close,
                AVG(high - low) as media_range
            FROM velas
            WHERE fechada = TRUE
            GROUP BY exchange, ativo, timeframe, testnet, DATE_TRUNC('hour', open_time);
            
            -- Índice para view materializada
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_velas_agregadas 
            ON mv_velas_agregadas(exchange, ativo, timeframe, testnet, hora);
            
            -- Tabelas de Padrões de Trading (v1.3.0)
            -- Tabela: padroes_detectados
            CREATE TABLE IF NOT EXISTS padroes_detectados (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                timeframe VARCHAR(5) NOT NULL,
                open_time TIMESTAMP NOT NULL,
                tipo_padrao VARCHAR(50) NOT NULL,
                direcao VARCHAR(10) NOT NULL,
                score NUMERIC(5,4) NOT NULL,
                confidence NUMERIC(5,4) NOT NULL,
                regime VARCHAR(20) NOT NULL,
                suggested_sl NUMERIC(20,8),
                suggested_tp NUMERIC(20,8),
                final_score NUMERIC(5,4) NOT NULL,
                meta JSONB,
                criado_em TIMESTAMP DEFAULT NOW()
            );
            
            -- Índices para padroes_detectados
            CREATE INDEX IF NOT EXISTS idx_padroes_symbol_timeframe 
            ON padroes_detectados(symbol, timeframe, open_time);
            
            CREATE INDEX IF NOT EXISTS idx_padroes_tipo 
            ON padroes_detectados(tipo_padrao);
            
            CREATE INDEX IF NOT EXISTS idx_padroes_final_score 
            ON padroes_detectados(final_score);
            
            -- Tabela: padroes_metricas
            CREATE TABLE IF NOT EXISTS padroes_metricas (
                id SERIAL PRIMARY KEY,
                tipo_padrao VARCHAR(50) NOT NULL,
                symbol VARCHAR(20),
                timeframe VARCHAR(5),
                periodo_inicio TIMESTAMP NOT NULL,
                periodo_fim TIMESTAMP NOT NULL,
                frequency NUMERIC(10,4) NOT NULL,
                precision NUMERIC(5,4),
                recall NUMERIC(5,4),
                expectancy NUMERIC(10,4),
                sharpe_condicional NUMERIC(10,4),
                drawdown_condicional NUMERIC(10,4),
                winrate NUMERIC(5,4),
                avg_rr NUMERIC(5,4),
                total_trades INTEGER DEFAULT 0,
                trades_win INTEGER DEFAULT 0,
                trades_loss INTEGER DEFAULT 0,
                tipo_validacao VARCHAR(20),
                criado_em TIMESTAMP DEFAULT NOW()
            );
            
            -- Índices para padroes_metricas
            CREATE INDEX IF NOT EXISTS idx_padroes_metricas_tipo 
            ON padroes_metricas(tipo_padrao, periodo_inicio, periodo_fim);
            
            CREATE INDEX IF NOT EXISTS idx_padroes_metricas_validacao 
            ON padroes_metricas(tipo_validacao);
            
            -- Tabela: padroes_confidence
            CREATE TABLE IF NOT EXISTS padroes_confidence (
                id SERIAL PRIMARY KEY,
                tipo_padrao VARCHAR(50) NOT NULL,
                symbol VARCHAR(20),
                timeframe VARCHAR(5),
                data_ultimo_win TIMESTAMP,
                days_since_last_win INTEGER,
                base_score NUMERIC(5,4) NOT NULL,
                confidence_score NUMERIC(5,4) NOT NULL,
                em_quarentena BOOLEAN DEFAULT FALSE,
                criado_em TIMESTAMP DEFAULT NOW()
            );
            
            -- Índices para padroes_confidence
            CREATE INDEX IF NOT EXISTS idx_padroes_confidence_tipo 
            ON padroes_confidence(tipo_padrao, symbol, timeframe);
            
            CREATE INDEX IF NOT EXISTS idx_padroes_confidence_quarentena 
            ON padroes_confidence(em_quarentena);
            """
            
            cursor.execute(create_velas_table)
            conn.commit()
            
            # Registra versão do schema no histórico
            self._registrar_versao_schema("velas", "v1.2.0", 
                "PluginBancoDados refatorado com CRUD completo e retorno padronizado", conn)
            
            # Registra versão das tabelas de padrões (v1.3.0)
            self._registrar_versao_schema("padroes_detectados", "v1.3.0", 
                "Tabela de padrões detectados com telemetria completa", conn)
            self._registrar_versao_schema("padroes_metricas", "v1.3.0", 
                "Tabela de métricas de performance por padrão", conn)
            self._registrar_versao_schema("padroes_confidence", "v1.3.0", 
                "Tabela de histórico de confidence decay", conn)
            
            cursor.close()
            self._devolver_conexao(conn)
            
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Tabelas criadas/verificadas com sucesso"
                )
            
            return True
            
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao criar tabelas: {e}",
                    exc_info=True,
                )
            return False
        except Exception as e:
            if conn:
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro inesperado ao criar tabelas: {e}",
                    exc_info=True,
                )
            return False
    
    def _obter_conexao(self):
        """
        Obtém conexão do pool.
        
        Returns:
            psycopg2.connection: Conexão do pool ou None
        """
        try:
            if not self.connection_pool:
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}] Pool de conexões não inicializado"
                    )
                return None
            
            return self.connection_pool.getconn()
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao obter conexão: {e}",
                    exc_info=True,
                )
            return None
    
    def _devolver_conexao(self, conn):
        """
        Devolve conexão para o pool.
        
        Args:
            conn: Conexão a ser devolvida
        """
        try:
            if self.connection_pool and conn:
                self.connection_pool.putconn(conn)
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao devolver conexão: {e}",
                    exc_info=True,
                )
    
    def _formatar_retorno(
        self,
        sucesso: bool,
        operacao: str,
        tabela: str,
        dados: Optional[Any] = None,
        mensagem: Optional[str] = None,
        linhas_afetadas: int = 0,
        erro: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Formata retorno padronizado para todas as operações CRUD.
        
        Útil para integração com IA e padronização de respostas.
        
        Args:
            sucesso: Se operação foi bem-sucedida
            operacao: Tipo de operação (INSERT, UPDATE, SELECT, DELETE)
            tabela: Nome da tabela
            dados: Dados retornados (para SELECT) ou inseridos/atualizados
            mensagem: Mensagem descritiva
            linhas_afetadas: Número de linhas afetadas
            erro: Mensagem de erro (se houver)
            
        Returns:
            dict: Retorno padronizado:
            {
                "sucesso": bool,
                "operacao": str,
                "tabela": str,
                "dados": Any,
                "mensagem": str,
                "linhas_afetadas": int,
                "erro": Optional[str],
                "timestamp": str
            }
        """
        return {
            "sucesso": sucesso,
            "operacao": operacao,
            "tabela": tabela,
            "dados": dados,
            "mensagem": mensagem or (f"Operação {operacao} executada com sucesso" if sucesso else f"Erro na operação {operacao}"),
            "linhas_afetadas": linhas_afetadas,
            "erro": erro,
            "timestamp": datetime.now().isoformat(),
        }
    
    # ============================================================
    # MÉTODOS PÚBLICOS CRUD (SEM UNDERSCORE)
    # ============================================================
    
    def inserir(self, tabela: str, dados: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Insere dados na tabela especificada.
        
        Método público para inserção de dados. Delega para métodos internos
        específicos por tabela.
        
        Args:
            tabela: Nome da tabela
            dados: Dados a serem inseridos (dict ou list)
            
        Returns:
            dict: Retorno padronizado com resultado da operação
        """
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}][INSERT] Inserindo dados na tabela '{tabela}'"
                )
            
            # Converte para lista se necessário
            if isinstance(dados, dict):
                dados = [dados]
            
            if not dados:
                return self._formatar_retorno(
                    sucesso=False,
                    operacao="INSERT",
                    tabela=tabela,
                    mensagem="Nenhum dado fornecido",
                    erro="Lista de dados vazia",
                )
            
            # Delega para método interno específico por tabela
            if tabela == "velas":
                resultado = self._inserir_velas(dados)
            elif tabela == "telemetria_plugins":
                resultado = self._inserir_telemetria(dados)
            elif tabela == "schema_versoes":
                resultado = self._inserir_generico(tabela, dados)
            else:
                resultado = self._inserir_generico(tabela, dados)
            
            if resultado["sucesso"]:
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}][INSERT] {resultado['linhas_afetadas']} registro(s) "
                        f"inserido(s) na tabela '{tabela}'"
                    )
            else:
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}][INSERT] Erro ao inserir na tabela '{tabela}': "
                        f"{resultado.get('erro', 'Erro desconhecido')}"
                    )
            
            return resultado
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][INSERT] Exceção ao inserir em '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="INSERT",
                tabela=tabela,
                erro=str(e),
            )
    
    def consultar(
        self,
        tabela: str,
        filtros: Optional[Dict[str, Any]] = None,
        campos: Optional[List[str]] = None,
        limite: Optional[int] = None,
        ordem: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Consulta dados da tabela especificada.
        
        Método público para consulta de dados.
        
        Args:
            tabela: Nome da tabela
            filtros: Dicionário com condições WHERE (ex: {"ativo": "BTCUSDT"})
            campos: Lista de campos a retornar (None = todos)
            limite: Número máximo de registros a retornar
            ordem: Campo para ordenação (ex: "open_time DESC")
            
        Returns:
            dict: Retorno padronizado com dados consultados
        """
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}][SELECT] Consultando tabela '{tabela}'"
                )
            
            resultado = self._consultar(tabela, filtros, campos, limite, ordem)
            
            if resultado["sucesso"]:
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}][SELECT] {resultado['linhas_afetadas']} registro(s) "
                        f"encontrado(s) na tabela '{tabela}'"
                    )
            else:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}][SELECT] Erro ao consultar '{tabela}': "
                        f"{resultado.get('erro', 'Erro desconhecido')}"
                    )
            
            return resultado
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][SELECT] Exceção ao consultar '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="SELECT",
                tabela=tabela,
                erro=str(e),
            )
    
    def atualizar(
        self,
        tabela: str,
        filtros: Dict[str, Any],
        dados: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Atualiza dados na tabela especificada.
        
        Método público para atualização de dados.
        
        Args:
            tabela: Nome da tabela
            filtros: Dicionário com condições WHERE (ex: {"ativo": "BTCUSDT"})
            dados: Dicionário com campos a atualizar (ex: {"volume": 1000})
            
        Returns:
            dict: Retorno padronizado com resultado da operação
        """
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}][UPDATE] Atualizando tabela '{tabela}'"
                )
            
            resultado = self._atualizar(tabela, filtros, dados)
            
            if resultado["sucesso"]:
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}][UPDATE] {resultado['linhas_afetadas']} registro(s) "
                        f"atualizado(s) na tabela '{tabela}'"
                    )
            else:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}][UPDATE] Erro ao atualizar '{tabela}': "
                        f"{resultado.get('erro', 'Erro desconhecido')}"
                    )
            
            return resultado
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][UPDATE] Exceção ao atualizar '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="UPDATE",
                tabela=tabela,
                erro=str(e),
            )
    
    def deletar(
        self,
        tabela: str,
        filtros: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Deleta dados da tabela especificada.
        
        Método público para exclusão de dados.
        
        Args:
            tabela: Nome da tabela
            filtros: Dicionário com condições WHERE (ex: {"ativo": "BTCUSDT"})
            
        Returns:
            dict: Retorno padronizado com resultado da operação
        """
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}][DELETE] Deletando da tabela '{tabela}'"
                )
            
            resultado = self._deletar(tabela, filtros)
            
            if resultado["sucesso"]:
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}][DELETE] {resultado['linhas_afetadas']} registro(s) "
                        f"deletado(s) da tabela '{tabela}'"
                    )
            else:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}][DELETE] Erro ao deletar de '{tabela}': "
                        f"{resultado.get('erro', 'Erro desconhecido')}"
                    )
            
            return resultado
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][DELETE] Exceção ao deletar de '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="DELETE",
                tabela=tabela,
                erro=str(e),
            )
    
    # ============================================================
    # MÉTODOS INTERNOS CRUD (COM UNDERSCORE)
    # ============================================================
    
    def _inserir_velas(self, velas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Insere velas na tabela usando upsert para evitar duplicatas.
        
        Conforme instrucao-velas.md:
        - Se open_time NÃO existe no banco → INSERT
        - Se existe, mas close/volume mudou → UPDATE (vela em formação)
        - Senão → ignora
        
        Args:
            velas: Lista de velas a serem inseridas/atualizadas
            
        Returns:
            dict: Retorno padronizado
        """
        if not velas:
            return self._formatar_retorno(
                sucesso=True,
                operacao="INSERT",
                tabela="velas",
                mensagem="Nenhuma vela para inserir",
            )
        
        conn = None
        try:
            conn = self._obter_conexao()
            if not conn:
                return self._formatar_retorno(
                    sucesso=False,
                    operacao="INSERT",
                    tabela="velas",
                    erro="Não foi possível obter conexão",
                )
            
            cursor = conn.cursor()
            
            # Query de upsert conforme instrucao-velas.md
            # Inclui campo exchange para suporte multi-exchange
            # Inclui campo testnet para distinguir testnet/mainnet
            upsert_query = """
            INSERT INTO velas (
                exchange, ativo, timeframe, open_time, close_time,
                open, high, low, close, volume, fechada, testnet
            ) VALUES %s
            ON CONFLICT (exchange, ativo, timeframe, open_time, testnet) 
            DO UPDATE SET
                close_time = EXCLUDED.close_time,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                fechada = EXCLUDED.fechada,
                atualizado_em = NOW()
            WHERE velas.close != EXCLUDED.close 
               OR velas.volume != EXCLUDED.volume;
            """
            
            # Prepara dados para inserção
            valores = []
            for vela in velas:
                # Converte timestamp para datetime (UTC)
                open_time = datetime.utcfromtimestamp(vela["timestamp"] / 1000)
                
                # Calcula close_time baseado no timeframe
                timeframe_minutes = {
                    "15m": 15,
                    "1h": 60,
                    "4h": 240,
                }.get(vela.get("timeframe", "15m"), 15)
                
                # Adiciona minutos ao open_time para obter close_time
                close_time = open_time + timedelta(minutes=timeframe_minutes)
                
                valores.append((
                    vela.get("exchange", "bybit"),  # Campo exchange (padrão: bybit)
                    vela["ativo"],
                    vela["timeframe"],
                    open_time,
                    close_time,
                    vela["open"],
                    vela["high"],
                    vela["low"],
                    vela["close"],
                    vela["volume"],
                    vela.get("fechada", True),
                    vela.get("testnet", False),  # Campo testnet (padrão: False/mainnet)
                ))
            
            # Executa upsert em lote
            execute_values(
                cursor,
                upsert_query,
                valores,
                template=None,
                page_size=100,
            )
            
            linhas_afetadas = cursor.rowcount
            conn.commit()
            cursor.close()
            self._devolver_conexao(conn)
            
            return self._formatar_retorno(
                sucesso=True,
                operacao="INSERT",
                tabela="velas",
                dados=velas,
                mensagem=f"{linhas_afetadas} vela(s) inserida(s)/atualizada(s)",
                linhas_afetadas=linhas_afetadas,
            )
            
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][INSERT] Erro ao inserir velas: {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="INSERT",
                tabela="velas",
                erro=str(e),
            )
        except Exception as e:
            if conn:
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][INSERT] Erro inesperado ao inserir velas: {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="INSERT",
                tabela="velas",
                erro=str(e),
            )
    
    def _inserir_telemetria(self, dados: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Insere dados de telemetria na tabela telemetria_plugins.
        
        Args:
            dados: Lista de dados de telemetria
            
        Returns:
            dict: Retorno padronizado
        """
        if not dados:
            return self._formatar_retorno(
                sucesso=True,
                operacao="INSERT",
                tabela="telemetria_plugins",
                mensagem="Nenhum dado de telemetria para inserir",
            )
        
        conn = None
        try:
            conn = self._obter_conexao()
            if not conn:
                return self._formatar_retorno(
                    sucesso=False,
                    operacao="INSERT",
                    tabela="telemetria_plugins",
                    erro="Não foi possível obter conexão",
                )
            
            cursor = conn.cursor()
            
            # Query de inserção
            insert_query = """
            INSERT INTO telemetria_plugins (
                plugin, timestamp, total_execucoes, execucoes_sucesso,
                execucoes_erro, falhas_consecutivas, tempo_medio,
                tempo_minimo, tempo_maximo, taxa_sucesso,
                ultima_execucao, ultimo_status, nivel_gravidade
            ) VALUES %s
            """
            
            # Prepara dados para inserção
            valores = []
            for tel in dados:
                ultima_exec = None
                if tel.get("ultima_execucao"):
                    if isinstance(tel["ultima_execucao"], str):
                        ultima_exec = datetime.fromisoformat(tel["ultima_execucao"])
                    else:
                        ultima_exec = tel["ultima_execucao"]
                
                valores.append((
                    tel.get("plugin", ""),
                    datetime.fromisoformat(tel.get("timestamp", datetime.now().isoformat())),
                    tel.get("total_execucoes", 0),
                    tel.get("execucoes_sucesso", 0),
                    tel.get("execucoes_erro", 0),
                    tel.get("falhas_consecutivas", 0),
                    tel.get("tempo_medio", 0.0),
                    tel.get("tempo_minimo", 0.0),
                    tel.get("tempo_maximo", 0.0),
                    tel.get("taxa_sucesso", 0.0),
                    ultima_exec,
                    tel.get("ultimo_status"),
                    tel.get("nivel_gravidade", "info"),
                ))
            
            # Executa inserção em lote
            execute_values(
                cursor,
                insert_query,
                valores,
                template=None,
                page_size=100,
            )
            
            linhas_afetadas = cursor.rowcount
            conn.commit()
            cursor.close()
            self._devolver_conexao(conn)
            
            return self._formatar_retorno(
                sucesso=True,
                operacao="INSERT",
                tabela="telemetria_plugins",
                dados=dados,
                mensagem=f"{linhas_afetadas} registro(s) de telemetria inserido(s)",
                linhas_afetadas=linhas_afetadas,
            )
            
        except Exception as e:
            if conn:
                if hasattr(conn, 'rollback'):
                    conn.rollback()
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][INSERT] Erro ao inserir telemetria: {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="INSERT",
                tabela="telemetria_plugins",
                erro=str(e),
            )
    
    def _inserir_generico(self, tabela: str, dados: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Insere dados em tabela genérica usando INSERT simples.
        
        Args:
            tabela: Nome da tabela
            dados: Lista de dicionários com dados a inserir
            
        Returns:
            dict: Retorno padronizado
        """
        if not dados:
            return self._formatar_retorno(
                sucesso=True,
                operacao="INSERT",
                tabela=tabela,
                mensagem="Nenhum dado para inserir",
            )
        
        conn = None
        try:
            conn = self._obter_conexao()
            if not conn:
                return self._formatar_retorno(
                    sucesso=False,
                    operacao="INSERT",
                    tabela=tabela,
                    erro="Não foi possível obter conexão",
                )
            
            cursor = conn.cursor()
            
            # Obtém colunas do primeiro registro
            primeiro_registro = dados[0]
            colunas = list(primeiro_registro.keys())
            
            # Valida que todos os registros têm as mesmas colunas
            for registro in dados:
                if set(registro.keys()) != set(colunas):
                    return self._formatar_retorno(
                        sucesso=False,
                        operacao="INSERT",
                        tabela=tabela,
                        erro="Registros com colunas diferentes",
                    )
            
            # Monta query de inserção (usando sql.Identifier para segurança)
            colunas_str = ", ".join([sql.Identifier(col).as_string(conn) for col in colunas])
            placeholders = ", ".join(["%s"] * len(colunas))
            tabela_ident = sql.Identifier(tabela).as_string(conn)
            insert_query = f"""
            INSERT INTO {tabela_ident} ({colunas_str})
            VALUES ({placeholders})
            """
            
            # Prepara valores
            valores = []
            for registro in dados:
                valores.append(tuple(registro.values()))
            
            # Executa inserção em lote
            execute_values(
                cursor,
                insert_query,
                valores,
                template=None,
                page_size=100,
            )
            
            linhas_afetadas = cursor.rowcount
            conn.commit()
            cursor.close()
            self._devolver_conexao(conn)
            
            return self._formatar_retorno(
                sucesso=True,
                operacao="INSERT",
                tabela=tabela,
                dados=dados,
                mensagem=f"{linhas_afetadas} registro(s) inserido(s)",
                linhas_afetadas=linhas_afetadas,
            )
            
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][INSERT] Erro ao inserir em '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="INSERT",
                tabela=tabela,
                erro=str(e),
            )
        except Exception as e:
            if conn:
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][INSERT] Erro inesperado ao inserir em '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="INSERT",
                tabela=tabela,
                erro=str(e),
            )
    
    def _consultar(
        self,
        tabela: str,
        filtros: Optional[Dict[str, Any]] = None,
        campos: Optional[List[str]] = None,
        limite: Optional[int] = None,
        ordem: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Consulta dados da tabela especificada.
        
        Args:
            tabela: Nome da tabela
            filtros: Dicionário com condições WHERE
            campos: Lista de campos a retornar (None = todos)
            limite: Número máximo de registros
            ordem: Campo para ordenação
            
        Returns:
            dict: Retorno padronizado com dados consultados
        """
        conn = None
        try:
            conn = self._obter_conexao()
            if not conn:
                return self._formatar_retorno(
                    sucesso=False,
                    operacao="SELECT",
                    tabela=tabela,
                    erro="Não foi possível obter conexão",
                )
            
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Monta query SELECT (usando sql.Identifier para segurança)
            if campos:
                campos_str = ", ".join([sql.Identifier(campo).as_string(conn) for campo in campos])
            else:
                campos_str = "*"
            tabela_ident = sql.Identifier(tabela).as_string(conn)
            query = f"SELECT {campos_str} FROM {tabela_ident}"
            
            # Adiciona WHERE se houver filtros
            params = []
            if filtros:
                condicoes = []
                for campo, valor in filtros.items():
                    condicoes.append(f"{campo} = %s")
                    params.append(valor)
                query += " WHERE " + " AND ".join(condicoes)
            
            # Adiciona ORDER BY se especificado
            if ordem:
                query += f" ORDER BY {ordem}"
            
            # Adiciona LIMIT se especificado
            if limite:
                query += f" LIMIT {limite}"
            
            # Executa query
            cursor.execute(query, params)
            resultados = cursor.fetchall()
            
            # Converte RealDictRow para dict
            dados = [dict(row) for row in resultados]
            
            cursor.close()
            self._devolver_conexao(conn)
            
            return self._formatar_retorno(
                sucesso=True,
                operacao="SELECT",
                tabela=tabela,
                dados=dados,
                mensagem=f"{len(dados)} registro(s) encontrado(s)",
                linhas_afetadas=len(dados),
            )
            
        except psycopg2.Error as e:
            if conn:
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][SELECT] Erro ao consultar '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="SELECT",
                tabela=tabela,
                erro=str(e),
            )
        except Exception as e:
            if conn:
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][SELECT] Erro inesperado ao consultar '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="SELECT",
                tabela=tabela,
                erro=str(e),
            )
    
    def _atualizar(
        self,
        tabela: str,
        filtros: Dict[str, Any],
        dados: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Atualiza dados na tabela especificada.
        
        Args:
            tabela: Nome da tabela
            filtros: Dicionário com condições WHERE
            dados: Dicionário com campos a atualizar
            
        Returns:
            dict: Retorno padronizado
        """
        if not filtros:
            return self._formatar_retorno(
                sucesso=False,
                operacao="UPDATE",
                tabela=tabela,
                erro="Filtros não fornecidos (atualização sem filtros é perigosa)",
            )
        
        if not dados:
            return self._formatar_retorno(
                sucesso=False,
                operacao="UPDATE",
                tabela=tabela,
                erro="Nenhum dado para atualizar",
            )
        
        conn = None
        try:
            conn = self._obter_conexao()
            if not conn:
                return self._formatar_retorno(
                    sucesso=False,
                    operacao="UPDATE",
                    tabela=tabela,
                    erro="Não foi possível obter conexão",
                )
            
            cursor = conn.cursor()
            
            # Monta query UPDATE (usando sql.Identifier para segurança)
            sets = []
            params = []
            
            for campo, valor in dados.items():
                campo_ident = sql.Identifier(campo).as_string(conn)
                sets.append(f"{campo_ident} = %s")
                params.append(valor)
            
            # Adiciona WHERE
            condicoes = []
            for campo, valor in filtros.items():
                campo_ident = sql.Identifier(campo).as_string(conn)
                condicoes.append(f"{campo_ident} = %s")
                params.append(valor)
            
            tabela_ident = sql.Identifier(tabela).as_string(conn)
            query = f"""
            UPDATE {tabela_ident}
            SET {', '.join(sets)}, atualizado_em = NOW()
            WHERE {' AND '.join(condicoes)}
            """
            
            # Executa UPDATE
            cursor.execute(query, params)
            linhas_afetadas = cursor.rowcount
            
            conn.commit()
            cursor.close()
            self._devolver_conexao(conn)
            
            return self._formatar_retorno(
                sucesso=True,
                operacao="UPDATE",
                tabela=tabela,
                dados=dados,
                mensagem=f"{linhas_afetadas} registro(s) atualizado(s)",
                linhas_afetadas=linhas_afetadas,
            )
            
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][UPDATE] Erro ao atualizar '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="UPDATE",
                tabela=tabela,
                erro=str(e),
            )
        except Exception as e:
            if conn:
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][UPDATE] Erro inesperado ao atualizar '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="UPDATE",
                tabela=tabela,
                erro=str(e),
            )
    
    def _deletar(
        self,
        tabela: str,
        filtros: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Deleta dados da tabela especificada.
        
        Args:
            tabela: Nome da tabela
            filtros: Dicionário com condições WHERE
            
        Returns:
            dict: Retorno padronizado
        """
        if not filtros:
            return self._formatar_retorno(
                sucesso=False,
                operacao="DELETE",
                tabela=tabela,
                erro="Filtros não fornecidos (deleção sem filtros é perigosa)",
            )
        
        conn = None
        try:
            conn = self._obter_conexao()
            if not conn:
                return self._formatar_retorno(
                    sucesso=False,
                    operacao="DELETE",
                    tabela=tabela,
                    erro="Não foi possível obter conexão",
                )
            
            cursor = conn.cursor()
            
            # Monta query DELETE (usando sql.Identifier para segurança)
            condicoes = []
            params = []
            
            for campo, valor in filtros.items():
                campo_ident = sql.Identifier(campo).as_string(conn)
                condicoes.append(f"{campo_ident} = %s")
                params.append(valor)
            
            tabela_ident = sql.Identifier(tabela).as_string(conn)
            query = f"""
            DELETE FROM {tabela_ident}
            WHERE {' AND '.join(condicoes)}
            """
            
            # Executa DELETE
            cursor.execute(query, params)
            linhas_afetadas = cursor.rowcount
            
            conn.commit()
            cursor.close()
            self._devolver_conexao(conn)
            
            return self._formatar_retorno(
                sucesso=True,
                operacao="DELETE",
                tabela=tabela,
                mensagem=f"{linhas_afetadas} registro(s) deletado(s)",
                linhas_afetadas=linhas_afetadas,
            )
            
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][DELETE] Erro ao deletar de '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="DELETE",
                tabela=tabela,
                erro=str(e),
            )
        except Exception as e:
            if conn:
                self._devolver_conexao(conn)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}][DELETE] Erro inesperado ao deletar de '{tabela}': {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="DELETE",
                tabela=tabela,
                erro=str(e),
            )
    
    # ============================================================
    # MÉTODOS AUXILIARES
    # ============================================================
    
    def _registrar_versao_schema(self, tabela: str, versao: str, descricao: str, conn=None):
        """
        Registra versão do schema no histórico.
        
        Útil quando migrar tabelas para rastrear mudanças.
        
        Args:
            tabela: Nome da tabela
            versao: Versão do schema (ex: v1.2.0)
            descricao: Descrição da mudança
            conn: Conexão do banco (opcional, cria nova se não fornecido)
        """
        try:
            usar_conn_externa = conn is not None
            if not conn:
                conn = self._obter_conexao()
                if not conn:
                    return False
            
            cursor = conn.cursor()
            
            # Verifica se versão já existe
            cursor.execute(
                "SELECT id FROM schema_versoes WHERE tabela = %s AND versao = %s",
                (tabela, versao)
            )
            if cursor.fetchone():
                # Versão já registrada
                cursor.close()
                if not usar_conn_externa:
                    conn.commit()
                    self._devolver_conexao(conn)
                return True
            
            # Insere nova versão
            cursor.execute(
                """
                INSERT INTO schema_versoes (tabela, versao, descricao, aplicado_por)
                VALUES (%s, %s, %s, %s)
                """,
                (tabela, versao, descricao, self.PLUGIN_NAME)
            )
            
            if not usar_conn_externa:
                conn.commit()
                cursor.close()
                self._devolver_conexao(conn)
            else:
                cursor.close()
            
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Versão de schema registrada: {tabela} v{versao}"
                )
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao registrar versão de schema: {e}",
                    exc_info=True,
                )
            return False
    
    def atualizar_view_materializada(self) -> Dict[str, Any]:
        """
        Atualiza view materializada para médias e indicadores agregados.
        
        Acelera análises da IA sem recalcular tudo.
        
        Returns:
            dict: Retorno padronizado
        """
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Atualizando view materializada mv_velas_agregadas"
                )
            
            conn = self._obter_conexao()
            if not conn:
                return self._formatar_retorno(
                    sucesso=False,
                    operacao="REFRESH",
                    tabela="mv_velas_agregadas",
                    erro="Não foi possível obter conexão",
                )
            
            cursor = conn.cursor()
            
            # Atualiza view materializada
            cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_velas_agregadas")
            
            conn.commit()
            cursor.close()
            self._devolver_conexao(conn)
            
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] View materializada atualizada com sucesso"
                )
            
            return self._formatar_retorno(
                sucesso=True,
                operacao="REFRESH",
                tabela="mv_velas_agregadas",
                mensagem="View materializada atualizada com sucesso",
            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao atualizar view materializada: {e}",
                    exc_info=True,
                )
            return self._formatar_retorno(
                sucesso=False,
                operacao="REFRESH",
                tabela="mv_velas_agregadas",
                erro=str(e),
            )
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executa verificação de conexão e saúde do banco.
        
        Este método é chamado pelo GerenciadorPlugins durante o ciclo de execução.
        Verifica conexão e retorna status do banco.
        
        Args:
            dados_entrada: Opcional, não usado neste plugin
            
        Returns:
            dict: Status da conexão e saúde do banco
        """
        try:
            # Verifica se pool está inicializado
            if not self.connection_pool:
                return {
                    "status": StatusExecucao.ERRO.value,
                    "mensagem": "Pool de conexões não inicializado",
                    "plugin": self.PLUGIN_NAME,
                }
            
            # Testa conexão
            conn = self._obter_conexao()
            if not conn:
                return {
                    "status": StatusExecucao.ERRO.value,
                    "mensagem": "Não foi possível obter conexão do pool",
                    "plugin": self.PLUGIN_NAME,
                }
            
            # Testa com query simples
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            self._devolver_conexao(conn)
            
            return {
                "status": StatusExecucao.OK.value,
                "mensagem": "Banco de dados operacional",
                "plugin": self.PLUGIN_NAME,
                "host": self.db_host,
                "database": self.db_name,
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao verificar conexão: {e}",
                    exc_info=True,
                )
            return {
                "status": StatusExecucao.ERRO.value,
                "mensagem": str(e),
                "plugin": self.PLUGIN_NAME,
            }
    
    @property
    def plugin_tabelas(self) -> Dict[str, Dict[str, Any]]:
        """
        Define as tabelas que este plugin gerencia.
        
        Returns:
            dict: Definições de tabelas
        """
        return {
            "velas": {
                "descricao": "Histórico de velas OHLCV por timeframe",
                "modo_acesso": "own",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "exchange": "VARCHAR(20) DEFAULT 'bybit'",
                    "ativo": "VARCHAR(20) NOT NULL",
                    "timeframe": "VARCHAR(5) NOT NULL",
                    "open_time": "TIMESTAMP NOT NULL",
                    "close_time": "TIMESTAMP NOT NULL",
                    "open": "NUMERIC(20,8) NOT NULL",
                    "high": "NUMERIC(20,8) NOT NULL",
                    "low": "NUMERIC(20,8) NOT NULL",
                    "close": "NUMERIC(20,8) NOT NULL",
                    "volume": "NUMERIC(20,8) NOT NULL",
                    "fechada": "BOOLEAN DEFAULT TRUE",
                    "testnet": "BOOLEAN DEFAULT FALSE",
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                    "atualizado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
            "telemetria_plugins": {
                "descricao": "Telemetria de plugins para estatísticas de aprendizado para IA",
                "modo_acesso": "shared",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "plugin": "VARCHAR(100) NOT NULL",
                    "timestamp": "TIMESTAMP NOT NULL DEFAULT NOW()",
                    "total_execucoes": "INTEGER DEFAULT 0",
                    "execucoes_sucesso": "INTEGER DEFAULT 0",
                    "execucoes_erro": "INTEGER DEFAULT 0",
                    "falhas_consecutivas": "INTEGER DEFAULT 0",
                    "tempo_medio": "NUMERIC(10,6) DEFAULT 0.0",
                    "tempo_minimo": "NUMERIC(10,6) DEFAULT 0.0",
                    "tempo_maximo": "NUMERIC(10,6) DEFAULT 0.0",
                    "taxa_sucesso": "NUMERIC(5,4) DEFAULT 0.0",
                    "ultima_execucao": "TIMESTAMP",
                    "ultimo_status": "VARCHAR(20)",
                    "nivel_gravidade": "VARCHAR(20) DEFAULT 'info'",
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
            "schema_versoes": {
                "descricao": "Histórico de versões de schema (útil quando migrar tabelas)",
                "modo_acesso": "shared",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "tabela": "VARCHAR(100) NOT NULL",
                    "versao": "VARCHAR(20) NOT NULL",
                    "descricao": "TEXT",
                    "migracao_sql": "TEXT",
                    "aplicado_em": "TIMESTAMP DEFAULT NOW()",
                    "aplicado_por": "VARCHAR(100)",
                }
            },
            "padroes_detectados": {
                "descricao": "Padrões de trading detectados com telemetria completa",
                "modo_acesso": "shared",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "symbol": "VARCHAR(20) NOT NULL",
                    "timeframe": "VARCHAR(5) NOT NULL",
                    "open_time": "TIMESTAMP NOT NULL",
                    "tipo_padrao": "VARCHAR(50) NOT NULL",
                    "direcao": "VARCHAR(10) NOT NULL",
                    "score": "NUMERIC(5,4) NOT NULL",
                    "confidence": "NUMERIC(5,4) NOT NULL",
                    "regime": "VARCHAR(20) NOT NULL",
                    "suggested_sl": "NUMERIC(20,8)",
                    "suggested_tp": "NUMERIC(20,8)",
                    "final_score": "NUMERIC(5,4) NOT NULL",
                    "meta": "JSONB",
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
            "padroes_metricas": {
                "descricao": "Métricas de performance por padrão de trading",
                "modo_acesso": "shared",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "tipo_padrao": "VARCHAR(50) NOT NULL",
                    "symbol": "VARCHAR(20)",
                    "timeframe": "VARCHAR(5)",
                    "periodo_inicio": "TIMESTAMP NOT NULL",
                    "periodo_fim": "TIMESTAMP NOT NULL",
                    "frequency": "NUMERIC(10,4) NOT NULL",
                    "precision": "NUMERIC(5,4)",
                    "recall": "NUMERIC(5,4)",
                    "expectancy": "NUMERIC(10,4)",
                    "sharpe_condicional": "NUMERIC(10,4)",
                    "drawdown_condicional": "NUMERIC(10,4)",
                    "winrate": "NUMERIC(5,4)",
                    "avg_rr": "NUMERIC(5,4)",
                    "total_trades": "INTEGER DEFAULT 0",
                    "trades_win": "INTEGER DEFAULT 0",
                    "trades_loss": "INTEGER DEFAULT 0",
                    "tipo_validacao": "VARCHAR(20)",
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
            "padroes_confidence": {
                "descricao": "Histórico de confidence decay por padrão",
                "modo_acesso": "shared",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "tipo_padrao": "VARCHAR(50) NOT NULL",
                    "symbol": "VARCHAR(20)",
                    "timeframe": "VARCHAR(5)",
                    "data_ultimo_win": "TIMESTAMP",
                    "days_since_last_win": "INTEGER",
                    "base_score": "NUMERIC(5,4) NOT NULL",
                    "confidence_score": "NUMERIC(5,4) NOT NULL",
                    "em_quarentena": "BOOLEAN DEFAULT FALSE",
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
        }
    
    def _finalizar_interno(self) -> bool:
        """
        Finaliza conexão com PostgreSQL.
        
        Returns:
            bool: True se finalizado com sucesso
        """
        try:
            if self.connection_pool:
                self.connection_pool.closeall()
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Pool de conexões fechado"
                    )
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao finalizar: {e}",
                    exc_info=True,
                )
            return False
