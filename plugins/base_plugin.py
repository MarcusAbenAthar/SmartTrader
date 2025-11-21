"""
Classe base para todos os plugins do sistema.

Define o ciclo de vida padrão e interface comum para plugins.
Todos os plugins devem herdar desta classe.

__institucional__ = "Smart_Trader Core PluginBase - Compatível com sistema 6/8 Unificado"

Melhorias implementadas:
- Controle de execução com método rodar() (wrapper de executar())
- Hooks opcionais: antes_executar() e apos_executar()
- Context manager (__enter__ e __exit__) para uso com 'with'
- Tipagem explícita com Protocols para gerenciadores
- Verificação de schema antes de persistir dados
- Decorator institucional execucao_segura() para execução à prova de falhas
- Telemetry interna (contadores, métricas de performance)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Protocol, runtime_checkable, Callable
from datetime import datetime
from functools import wraps
from enum import Enum
import logging


# ============================================================
# ENUM PARA STATUS DE EXECUÇÃO
# ============================================================

class StatusExecucao(Enum):
    """
    Enum para status de execução de plugins.
    
    Melhora legibilidade e evita strings soltas no código.
    Útil para IA classificar e analisar resultados de execução.
    """
    OK = "ok"
    ERRO = "erro"
    AVISO = "aviso"
    PENDENTE = "pendente"
    CANCELADO = "cancelado"
    
    def __str__(self):
        return self.value


# ============================================================
# NÍVEIS DE GRAVIDADE E AÇÕES AUTOMÁTICAS
# ============================================================

class NivelGravidade(Enum):
    """
    Níveis de gravidade para problemas detectados em plugins.
    
    Cada nível tem uma ação automática associada que o sistema
    pode executar para tentar resolver o problema.
    """
    INFO = "info"  # Informativo, sem ação
    WARNING = "warning"  # Aviso, log apenas
    ERROR = "error"  # Erro, tenta recuperar automaticamente
    CRITICAL = "critical"  # Crítico, reinicializa plugin
    
    def acao_automatica(self) -> str:
        """
        Retorna a ação automática para este nível de gravidade.
        
        Returns:
            str: Descrição da ação automática
        """
        acoes = {
            "info": "Nenhuma ação",
            "warning": "Log de aviso",
            "error": "Tentativa de recuperação automática",
            "critical": "Reinicialização do plugin",
        }
        return acoes.get(self.value, "Nenhuma ação")


# ============================================================
# PROTOCOLS PARA TIPAGEM EXPLÍCITA DOS GERENCIADORES
# ============================================================

@runtime_checkable
class GerenciadorLogProtocol(Protocol):
    """
    Protocol que define a interface mínima esperada do GerenciadorLog.
    
    Permite autocompletar e validação estática sem acoplamento direto.
    """
    
    def get_logger(
        self,
        nome: str,
        tipo_log: str = "rastreamento",
        nivel: int = logging.INFO,
    ) -> logging.Logger:
        """
        Obtém ou cria um logger para o nome especificado.
        
        Args:
            nome: Nome do logger (geralmente PLUGIN_NAME)
            tipo_log: Tipo de log (bot, banco, dados, sinais, erros, rastreamento)
            nivel: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            
        Returns:
            logging.Logger: Logger configurado
        """
        ...


@runtime_checkable
class GerenciadorBancoProtocol(Protocol):
    """
    Protocol que define a interface mínima esperada do GerenciadorBanco.
    
    Permite autocompletar e validação estática sem acoplamento direto.
    """
    
    def persistir_dados(
        self, plugin: str, tabela: str, dados: Any
    ) -> bool:
        """
        Persiste dados via plugin BancoDados.
        
        Args:
            plugin: Nome do plugin que está solicitando a persistência
            tabela: Nome da tabela (deve estar declarada no schema)
            dados: Dados a serem persistidos
            
        Returns:
            bool: True se persistido com sucesso, False caso contrário.
        """
        ...


# ============================================================
# DECORATOR INSTITUCIONAL DE EXECUÇÃO SEGURA
# ============================================================

def execucao_segura(func: Callable) -> Callable:
    """
    Decorator institucional que garante execução segura usando context manager.
    
    Automaticamente inicializa e finaliza o plugin, garantindo limpeza mesmo em
    caso de exceção. Tornado padrão 100% à prova de falhas humanas.
    
    Uso:
        @execucao_segura
        def executar(self, dados):
            # Sua lógica aqui
            return resultado
    
    O decorator usa 'with self:' internamente para garantir:
    - Inicialização automática se necessário
    - Finalização automática mesmo em caso de exceção
    - Tratamento seguro de recursos
    
    Args:
        func: Método do plugin a ser decorado (geralmente executar())
        
    Returns:
        Callable: Função wrapper que executa com segurança
        
    Raises:
        RuntimeError: Se falhar ao inicializar o plugin
    """
    @wraps(func)
    def wrapper(self: 'Plugin', *args, **kwargs):
        # Usa context manager para garantir inicialização e finalização
        with self:
            return func(self, *args, **kwargs)
    
    return wrapper


# ============================================================
# CLASSE BASE PLUGIN
# ============================================================

# ============================================================
# ÁRVORE HIERÁRQUICA DOS TIPOS DE PLUGIN
# ============================================================

class TipoPlugin(Enum):
    """
    Enum que define a hierarquia de tipos de plugin no sistema.
    
    Útil para IA classificar e organizar módulos automaticamente.
    
    Hierarquia:
    - INDICADOR: Plugins que calculam indicadores técnicos (RSI, MACD, etc.)
    - GERENCIADOR: Gerenciadores do sistema (Log, Banco, Plugins, Bot)
    - CONEXAO: Plugins de conexão com APIs externas (Bybit, etc.)
    - DADOS: Plugins que processam dados brutos (velas, dados de mercado)
    - IA: Plugins de inteligência artificial (Llama, análise preditiva)
    - AUXILIAR: Plugins auxiliares (utilitários, helpers)
    """
    INDICADOR = "indicador"
    GERENCIADOR = "gerenciador"
    CONEXAO = "conexao"
    DADOS = "dados"
    IA = "ia"
    AUXILIAR = "auxiliar"
    
    def __str__(self):
        return self.value


class Plugin(ABC):
    """
    Classe base abstrata para todos os plugins do sistema.
    
    Define o ciclo de vida completo:
    1. Inicialização: __init__ -> inicializar()
    2. Execução: executar() (pode usar @execucao_segura)
    3. Persistência: via GerenciadorBanco
    4. Finalização: finalizar()
    
    Attributes:
        PLUGIN_NAME (str): Nome único do plugin (obrigatório)
        plugin_versao (str): Versão do plugin no formato SemVer (vX.Y.Z)
        plugin_schema_versao (str): Versão do schema do banco (vX.Y.Z)
        plugin_tipo (TipoPlugin): Tipo do plugin na hierarquia
        plugin_metadados (dict): Metadados padrão (autor, data, dependências)
        dados_completos (dict): Estrutura {"crus": {}, "analisados": {}}
        logger: Instância do logger específico do plugin
        __institucional__ (str): Identificador institucional para introspecção
    """
    
    # Identificador institucional para introspecção pelo GerenciadorPlugins
    __institucional__ = "Smart_Trader Core PluginBase - Compatível com sistema 6/8 Unificado"

    PLUGIN_NAME: str = "PluginBase"
    plugin_versao: str = "v1.0.0"
    plugin_schema_versao: str = "v1.0.0"
    plugin_tipo: TipoPlugin = TipoPlugin.AUXILIAR

    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLogProtocol] = None,
        gerenciador_banco: Optional[GerenciadorBancoProtocol] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o plugin base.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog (injetada pelo GerenciadorPlugins)
            gerenciador_banco: Instância do GerenciadorBanco (injetada pelo GerenciadorPlugins)
            config: Configuração do plugin (opcional)
        """
        self.PLUGIN_NAME = self.__class__.__name__
        self.gerenciador_log: Optional[GerenciadorLogProtocol] = gerenciador_log
        self.gerenciador_banco: Optional[GerenciadorBancoProtocol] = gerenciador_banco
        self.config: Dict[str, Any] = config or {}
        
        # Estrutura de dados padronizada
        self.dados_completos: Dict[str, Any] = {
            "crus": {},
            "analisados": {},
        }
        
        # Estado interno
        self._inicializado: bool = False
        self._em_execucao: bool = False
        self._cancelamento_solicitado: bool = False  # Flag para cancelamento gracioso
        self._timestamp_inicio: Optional[datetime] = None
        self._timestamp_execucao: Optional[datetime] = None
        
        # Logger (será inicializado no inicializar())
        self.logger: Optional[logging.Logger] = None
        
        # Metadados padrão do plugin (útil para IA classificar módulos)
        self.plugin_metadados: Dict[str, Any] = {
            "autor": self.config.get("plugin_autor", "SmartTrader Team"),
            "data_criacao": self.config.get("plugin_data_criacao", datetime.now().isoformat()),
            "data_atualizacao": datetime.now().isoformat(),
            "dependencias": self.config.get("plugin_dependencias", []),
            "tipo": self.plugin_tipo.value if hasattr(self, 'plugin_tipo') else TipoPlugin.AUXILIAR.value,
            "descricao": self.config.get("plugin_descricao", ""),
        }
        
        # Tolerância de erro temporal para monitoramento (em segundos)
        # Útil para IA avaliar sincronização entre plugins
        self.monitoramento_delay_maximo: float = self.config.get("monitoramento_delay_maximo", 0.3)
        
        # Nível de gravidade atual (usado para ações automáticas)
        self._nivel_gravidade_atual: NivelGravidade = NivelGravidade.INFO
        
        # ============================================================
        # TELEMETRIA INTERNA (para GerenciadorBot tomar decisões)
        # ============================================================
        self._telemetria: Dict[str, Any] = {
            "total_execucoes": 0,
            "execucoes_sucesso": 0,
            "execucoes_erro": 0,
            "falhas_consecutivas": 0,
            "tempo_total": 0.0,
            "tempo_medio": 0.0,
            "tempo_minimo": float('inf'),
            "tempo_maximo": 0.0,
            "ultima_execucao": None,  # datetime da última execução
            "ultimo_status": None,  # "ok" ou "erro"
            "primeira_execucao": None,  # datetime da primeira execução
        }

    def inicializar(self) -> bool:
        """
        Inicializa o plugin.
        
        Este método deve ser chamado após a injeção de dependências.
        Inicializa o logger e prepara estruturas internas.
        Nenhum processo ou thread deve ser iniciado aqui.
        
        Returns:
            bool: True se inicializado com sucesso, False caso contrário.
        """
        try:
            # Inicializa logger se disponível
            if self.gerenciador_log:
                # Determina tipo de log baseado no tipo de plugin
                tipo_log = "system"
                if self.plugin_tipo == TipoPlugin.INDICADOR:
                    tipo_log = "system"  # Indicadores usam system por padrão
                elif self.PLUGIN_NAME == "PluginBancoDados":
                    tipo_log = "banco"
                elif "Padroes" in self.PLUGIN_NAME:
                    tipo_log = "padroes"
                elif "Ia" in self.PLUGIN_NAME or "Llama" in self.PLUGIN_NAME:
                    tipo_log = "ia"
                
                self.logger = self.gerenciador_log.get_logger(self.PLUGIN_NAME, tipo_log)
            
            # Chama inicialização específica do plugin
            resultado = self._inicializar_interno()
            
            if resultado:
                self._inicializado = True
                self._timestamp_inicio = datetime.now()
                
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Plugin inicializado com sucesso (versão: {self.plugin_versao})"
                    )
            
            return resultado
        except Exception as e:
            if self.logger:
                self.logger.critical(
                    f"[{self.PLUGIN_NAME}] Erro ao inicializar plugin: {e}",
                    exc_info=True,
                )
            return False

    def _inicializar_interno(self) -> bool:
        """
        Método interno para inicialização específica do plugin.
        
        Sobrescreva este método em plugins filhos para adicionar lógica de inicialização.
        
        Returns:
            bool: True se inicializado com sucesso, False caso contrário.
        """
        return True

    @abstractmethod
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executa a lógica principal do plugin.
        
        Este método é chamado pelo GerenciadorPlugins durante o ciclo de execução.
        Deve processar dados, gerar análises e armazenar resultados em self.dados_completos.
        
        Nota: Para uso direto, prefira rodar() que gerencia estado e logs automaticamente.
        
        Para suporte assíncrono, use executar_async() quando disponível.
        
        Args:
            dados_entrada: Dados de entrada (de outros plugins ou APIs externas)
            
        Returns:
            dict: Resultado da execução com status e dados relevantes
        """
        pass
    
    async def executar_async(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Versão assíncrona do método executar().
        
        Suporte nativo para execução assíncrona (async/await).
        Útil quando threads forem substituídas por async workers.
        
        Por padrão, chama executar() de forma síncrona.
        Sobrescreva este método em plugins filhos para implementar lógica assíncrona.
        
        Args:
            dados_entrada: Dados de entrada (de outros plugins ou APIs externas)
            
        Returns:
            dict: Resultado da execução com status e dados relevantes
        """
        import asyncio
        # Executa método síncrono em thread pool para não bloquear
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.executar, dados_entrada)

    def antes_executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Hook executado ANTES do método executar().
        
        Permite preparação, validação ou transformação de dados antes da execução.
        Sobrescreva este método para adicionar lógica pré-execução sem modificar executar().
        
        Args:
            dados_entrada: Dados de entrada originais
            
        Returns:
            dict opcional: Dados modificados/preparados para executar()
                          Se retornar None, usa dados_entrada originais
        """
        return dados_entrada

    def apos_executar(
        self,
        resultado: Dict[str, Any],
        dados_entrada: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Hook executado APÓS o método executar().
        
        Permite pós-processamento, logging adicional ou validação dos resultados.
        Sobrescreva este método para adicionar lógica pós-execução sem modificar executar().
        
        Args:
            resultado: Resultado retornado por executar()
            dados_entrada: Dados de entrada originais
            
        Returns:
            dict: Resultado final (pode ser modificado ou o mesmo)
        """
        return resultado

    def rodar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Wrapper padronizado para executar() com gerenciamento automático de estado e logs.
        
        Gerencia automaticamente:
        - Flag _em_execucao
        - Timestamps de início/fim
        - Logs padronizados de início/fim
        - Tratamento de erros
        - Telemetria (métricas de performance e estabilidade)
        
        Este método deve ser usado ao invés de executar() diretamente quando possível.
        
        Nota: Para garantir execução 100% segura, você também pode usar o decorator
        @execucao_segura no método executar():
        
        ```python
        from plugins.base_plugin import execucao_segura
        
        class MeuPlugin(Plugin):
            @execucao_segura
            def executar(self, dados):
                # Sua lógica aqui - inicialização/finalização automáticas
                return resultado
        ```
        
        Args:
            dados_entrada: Dados de entrada (de outros plugins ou APIs externas)
            
        Returns:
            dict: Resultado da execução com status e dados relevantes
        """
        if not self._inicializado:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Plugin não inicializado. "
                    "Chame inicializar() antes de rodar()."
                )
            return {
                "status": "erro",
                "mensagem": "Plugin não inicializado",
                "plugin": self.PLUGIN_NAME,
            }

        if self._em_execucao:
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Tentativa de execução concorrente detectada"
                )
            return {
                "status": "erro",
                "mensagem": "Execução já em andamento",
                "plugin": self.PLUGIN_NAME,
            }

        # Marca como em execução
        self._em_execucao = True
        self._timestamp_execucao = datetime.now()
        
        if self.logger:
            self.logger.info(
                f"[{self.PLUGIN_NAME}] Iniciando execução..."
            )

        try:
            # Hook antes_executar()
            dados_processados = self.antes_executar(dados_entrada)
            if dados_processados is None:
                dados_processados = dados_entrada

            # Executa a lógica principal
            resultado = self.executar(dados_processados)

            # Hook apos_executar()
            resultado_final = self.apos_executar(resultado, dados_processados)

            # Calcula duração
            duracao = (datetime.now() - self._timestamp_execucao).total_seconds()
            status_str = resultado_final.get("status", "ok")
            
            # Usa enum para status
            try:
                status = StatusExecucao(status_str)
            except ValueError:
                status = StatusExecucao.OK if status_str == "ok" else StatusExecucao.ERRO
            
            # Verifica delay máximo de monitoramento
            if duracao > self.monitoramento_delay_maximo:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Delay de execução acima do máximo aceitável: "
                        f"{duracao:.3f}s > {self.monitoramento_delay_maximo:.3f}s"
                    )
            
            # Atualiza telemetria para sucesso
            self._atualizar_telemetria(status=status.value, duracao=duracao)

            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Execução concluída com status '{status}' "
                    f"(duração: {duracao:.2f}s)"
                )

            return resultado_final

        except Exception as e:
            duracao = (datetime.now() - self._timestamp_execucao).total_seconds() if self._timestamp_execucao else 0
            
            # Define nível de gravidade baseado no erro
            self._nivel_gravidade_atual = NivelGravidade.ERROR
            if "critical" in str(e).lower() or isinstance(e, SystemError):
                self._nivel_gravidade_atual = NivelGravidade.CRITICAL
            
            # Executa ação automática se necessário
            self._executar_acao_automatica()
            
            # Atualiza telemetria para erro
            self._atualizar_telemetria(status=StatusExecucao.ERRO.value, duracao=duracao)
            
            if self.logger:
                self.logger.critical(
                    f"[{self.PLUGIN_NAME}] Erro durante execução: {e} "
                    f"(duração até erro: {duracao:.2f}s)",
                    exc_info=True,
                )

            return {
                "status": "erro",
                "mensagem": str(e),
                "plugin": self.PLUGIN_NAME,
                "duracao_ate_erro": duracao,
            }

        finally:
            # Sempre libera a flag, mesmo em caso de erro
            self._em_execucao = False
            self._timestamp_execucao = None

    def _executar_acao_automatica(self):
        """
        Executa ação automática baseada no nível de gravidade atual.
        
        Ações:
        - INFO/WARNING: Nenhuma ação
        - ERROR: Tenta recuperação automática
        - CRITICAL: Reinicializa o plugin
        """
        if self._nivel_gravidade_atual == NivelGravidade.CRITICAL:
            if self.logger:
                self.logger.critical(
                    f"[{self.PLUGIN_NAME}] Nível CRITICAL detectado. "
                    f"Executando ação automática: {self._nivel_gravidade_atual.acao_automatica()}"
                )
            # Reinicializa plugin
            try:
                self.finalizar()
                self.inicializar()
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Plugin reinicializado automaticamente"
                    )
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}] Erro ao reinicializar automaticamente: {e}",
                        exc_info=True,
                    )
        elif self._nivel_gravidade_atual == NivelGravidade.ERROR:
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Nível ERROR detectado. "
                    f"Tentando recuperação automática: {self._nivel_gravidade_atual.acao_automatica()}"
                )
            # Tenta recuperação (pode ser sobrescrito em plugins filhos)
            self._tentar_recuperacao()
    
    def _tentar_recuperacao(self):
        """
        Tenta recuperação automática em caso de erro.
        
        Sobrescreva este método em plugins filhos para implementar
        lógica de recuperação específica.
        """
        # Implementação padrão: apenas log
        pass
    
    def _atualizar_telemetria(self, status: str, duracao: float):
        """
        Atualiza as métricas internas de telemetria.
        
        Usado pelo método rodar() para coletar estatísticas que o GerenciadorBot
        pode usar para avaliar estabilidade e performance do plugin.
        
        Args:
            status: Status da execução ("ok" ou "erro")
            duracao: Duração da execução em segundos
        """
        tel = self._telemetria
        agora = datetime.now()
        
        # Contadores básicos
        tel["total_execucoes"] += 1
        tel["ultima_execucao"] = agora
        tel["ultimo_status"] = status
        
        # Primeira execução
        if tel["primeira_execucao"] is None:
            tel["primeira_execucao"] = agora
        
        # Sucesso/Erro
        if status == "ok":
            tel["execucoes_sucesso"] += 1
            tel["falhas_consecutivas"] = 0
        else:
            tel["execucoes_erro"] += 1
            tel["falhas_consecutivas"] += 1
        
        # Métricas de tempo
        tel["tempo_total"] += duracao
        tel["tempo_medio"] = tel["tempo_total"] / tel["total_execucoes"]
        
        if duracao < tel["tempo_minimo"]:
            tel["tempo_minimo"] = duracao
        if duracao > tel["tempo_maximo"]:
            tel["tempo_maximo"] = duracao

    def obter_telemetria(self) -> Dict[str, Any]:
        """
        Obtém as métricas de telemetria do plugin.
        
        Útil para o GerenciadorBot avaliar estabilidade e tomar decisões.
        
        Returns:
            dict: Dicionário com todas as métricas coletadas:
                - total_execucoes: Total de execuções
                - execucoes_sucesso: Quantidade de sucessos
                - execucoes_erro: Quantidade de erros
                - falhas_consecutivas: Falhas seguidas (alerta de instabilidade)
                - tempo_medio: Tempo médio de execução em segundos
                - tempo_minimo: Menor tempo de execução
                - tempo_maximo: Maior tempo de execução
                - taxa_sucesso: Percentual de sucesso (0.0 a 1.0)
                - ultima_execucao: Timestamp da última execução
                - ultimo_status: Status da última execução ("ok" ou "erro")
        """
        tel = self._telemetria.copy()
        
        # Calcula taxa de sucesso
        if tel["total_execucoes"] > 0:
            tel["taxa_sucesso"] = tel["execucoes_sucesso"] / tel["total_execucoes"]
        else:
            tel["taxa_sucesso"] = 0.0
        
        # Limpa valores infinitos
        if tel["tempo_minimo"] == float('inf'):
            tel["tempo_minimo"] = 0.0
        
        # Armazena telemetria no banco a cada execução (ou por lote)
        # Gera estatísticas de aprendizado para IA
        self._armazenar_telemetria_banco(tel)
        
        return tel
    
    def _armazenar_telemetria_banco(self, telemetria: Dict[str, Any]):
        """
        Armazena telemetria no banco via gerenciador_banco.
        
        Gera estatísticas de aprendizado para IA analisar padrões de execução.
        
        Args:
            telemetria: Dicionário com métricas de telemetria
        """
        try:
            if not self.gerenciador_banco:
                return
            
            # Prepara dados para persistência
            dados_telemetria = {
                "plugin": self.PLUGIN_NAME,
                "timestamp": datetime.now().isoformat(),
                "total_execucoes": telemetria.get("total_execucoes", 0),
                "execucoes_sucesso": telemetria.get("execucoes_sucesso", 0),
                "execucoes_erro": telemetria.get("execucoes_erro", 0),
                "falhas_consecutivas": telemetria.get("falhas_consecutivas", 0),
                "tempo_medio": telemetria.get("tempo_medio", 0.0),
                "tempo_minimo": telemetria.get("tempo_minimo", 0.0),
                "tempo_maximo": telemetria.get("tempo_maximo", 0.0),
                "taxa_sucesso": telemetria.get("taxa_sucesso", 0.0),
                "ultima_execucao": telemetria.get("ultima_execucao").isoformat() if telemetria.get("ultima_execucao") else None,
                "ultimo_status": telemetria.get("ultimo_status"),
                "nivel_gravidade": self._nivel_gravidade_atual.value,
            }
            
            # Persiste via gerenciador_banco (pode ser em lote)
            # Se gerenciador_banco tem método inserir direto, usa ele
            if hasattr(self.gerenciador_banco, 'banco_dados') and self.gerenciador_banco.banco_dados:
                self.gerenciador_banco.banco_dados.inserir("telemetria_plugins", dados_telemetria)
            else:
                self.persistir_dados("telemetria_plugins", dados_telemetria)
            
        except Exception as e:
            # Não falha se não conseguir salvar telemetria
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao armazenar telemetria no banco: {e}"
                )

    @property
    def plugin_tabelas(self) -> Dict[str, Dict[str, Any]]:
        """
        Define as tabelas que este plugin utiliza.
        
        Sobrescreva esta propriedade em plugins filhos para declarar tabelas.
        Formato esperado:
        {
            "nome_da_tabela": {
                "descricao": "Descrição da tabela",
                "modo_acesso": "own" ou "shared",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "coluna1": "TIPO_SQL [CONSTRAINTS]",
                    ...
                }
            }
        }
        
        Returns:
            dict: Dicionário com definições de tabelas
        """
        return {}

    def persistir_dados(self, tabela: str, dados: Any) -> bool:
        """
        Persiste dados via GerenciadorBanco.
        
        Valida se a tabela está declarada em plugin_tabelas antes de persistir,
        evitando inconsistências no banco de dados.
        
        Args:
            tabela: Nome da tabela (deve estar declarada em plugin_tabelas)
            dados: Dados a serem persistidos
            
        Returns:
            bool: True se persistido com sucesso, False caso contrário.
        """
        try:
            if not self.gerenciador_banco:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] GerenciadorBanco não disponível para persistir dados"
                    )
                return False

            # Verificação de schema: confirma se tabela existe em plugin_tabelas
            tabelas_declaradas = self.plugin_tabelas
            if tabela not in tabelas_declaradas:
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}] Tabela '{tabela}' não está declarada em plugin_tabelas. "
                        f"Tabelas declaradas: {list(tabelas_declaradas.keys())}"
                    )
                return False

            # Log informativo sobre a tabela
            if self.logger:
                info_tabela = tabelas_declaradas[tabela]
                modo_acesso = info_tabela.get("modo_acesso", "unknown")
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Persistindo dados na tabela '{tabela}' "
                    f"(modo: {modo_acesso}, plugin: {info_tabela.get('plugin', 'N/A')})"
                )

            resultado = self.gerenciador_banco.persistir_dados(
                plugin=self.PLUGIN_NAME,
                tabela=tabela,
                dados=dados,
            )

            if self.logger and resultado:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Dados persistidos com sucesso na tabela '{tabela}'"
                )
            elif self.logger and not resultado:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Falha ao persistir dados na tabela '{tabela}'"
                )

            return resultado
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao persistir dados na tabela '{tabela}': {e}",
                    exc_info=True,
                )
            return False

    def solicitar_cancelamento(self):
        """
        Solicita cancelamento gracioso do plugin.
        
        Útil quando o sistema está sendo finalizado e queremos que
        operações em andamento sejam canceladas de forma graciosa.
        """
        self._cancelamento_solicitado = True
        if self.logger:
            self.logger.debug(f"[{self.PLUGIN_NAME}] Cancelamento solicitado")
    
    def cancelamento_solicitado(self) -> bool:
        """
        Verifica se cancelamento foi solicitado.
        
        Returns:
            bool: True se cancelamento foi solicitado, False caso contrário
        """
        return self._cancelamento_solicitado
    
    def finalizar(self) -> bool:
        """
        Finaliza o plugin e libera recursos.
        
        Este método deve:
        - Encerrar processos, threads ou tarefas assíncronas
        - Liberar recursos (arquivos, conexões, buffers)
        - Garantir consistência dos dados persistidos
        
        IMPORTANTE: Não deve ser chamado durante o ciclo de execução normal!
        Apenas no encerramento do sistema.
        
        Returns:
            bool: True se finalizado com sucesso, False caso contrário.
        
        """
        try:
            # Solicita cancelamento antes de finalizar
            self.solicitar_cancelamento()
            
            import traceback
            # Log de debug para identificar chamadas indevidas
            if self.logger:
                stack = ''.join(traceback.format_stack()[-3:-1])
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] finalizar() chamado. "
                    f"Stack trace: {stack}"
                )
            
            # Chama finalização específica do plugin
            resultado = self._finalizar_interno()
            
            if resultado:
                self._inicializado = False
                self._em_execucao = False
                
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Plugin finalizado com sucesso"
                    )
            
            return resultado
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao finalizar plugin: {e}",
                    exc_info=True,
                )
            return False

    def _finalizar_interno(self) -> bool:
        """
        Método interno para finalização específica do plugin.
        
        Sobrescreva este método em plugins filhos para adicionar lógica de finalização.
        
        Returns:
            bool: True se finalizado com sucesso, False caso contrário.
        """
        return True

    @property
    def esta_inicializado(self) -> bool:
        """Verifica se o plugin está inicializado."""
        return self._inicializado

    @property
    def esta_em_execucao(self) -> bool:
        """Verifica se o plugin está em execução."""
        return self._em_execucao

    # ============================================================
    # CONTEXT MANAGER (with statement)
    # ============================================================

    def __enter__(self):
        """
        Context manager entry: inicializa o plugin automaticamente.
        
        Permite uso com 'with':
        
        with PluginXYZ() as plugin:
            plugin.rodar()
        
        Returns:
            Plugin: Instância do plugin (self)
        """
        if not self._inicializado:
            if not self.inicializar():
                raise RuntimeError(
                    f"[{self.PLUGIN_NAME}] Falha ao inicializar plugin no context manager"
                )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit: finaliza o plugin automaticamente e trata exceções.
        
        Garante limpeza segura mesmo em caso de exceção durante a execução.
        
        IMPORTANTE: Plugins com keep_alive=True não serão finalizados durante o
        ciclo de execução normal. Apenas serão finalizados quando explicitamente
        solicitado (finalização do sistema).
        
        Args:
            exc_type: Tipo da exceção (None se não houve exceção)
            exc_val: Valor da exceção
            exc_tb: Traceback da exceção
            
        Returns:
            bool: False para propagar exceção, True para suprimir
        """
        # Verifica se plugin tem keep_alive ativo (plugins de conexão persistente)
        # Se tiver, não finaliza durante ciclo de execução
        if hasattr(self, 'keep_alive') and self.keep_alive:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Plugin com keep_alive ativo - "
                    f"não finalizando durante ciclo de execução"
                )
            # Não finaliza, apenas retorna
        else:
            # Finaliza apenas se não tiver keep_alive
            try:
                if self._inicializado:
                    self.finalizar()
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}] Erro ao finalizar no context manager: {e}",
                        exc_info=True,
                    )

        # Se houve exceção durante a execução, trata de forma especial
        if exc_type is not None:
            # SystemExit e KeyboardInterrupt são exceções normais de finalização
            # Não devem ser logadas como erro
            if exc_type in (SystemExit, KeyboardInterrupt):
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Finalização solicitada (SystemExit/KeyboardInterrupt)"
                    )
                # Suprime SystemExit/KeyboardInterrupt para permitir finalização graciosa
                return True
            else:
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}] Exceção capturada no context manager: "
                        f"{exc_type.__name__}: {exc_val}",
                        exc_info=(exc_type, exc_val, exc_tb),
                    )
                # Retorna False para propagar a exceção original
                return False

        return False  # Não suprime exceções por padrão

    def __repr__(self) -> str:
        """Representação string do plugin."""
        return (
            f"<{self.PLUGIN_NAME} "
            f"(versão: {self.plugin_versao}, "
            f"inicializado: {self._inicializado}, "
            f"em_execucao: {self._em_execucao})>"
        )

