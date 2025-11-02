"""
Gerenciador de Plugins do sistema.

Orquestra o ciclo de vida dos plugins:
- Descobrimento de plugins
- Resolução de dependências
- Ordem de execução
- Inicialização e finalização
"""

from typing import Dict, Any, Optional, List, Type
from pathlib import Path
import importlib
import inspect
from plugins.gerenciadores.gerenciador import GerenciadorBase
from plugins.base_plugin import Plugin
import json


class GerenciadorPlugins(GerenciadorBase):
    """
    Gerenciador de plugins do sistema.
    
    Responsabilidades:
    - Descoberta e carregamento de plugins
    - Resolução de dependências entre plugins
    - Orquestração do ciclo de vida (inicializar -> executar -> finalizar)
    - Gerenciamento de ordem de execução
    
    Não acessa banco ou API diretamente - apenas orquestra plugins.
    
    Attributes:
        GERENCIADOR_NAME (str): Nome do gerenciador
        plugins (dict): Dicionário de plugins carregados {nome: instância}
        dependencias (dict): Grafo de dependências entre plugins
        ordem_execucao (list): Ordem de execução calculada
    """

    GERENCIADOR_NAME: str = "GerenciadorPlugins"

    def __init__(
        self,
        gerenciador_log=None,
        gerenciador_banco=None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o GerenciadorPlugins.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            gerenciador_banco: Instância do GerenciadorBanco
            config: Configuração do sistema
        """
        super().__init__()
        self.gerenciador_log = gerenciador_log
        self.gerenciador_banco = gerenciador_banco
        self.config = config or {}
        
        self.plugins: Dict[str, Plugin] = {}
        self.dependencias: Dict[str, List[str]] = {}
        self.ordem_execucao: List[str] = []
        
        self.logger = None

    def inicializar(self) -> bool:
        """
        Inicializa o GerenciadorPlugins.
        
        Returns:
            bool: True se inicializado com sucesso, False caso contrário.
        """
        try:
            if self.gerenciador_log:
                self.logger = self.gerenciador_log.get_logger(
                    self.GERENCIADOR_NAME, "rastreamento"
                )
            
            if self.logger:
                self.logger.info(
                    f"[{self.GERENCIADOR_NAME}] Iniciando descoberta de plugins..."
                )
            
            # Carrega plugins (a ser implementado quando plugins estiverem disponíveis)
            # Por enquanto apenas inicializa estrutura
            
            self._inicializado = True
            return True
        except Exception as e:
            if self.logger:
                self.logger.critical(
                    f"[{self.GERENCIADOR_NAME}] Erro ao inicializar: {e}",
                    exc_info=True,
                )
            return False

    def registrar_plugin(self, plugin: Plugin) -> bool:
        """
        Registra um plugin no gerenciador.
        
        Args:
            plugin: Instância do plugin a ser registrado
            
        Returns:
            bool: True se registrado com sucesso, False caso contrário.
        """
        try:
            if not isinstance(plugin, Plugin):
                if self.logger:
                    self.logger.error(
                        f"[{self.GERENCIADOR_NAME}] Tentativa de registrar objeto "
                        f"que não é Plugin: {type(plugin)}"
                    )
                return False

            nome = plugin.PLUGIN_NAME
            
            if nome in self.plugins:
                if self.logger:
                    self.logger.warning(
                        f"[{self.GERENCIADOR_NAME}] Plugin '{nome}' já registrado"
                    )
                return False

            # Injeta dependências
            plugin.gerenciador_log = self.gerenciador_log
            plugin.gerenciador_banco = self.gerenciador_banco
            plugin.config = self.config

            # Inicializa o plugin
            if not plugin.inicializar():
                if self.logger:
                    self.logger.error(
                        f"[{self.GERENCIADOR_NAME}] Falha ao inicializar plugin '{nome}'"
                    )
                return False

            # Registra
            self.plugins[nome] = plugin

            if self.logger:
                self.logger.info(
                    f"[{self.GERENCIADOR_NAME}] Plugin '{nome}' registrado com sucesso"
                )

            return True
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.GERENCIADOR_NAME}] Erro ao registrar plugin: {e}",
                    exc_info=True,
                )
            return False

    def executar_plugins(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executa todos os plugins na ordem correta.
        
        Args:
            dados_entrada: Dados de entrada para o primeiro plugin
            
        Returns:
            dict: Resultados agregados de todos os plugins
        """
        try:
            if not self._inicializado:
                if self.logger:
                    self.logger.error(
                        f"[{self.GERENCIADOR_NAME}] Gerenciador não inicializado"
                    )
                return {}

            resultados = {}
            dados_atuais = dados_entrada or {}

            # Calcula ordem de execução se necessário
            if not self.ordem_execucao:
                self._calcular_ordem_execucao()

            # Executa plugins na ordem
            for nome_plugin in self.ordem_execucao:
                if nome_plugin not in self.plugins:
                    continue

                plugin = self.plugins[nome_plugin]

                try:
                    plugin._em_execucao = True
                    
                    if self.logger:
                        self.logger.debug(
                            f"[{self.GERENCIADOR_NAME}] Executando plugin '{nome_plugin}'"
                        )

                    resultado = plugin.executar(dados_atuais)
                    resultados[nome_plugin] = resultado

                    # Atualiza dados para próximo plugin
                    if resultado and isinstance(resultado, dict):
                        dados_atuais.update(resultado)
                    
                    plugin._em_execucao = False
                except Exception as e:
                    plugin._em_execucao = False
                    if self.logger:
                        self.logger.error(
                            f"[{self.GERENCIADOR_NAME}] Erro ao executar plugin "
                            f"'{nome_plugin}': {e}",
                            exc_info=True,
                        )
                    resultados[nome_plugin] = {"erro": str(e)}

            return resultados
        except Exception as e:
            if self.logger:
                self.logger.critical(
                    f"[{self.GERENCIADOR_NAME}] Erro crítico ao executar plugins: {e}",
                    exc_info=True,
                )
            return {}

    def _calcular_ordem_execucao(self):
        """
        Calcula a ordem de execução dos plugins baseado em dependências.
        
        Usa ordenação topológica para garantir que dependências sejam executadas antes.
        """
        # Por enquanto, executa na ordem de registro
        # Pode ser expandido para usar ordenação topológica quando dependências
        # forem declaradas pelos plugins
        self.ordem_execucao = list(self.plugins.keys())

    def executar(self, *args, **kwargs):
        """
        Executa o gerenciador (delega para executar_plugins).
        """
        return self.executar_plugins(*args, **kwargs)

    def finalizar(self) -> bool:
        """
        Finaliza todos os plugins e o gerenciador.
        
        Returns:
            bool: True se finalizado com sucesso, False caso contrário.
        """
        try:
            # Finaliza plugins na ordem reversa
            for nome_plugin in reversed(self.ordem_execucao):
                if nome_plugin in self.plugins:
                    try:
                        self.plugins[nome_plugin].finalizar()
                    except Exception as e:
                        if self.logger:
                            self.logger.error(
                                f"[{self.GERENCIADOR_NAME}] Erro ao finalizar plugin "
                                f"'{nome_plugin}': {e}",
                                exc_info=True,
                            )

            if self.logger:
                self.logger.info(
                    f"[{self.GERENCIADOR_NAME}] Todos os plugins finalizados"
                )

            self._inicializado = False
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.GERENCIADOR_NAME}] Erro ao finalizar: {e}",
                    exc_info=True,
                )
            return False

    def obter_plugin(self, nome: str) -> Optional[Plugin]:
        """
        Obtém um plugin pelo nome.
        
        Args:
            nome: Nome do plugin
            
        Returns:
            Plugin ou None se não encontrado
        """
        return self.plugins.get(nome)

