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
                    self.GERENCIADOR_NAME, "system"
                )
            
            if self.logger:
                self.logger.debug(
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
                self.logger.debug(
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
                return {
                    "status": "erro",
                    "mensagem": "Gerenciador não inicializado",
                    "plugins_executados": [],
                    "plugins_com_erro": [],
                    "resultados": {},
                    "total_plugins": 0,
                    "total_executados": 0,
                    "total_erros": 0,
                }

            resultados = {}
            dados_atuais = dados_entrada or {}
            plugins_executados = []
            plugins_com_erro = []

            # Calcula ordem de execução se necessário
            if not self.ordem_execucao:
                self._calcular_ordem_execucao()
            
            # Log de diagnóstico: mostra todos os plugins registrados
            if self.logger:
                total_registrados = len(self.plugins)
                plugins_registrados = list(self.plugins.keys())
                plugins_na_ordem = list(self.ordem_execucao)
                self.logger.debug(
                    f"[{self.GERENCIADOR_NAME}] DEBUG — Plugins registrados: {total_registrados} "
                    f"({', '.join(plugins_registrados)})"
                )
                self.logger.debug(
                    f"[{self.GERENCIADOR_NAME}] DEBUG — Ordem de execução: {len(plugins_na_ordem)} "
                    f"({', '.join(plugins_na_ordem)})"
                )

            # Executa plugins na ordem
            plugins_pulados = []
            for nome_plugin in self.ordem_execucao:
                if nome_plugin not in self.plugins:
                    plugins_pulados.append(f"{nome_plugin} (não encontrado)")
                    continue

                plugin = self.plugins[nome_plugin]

                try:
                    # Pula plugins AUXILIAR - eles são executados sob demanda por outros plugins
                    # (ex: PluginFiltroDinamico é chamado pelo PluginDadosVelas)
                    # Pula plugins IA - eles são executados no final do ciclo após todos os pares
                    if hasattr(plugin, 'plugin_tipo'):
                        if plugin.plugin_tipo.value == "auxiliar":
                            plugins_pulados.append(f"{nome_plugin} (auxiliar)")
                            if self.logger:
                                self.logger.debug(
                                    f"[{self.GERENCIADOR_NAME}] Pulando plugin auxiliar '{nome_plugin}' "
                                    f"(executado sob demanda)"
                                )
                            continue
                        elif plugin.plugin_tipo.value == "ia":
                            plugins_pulados.append(f"{nome_plugin} (ia)")
                            if self.logger:
                                self.logger.debug(
                                    f"[{self.GERENCIADOR_NAME}] Pulando plugin IA '{nome_plugin}' "
                                    f"(executado no final do ciclo)"
                                )
                            continue
                    
                    # Verifica se plugin já está em execução
                    if plugin.esta_em_execucao:
                        if self.logger:
                            self.logger.warning(
                                f"[{self.GERENCIADOR_NAME}] Plugin '{nome_plugin}' já está em execução. Pulando..."
                            )
                        continue
                    
                    # Log DEBUG apenas (reduz spam - execução de plugins é rotina)
                    if self.logger:
                        self.logger.debug(
                            f"[{self.GERENCIADOR_NAME}] ▶ Executando plugin '{nome_plugin}'"
                        )

                    # Mede tempo de execução (usa perf_counter para maior precisão)
                    import time
                    tempo_inicio = time.perf_counter()
                    
                    # Executa plugin (executar() já tem @execucao_segura quando aplicável)
                    resultado = plugin.executar(dados_atuais)
                    
                    tempo_fim = time.perf_counter()
                    tempo_execucao_ms = (tempo_fim - tempo_inicio) * 1000
                    
                    # Garante que resultado é um dict antes de adicionar tempo
                    if resultado is None:
                        resultado = {"status": "ok", "plugin": nome_plugin}
                    elif not isinstance(resultado, dict):
                        resultado = {"status": "ok", "plugin": nome_plugin, "resultado_original": resultado}
                    
                    resultado["tempo_execucao_ms"] = tempo_execucao_ms
                    resultados[nome_plugin] = resultado
                    
                    # Log DEBUG: Tempo de execução por plugin
                    if self.logger:
                        status_resultado = resultado.get("status", "unknown") if isinstance(resultado, dict) else "unknown"
                        # Log mais detalhado para tempos muito baixos (usa mais casas decimais com perf_counter)
                        if tempo_execucao_ms < 0.1:
                            # Tempo muito pequeno - mostra com 4 casas decimais
                            self.logger.debug(
                                f"[{self.GERENCIADOR_NAME}] DEBUG — Tempo de execução — {nome_plugin}: {tempo_execucao_ms:.4f} ms "
                                f"(processamento muito rápido - dados em memória)"
                            )
                        elif tempo_execucao_ms < 1.0:
                            # Tempo pequeno - mostra com 3 casas decimais
                            self.logger.debug(
                                f"[{self.GERENCIADOR_NAME}] DEBUG — Tempo de execução — {nome_plugin}: {tempo_execucao_ms:.3f} ms "
                                f"(processamento rápido)"
                            )
                        else:
                            # Tempo normal - mostra com 2 casas decimais
                            self.logger.debug(
                                f"[{self.GERENCIADOR_NAME}] DEBUG — Tempo de execução — {nome_plugin}: {tempo_execucao_ms:.2f} ms"
                            )
                        # Log DEBUG apenas (reduz spam - execução de plugins é rotina)
                        self.logger.debug(
                            f"[{self.GERENCIADOR_NAME}] ✓ Plugin '{nome_plugin}' executado com status: {status_resultado}"
                        )
                    
                    # Verifica status
                    if resultado and isinstance(resultado, dict):
                        if resultado.get("status") == "ok":
                            plugins_executados.append(nome_plugin)
                        elif resultado.get("status") == "erro":
                            plugins_com_erro.append(nome_plugin)
                        
                        # Atualiza dados para próximo plugin (apenas dados válidos)
                        if resultado.get("status") == "ok":
                            dados_atuais.update(resultado)
                    else:
                        plugins_executados.append(nome_plugin)
                except Exception as e:
                    plugins_com_erro.append(nome_plugin)
                    if self.logger:
                        self.logger.error(
                            f"[{self.GERENCIADOR_NAME}] Erro ao executar plugin "
                            f"'{nome_plugin}': {e}",
                            exc_info=True,
                        )
                    resultados[nome_plugin] = {
                        "status": "erro",
                        "mensagem": str(e),
                        "plugin": nome_plugin
                    }

            # Calcula métricas consolidadas
            tempos_execucao = {}
            tempo_total_ms = 0
            for nome_plugin, resultado in resultados.items():
                if isinstance(resultado, dict) and "tempo_execucao_ms" in resultado:
                    tempo_ms = resultado["tempo_execucao_ms"]
                    tempos_execucao[nome_plugin] = tempo_ms
                    tempo_total_ms += tempo_ms
            
            # Log DEBUG: Métricas consolidadas de tempo
            if self.logger and tempos_execucao:
                tempos_str = ", ".join([f"{nome}: {tempo:.2f}ms" for nome, tempo in tempos_execucao.items()])
                self.logger.debug(
                    f"[{self.GERENCIADOR_NAME}] DEBUG — Tempo de execução por plugin: {tempos_str} — Total: {tempo_total_ms:.2f} ms"
                )
            
            # Extrai nomes dos plugins pulados intencionalmente (auxiliar/ia)
            # Formato: "PluginNome (auxiliar)" ou "PluginNome (ia)"
            plugins_pulados_intencionalmente = set()
            for item in plugins_pulados:
                if " (auxiliar)" in item or " (ia)" in item:
                    nome_plugin = item.split(" (")[0]
                    plugins_pulados_intencionalmente.add(nome_plugin)
            
            # Identifica plugins não executados (excluindo os pulados intencionalmente)
            plugins_nao_executados = [
                nome for nome in self.plugins.keys() 
                if nome not in plugins_executados 
                and nome not in plugins_com_erro
                and nome not in plugins_pulados_intencionalmente
            ]
            
            # Log de diagnóstico: mostra plugins pulados
            if plugins_pulados and self.logger:
                self.logger.debug(
                    f"[{self.GERENCIADOR_NAME}] DEBUG — Plugins pulados: {len(plugins_pulados)} "
                    f"({', '.join(plugins_pulados)})"
                )
            
            # Log INFO: Identifica plugins não executados (usa categoria PLUGIN)
            # Só loga se houver plugins realmente não executados (não os pulados intencionalmente)
            if plugins_nao_executados:
                if self.gerenciador_log:
                    from plugins.gerenciadores.gerenciador_log import CategoriaLog
                    import logging
                    self.gerenciador_log.log_categoria(
                        categoria=CategoriaLog.PLUGIN,
                        nome_origem=self.GERENCIADOR_NAME,
                        mensagem=f"{len(plugins_nao_executados)} plugin(s) não executado(s): {', '.join(plugins_nao_executados)}. Motivo: Plugin não está na ordem de execução ou foi pulado intencionalmente.",
                        nivel=logging.INFO,
                        tipo_log="system",
                        plugin_nome=self.GERENCIADOR_NAME
                    )
            
            # Retorna resultado agregado
            status_geral = "ok" if not plugins_com_erro else "erro_parcial" if plugins_executados else "erro"
            
            return {
                "status": status_geral,
                "plugins_executados": plugins_executados,
                "plugins_com_erro": plugins_com_erro,
                "plugins_nao_executados": plugins_nao_executados,
                "tempos_execucao": tempos_execucao,
                "tempo_total_ms": tempo_total_ms,
                "resultados": resultados,
                "total_plugins": len(self.plugins),
                "total_executados": len(plugins_executados),
                "total_erros": len(plugins_com_erro),
            }
        except Exception as e:
            if self.logger:
                self.logger.critical(
                    f"[{self.GERENCIADOR_NAME}] Erro crítico ao executar plugins: {e}",
                    exc_info=True,
                )
            return {
                "status": "erro",
                "mensagem": str(e),
                "plugins_executados": [],
                "plugins_com_erro": list(self.plugins.keys()),
                "resultados": {},
                "total_plugins": len(self.plugins),
                "total_executados": 0,
                "total_erros": len(self.plugins),
            }

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
            # Primeiro, solicita cancelamento em todos os plugins
            for nome_plugin in self.ordem_execucao:
                if nome_plugin in self.plugins:
                    try:
                        self.plugins[nome_plugin].solicitar_cancelamento()
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(
                                f"[{self.GERENCIADOR_NAME}] Erro ao solicitar cancelamento "
                                f"em plugin '{nome_plugin}': {e}"
                            )
            
            # Aguarda um pouco para requisições em andamento terminarem
            import time
            time.sleep(0.3)
            
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

