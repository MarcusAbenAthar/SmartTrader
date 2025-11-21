"""
Plugin de Conexão com a API Bybit.

Gerencia conexão, autenticação e operações básicas com a exchange Bybit.
Suporta testnet e mainnet conforme configuração.

__institucional__ = "Smart_Trader Plugin Bybit Conexão - Sistema 6/8 Unificado"
"""

import ccxt
from typing import Dict, Any, Optional
from datetime import datetime
import time
from plugins.base_plugin import Plugin, execucao_segura, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginBybitConexao(Plugin):
    """
    Plugin que gerencia conexão com a API Bybit.
    
    Responsabilidades:
    - Estabelecer e manter conexão com Bybit (testnet/mainnet)
    - Autenticação com API keys do .env
    - Verificação de status da conexão
    - Recuperação automática em caso de falha
    - Logging de operações e erros
    
    Características:
    - Suporte a testnet/mainnet automático
    - Reconexão automática
    - Rate limiting respeitado
    - Thread-safe para uso concorrente
    """
    
    __institucional__ = "Smart_Trader Plugin Bybit Conexão - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginBybitConexao"
    plugin_versao = "v1.0.0"
    plugin_schema_versao = "v1.0.0"
    plugin_tipo = TipoPlugin.CONEXAO
    
    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLogProtocol] = None,
        gerenciador_banco: Optional[GerenciadorBancoProtocol] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o PluginBybitConexao.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            gerenciador_banco: Instância do GerenciadorBanco
            config: Configuração do sistema (deve conter credenciais Bybit)
        """
        super().__init__(gerenciador_log, gerenciador_banco, config)
        
        # Extrai configurações Bybit
        bybit_config = self.config.get("bybit", {})
        self.api_key = bybit_config.get("api_key")
        self.api_secret = bybit_config.get("api_secret")
        self.testnet = bybit_config.get("testnet", False)
        self.market = bybit_config.get("market", "linear")
        
        # Instância da exchange (será criada na inicialização)
        self.exchange: Optional[ccxt.bybit] = None
        
        # Estado da conexão
        self._conexao_ativa: bool = False
        self._ultima_verificacao: Optional[datetime] = None
        self._tentativas_reconexao: int = 0
        self._max_tentativas_reconexao: int = 3
        
        # Keep alive - mantém conexão ativa
        self.keep_alive: bool = True
        
        # Rate limiting
        self._ultima_requisicao: float = 0.0
        self._delay_minimo_requisicoes: float = 0.1  # 100ms entre requisições
        
    def _inicializar_interno(self) -> bool:
        """
        Inicializa conexão com Bybit.
        
        Returns:
            bool: True se conexão estabelecida com sucesso
        """
        try:
            # Valida credenciais
            if not self.api_key or not self.api_secret:
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}] Credenciais Bybit não encontradas na configuração"
                    )
                return False
            
            # Cria instância da exchange
            self.exchange = ccxt.bybit({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'enableRateLimit': True,  # Respeita rate limits automaticamente
                'options': {
                    'defaultType': self.market,  # linear, inverse, spot
                },
            })
            
            # Mantém conexão ativa
            self.keep_alive = True
            
            # Configura testnet se necessário
            if self.testnet:
                self.exchange.set_sandbox_mode(True)
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Modo TESTNET ativado"
                    )
            
            # Testa conexão
            if self._verificar_conexao():
                self._conexao_ativa = True
                self._ultima_verificacao = datetime.now()
                
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Conexão estabelecida com sucesso "
                        f"(testnet: {self.testnet}, market: {self.market})"
                    )
                
                return True
            else:
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}] Falha ao verificar conexão inicial"
                    )
                return False
                
        except Exception as e:
            if self.logger:
                self.logger.critical(
                    f"[{self.PLUGIN_NAME}] Erro ao inicializar conexão: {e}",
                    exc_info=True,
                )
            return False
    
    def _verificar_conexao(self) -> bool:
        """
        Verifica se a conexão está ativa.
        
        Tenta uma operação simples (fetch balance ou time) para validar.
        
        Returns:
            bool: True se conexão está funcionando
        """
        try:
            if not self.exchange:
                return False
            
            # Tenta buscar timestamp da exchange (operação leve)
            timestamp = self.exchange.fetch_time()
            
            if timestamp:
                self._ultima_verificacao = datetime.now()
                self._tentativas_reconexao = 0
                return True
            
            return False
            
        except ccxt.NetworkError as e:
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Erro de rede ao verificar conexão: {e}"
                )
            return False
            
        except ccxt.ExchangeError as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro da exchange ao verificar conexão: {e}"
                )
            return False
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro inesperado ao verificar conexão: {e}",
                    exc_info=True,
                )
            return False
    
    def reconectar(self) -> bool:
        """
        Tenta reconectar à exchange.
        
        Returns:
            bool: True se reconexão bem-sucedida
        """
        if self._tentativas_reconexao >= self._max_tentativas_reconexao:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Máximo de tentativas de reconexão atingido"
                )
            return False
        
        try:
            self._tentativas_reconexao += 1
            
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Tentando reconectar "
                    f"(tentativa {self._tentativas_reconexao}/{self._max_tentativas_reconexao})"
                )
            
            # Recria instância da exchange
            self.exchange = ccxt.bybit({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': self.market,
                },
            })
            
            if self.testnet:
                self.exchange.set_sandbox_mode(True)
            
            # Aguarda um pouco antes de verificar
            time.sleep(1)
            
            if self._verificar_conexao():
                self._conexao_ativa = True
                self._tentativas_reconexao = 0
                
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Reconexão bem-sucedida"
                    )
                
                return True
            
            return False
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao tentar reconectar: {e}",
                    exc_info=True,
                )
            return False
    
    @property
    def plugin_tabelas(self) -> Dict[str, Dict[str, Any]]:
        """
        Define as tabelas que este plugin utiliza.
        
        Este plugin não persiste dados diretamente, apenas gerencia conexão.
        
        Returns:
            dict: Definições de tabelas (vazio para este plugin)
        """
        return {}
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Verifica status da conexão e atualiza estado interno.
        
        IMPORTANTE: Este método NÃO usa @execucao_segura porque este plugin
        mantém conexão persistente durante todo o ciclo de execução.
        A finalização só ocorre quando explicitamente solicitada.
        
        Args:
            dados_entrada: Opcional, não usado neste plugin
            
        Returns:
            dict: Status da conexão
        """
        try:
            # Garante que plugin está inicializado
            if not self._inicializado:
                if not self.inicializar():
                    return {
                        "status": "erro",
                        "mensagem": "Falha ao inicializar conexão",
                        "plugin": self.PLUGIN_NAME,
                    }
            
            # Verifica conexão periodicamente (a cada 30 segundos no mínimo)
            agora = datetime.now()
            if (not self._ultima_verificacao or 
                (agora - self._ultima_verificacao).total_seconds() > 30):
                
                conexao_ok = self._verificar_conexao()
                
                if not conexao_ok and self._conexao_ativa:
                    # Conexão perdida, tenta reconectar
                    self._conexao_ativa = False
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Conexão perdida, tentando reconectar..."
                        )
                    self.reconectar()
                elif conexao_ok:
                    self._conexao_ativa = True
            
            return {
                "status": "ok",
                "conexao_ativa": self._conexao_ativa,
                "testnet": self.testnet,
                "market": self.market,
                "ultima_verificacao": self._ultima_verificacao.isoformat() if self._ultima_verificacao else None,
                "tentativas_reconexao": self._tentativas_reconexao,
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao executar verificação: {e}",
                    exc_info=True,
                )
            return {
                "status": "erro",
                "mensagem": str(e),
                "plugin": self.PLUGIN_NAME,
            }
    
    def obter_exchange(self) -> Optional[ccxt.bybit]:
        """
        Obtém instância da exchange para uso por outros plugins.
        
        Retorna None se conexão não estiver ativa.
        
        Returns:
            ccxt.bybit: Instância da exchange ou None
        """
        if not self._conexao_ativa or not self.exchange:
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Tentativa de usar exchange sem conexão ativa"
                )
            return None
        
        return self.exchange
    
    def obter_status(self) -> Dict[str, Any]:
        """
        Obtém status completo da conexão.
        
        Returns:
            dict: Status incluindo:
                - conexao_ativa: Se conexão está funcionando
                - testnet: Se está em testnet
                - market: Tipo de mercado
                - ultima_verificacao: Timestamp da última verificação
                - tentativas_reconexao: Número de tentativas de reconexão
        """
        return {
            "conexao_ativa": self._conexao_ativa,
            "testnet": self.testnet,
            "market": self.market,
            "ultima_verificacao": self._ultima_verificacao.isoformat() if self._ultima_verificacao else None,
            "tentativas_reconexao": self._tentativas_reconexao,
            "api_key_configured": bool(self.api_key),
            "api_secret_configured": bool(self.api_secret),
        }
    
    def _finalizar_interno(self) -> bool:
        """
        Finaliza conexão com Bybit.
        
        IMPORTANTE: Este método só deve ser chamado no finalizar() do plugin,
        nunca durante o ciclo de execução normal (quando keep_alive=True).
        
        O keep_alive impede a finalização automática via context manager durante
        o ciclo de execução, mas não impede a finalização explícita via finalizar().
        """
        try:
            # Desabilita keep_alive antes de finalizar
            self.keep_alive = False
            
            # Fecha conexão se existir
            if self.exchange:
                # ccxt não precisa de close explícito, mas limpa referência
                self.exchange = None
            
            self._conexao_ativa = False
            
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Conexão finalizada"
                )
            
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao finalizar: {e}",
                    exc_info=True,
                )
            return False
    
    def desabilitar_keep_alive(self):
        """Desabilita keep_alive para permitir finalização."""
        self.keep_alive = False

