"""
Ponto de entrada principal do sistema Smart_Trader.

Orquestra inicialização e execução dos gerenciadores e plugins.
Sistema 6/8 - Trading Bot com 8 indicadores técnicos.
"""

import sys
import signal
from typing import Optional, Dict, Any
from plugins.gerenciadores.gerenciador_log import GerenciadorLog
from plugins.gerenciadores.gerenciador_banco import GerenciadorBanco
from plugins.gerenciadores.gerenciador_plugins import GerenciadorPlugins
from plugins.gerenciadores.gerenciador_bot import GerenciadorBot
from plugins.conexoes.plugin_bybit_conexao import PluginBybitConexao
from plugins.indicadores.plugin_dados_velas import PluginDadosVelas
from plugins.indicadores.plugin_ichimoku import PluginIchimoku
from plugins.indicadores.plugin_supertrend import PluginSupertrend
from plugins.indicadores.plugin_bollinger import PluginBollinger
from plugins.indicadores.plugin_volume import PluginVolume
from plugins.indicadores.plugin_ema import PluginEma
from plugins.indicadores.plugin_macd import PluginMacd
from plugins.indicadores.plugin_rsi import PluginRsi
from plugins.indicadores.plugin_vwap import PluginVwap
from utils.main_config import carregar_config

# ================================
# 1. LIMPEZA AUTOMÁTICA (sempre primeiro!)
# ================================
import subprocess
import os

# Garante que estamos no diretório do projeto
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Executa limpar_lixo.py antes de tudo
print("Executando limpeza automática...")
result = subprocess.run([sys.executable, "limpar_lixo.py"])

# Opcional: só continua se a limpeza foi bem-sucedida
if result.returncode != 0:
    print("Erro ao executar limpar_lixo.py. Encerrando.")
    sys.exit(1)

print("Limpeza concluída. Iniciando main.py...\n")


class SmartTrader:
    """
    Classe principal que orquestra todo o sistema.

    Responsabilidades:
    - Inicialização dos gerenciadores na ordem correta
    - Carregamento de configuração
    - Ciclo de execução principal
    - Finalização segura do sistema
    """

    def __init__(self):
        """Inicializa o sistema."""
        self.config: Optional[dict] = None
        self.gerenciador_log: Optional[GerenciadorLog] = None
        self.gerenciador_banco: Optional[GerenciadorBanco] = None
        self.gerenciador_plugins: Optional[GerenciadorPlugins] = None
        self.gerenciador_bot: Optional[GerenciadorBot] = None
        self._em_execucao = False

    def inicializar(self) -> bool:
        """
        Inicializa o sistema completo.

        Ordem de inicialização:
        1. Carrega configuração
        2. GerenciadorLog (base para tudo)
        3. GerenciadorBanco
        4. GerenciadorPlugins
        5. GerenciadorBot

        Returns:
            bool: True se inicializado com sucesso, False caso contrário.
        """
        try:
            print("[SmartTrader] Inicializando sistema...")

            # 1. Carrega configuração
            self.config = carregar_config()
            print("[SmartTrader] Configuração carregada")

            # 2. Inicializa GerenciadorLog (já inicializa automaticamente no __init__)
            self.gerenciador_log = GerenciadorLog(base_path="logs")
            print("[SmartTrader] GerenciadorLog inicializado")

            # 3. Inicializa GerenciadorBanco
            self.gerenciador_banco = GerenciadorBanco(
                gerenciador_log=self.gerenciador_log,
                schema_path=self.config.get("db", {}).get(
                    "schema_path", "utils/schema.json"
                ),
            )
            if not self.gerenciador_banco.inicializar():
                print("[SmartTrader] ERRO: Falha ao inicializar GerenciadorBanco")
                return False
            print("[SmartTrader] GerenciadorBanco inicializado")

            # 4. Inicializa GerenciadorPlugins
            self.gerenciador_plugins = GerenciadorPlugins(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
            )
            if not self.gerenciador_plugins.inicializar():
                print("[SmartTrader] ERRO: Falha ao inicializar GerenciadorPlugins")
                return False
            print("[SmartTrader] GerenciadorPlugins inicializado")
            
            # 4.1. Registra plugins principais
            self._registrar_plugins()

            # 5. Inicializa GerenciadorBot
            self.gerenciador_bot = GerenciadorBot(
                gerenciador_log=self.gerenciador_log,
                config=self.config,
            )
            if not self.gerenciador_bot.inicializar():
                print("[SmartTrader] ERRO: Falha ao inicializar GerenciadorBot")
                return False
            print("[SmartTrader] GerenciadorBot inicializado")

            print("[SmartTrader] Sistema inicializado com sucesso!")
            return True

        except Exception as e:
            print(f"[SmartTrader] ERRO CRÍTICO na inicialização: {e}")
            if self.gerenciador_log:
                self.gerenciador_log.log_erro_critico(
                    "SmartTrader", f"Erro na inicialização: {e}"
                )
            return False
    
    def _registrar_plugins(self):
        """
        Registra todos os plugins no GerenciadorPlugins.
        
        Ordem de registro:
        1. PluginBybitConexao (base para outros plugins)
        2. PluginBancoDados (banco de dados PostgreSQL)
        3. PluginDadosVelas (depende de PluginBybitConexao e PluginBancoDados)
        """
        try:
            # 1. Registra PluginBybitConexao
            plugin_conexao = PluginBybitConexao(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
            )
            
            if not self.gerenciador_plugins.registrar_plugin(plugin_conexao):
                print("[SmartTrader] ERRO: Falha ao registrar PluginBybitConexao")
                return False
            print("[SmartTrader] PluginBybitConexao registrado")
            
            # 2. Registra PluginBancoDados
            from plugins.plugin_banco_dados import PluginBancoDados
            
            plugin_banco_dados = PluginBancoDados(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
            )
            
            if not self.gerenciador_plugins.registrar_plugin(plugin_banco_dados):
                print("[SmartTrader] ERRO: Falha ao registrar PluginBancoDados")
                return False
            print("[SmartTrader] PluginBancoDados registrado")
            
            # 3. Registra PluginDadosVelas e conecta com PluginBybitConexao e PluginBancoDados
            plugin_dados_velas = PluginDadosVelas(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
            )
            
            if not self.gerenciador_plugins.registrar_plugin(plugin_dados_velas):
                print("[SmartTrader] ERRO: Falha ao registrar PluginDadosVelas")
                return False
            
            # Conecta PluginDadosVelas com PluginBybitConexao e PluginBancoDados
            plugin_dados_velas.definir_plugin_conexao(plugin_conexao)
            plugin_dados_velas.definir_plugin_banco_dados(plugin_banco_dados)
            
            # Configura callback para processamento incremental
            def callback_par_processado(par: str, dados_par: Dict[str, Any]):
                """Callback chamado quando um par é processado - analisa imediatamente"""
                try:
                    # Processa indicadores para este par específico
                    dados_entrada_par = {par: dados_par}
                    self._processar_indicadores_par(dados_entrada_par)
                except Exception as e:
                    logger = self.gerenciador_log.get_logger("SmartTrader", "system")
                    logger.error(
                        f"[SmartTrader] Erro no callback de par processado para {par}: {e}",
                        exc_info=True
                    )
            
            plugin_dados_velas.definir_callback_par_processado(callback_par_processado)
            print("[SmartTrader] PluginDadosVelas registrado e conectado (processamento incremental ativado)")
            
            # 4. Registra os 8 plugins de indicadores técnicos
            indicadores = [
                ("PluginIchimoku", PluginIchimoku),
                ("PluginSupertrend", PluginSupertrend),
                ("PluginBollinger", PluginBollinger),
                ("PluginVolume", PluginVolume),
                ("PluginEma", PluginEma),
                ("PluginMacd", PluginMacd),
                ("PluginRsi", PluginRsi),
                ("PluginVwap", PluginVwap),
            ]
            
            for nome, classe_plugin in indicadores:
                plugin = classe_plugin(
                    gerenciador_log=self.gerenciador_log,
                    gerenciador_banco=self.gerenciador_banco,
                    config=self.config,
                )
                
                if not self.gerenciador_plugins.registrar_plugin(plugin):
                    print(f"[SmartTrader] ERRO: Falha ao registrar {nome}")
                    return False
                
                # Conecta com PluginDadosVelas
                plugin.definir_plugin_dados_velas(plugin_dados_velas)
                print(f"[SmartTrader] {nome} registrado e conectado")
            
            return True
            
        except Exception as e:
            print(f"[SmartTrader] ERRO ao registrar plugins: {e}")
            if self.gerenciador_log:
                self.gerenciador_log.log_erro_critico(
                    "SmartTrader",
                    f"Erro ao registrar plugins: {e}",
                    detalhes={"erro": str(e)}
                )
            return False

    def executar(self):
        """Executa o ciclo principal do sistema."""
        try:
            if not self._validar_inicializacao():
                return

            self._em_execucao = True
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")

            logger.info("[SmartTrader] Iniciando ciclo de execução...")

            # Por enquanto apenas estrutura - será expandido quando plugins
            # de indicadores estiverem implementados
            ciclo_interval = self.config.get("bot", {}).get("cycle_interval", 5)

            logger.info(
                f"[SmartTrader] Sistema pronto. "
                f"Ciclo de execução configurado para {ciclo_interval}s"
            )
            
            # Ciclo principal de execução
            import time
            while self._em_execucao:
                try:
                    # Verifica se cancelamento foi solicitado
                    if not self._em_execucao:
                        break
                    
                    # Executa todos os plugins registrados
                    resultados = self.gerenciador_plugins.executar_plugins()
                    
                    # Log dos resultados
                    if resultados:
                        status = resultados.get("status", "unknown")
                        executados = resultados.get("total_executados", 0)
                        erros = resultados.get("total_erros", 0)
                        
                        if status == "ok":
                            logger.debug(
                                f"[SmartTrader] Ciclo executado com sucesso. "
                                f"Plugins processados: {executados}/{resultados.get('total_plugins', 0)}"
                            )
                        elif status == "erro_parcial":
                            logger.warning(
                                f"[SmartTrader] Ciclo executado com erros parciais. "
                                f"Sucesso: {executados}, Erros: {erros}"
                            )
                        else:
                            logger.error(
                                f"[SmartTrader] Erro no ciclo. "
                                f"Erros: {erros}, Sucesso: {executados}"
                            )
                    
                    # Agrega resultados dos indicadores e valida entrada
                    if resultados and self.gerenciador_bot:
                        # resultados vem do executar_plugins que retorna {"resultados": {...}}
                        resultados_plugins = resultados.get("resultados", resultados)
                        self._processar_indicadores_e_validar(resultados_plugins)
                    
                    # Aguarda próximo ciclo
                    time.sleep(ciclo_interval)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(
                        f"[SmartTrader] Erro no ciclo de execução: {e}",
                        exc_info=True
                    )
                    time.sleep(ciclo_interval)  # Continua mesmo com erro

        except KeyboardInterrupt:
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            logger.info("[SmartTrader] Interrompido pelo usuário")
        except Exception as e:
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            logger.critical(
                f"[SmartTrader] Erro crítico na execução: {e}", exc_info=True
            )

    def _processar_indicadores_par(self, dados_par: Dict[str, Any]):
        """
        Processa indicadores para um par específico em paralelo (processamento incremental).
        Consolida resultados em um único log INFO.
        
        Args:
            dados_par: Dados de um par específico {par: dados_par}
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        try:
            # Extrai o nome do par
            par = list(dados_par.keys())[0] if dados_par else "UNKNOWN"
            
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            
            # Obtém lista de plugins de indicadores
            indicadores_plugins = [
                "PluginIchimoku",
                "PluginSupertrend",
                "PluginBollinger",
                "PluginVolume",
                "PluginEma",
                "PluginMacd",
                "PluginRsi",
                "PluginVwap",
            ]
            
            resultados_indicadores = {}
            
            # Executa todos os indicadores em paralelo
            def executar_indicador(nome_plugin: str):
                """Executa um indicador e retorna resultado"""
                try:
                    plugin = self.gerenciador_plugins.obter_plugin(nome_plugin)
                    if not plugin:
                        return (nome_plugin, None)
                    
                    resultado = plugin.executar(dados_entrada=dados_par)
                    return (nome_plugin, resultado)
                except Exception as e:
                    logger.error(
                        f"[{par} | {nome_plugin}] ERROR — Falha no cálculo: {e}",
                        exc_info=True
                    )
                    return (nome_plugin, None)
            
            # Executa indicadores em paralelo
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {executor.submit(executar_indicador, nome): nome 
                          for nome in indicadores_plugins}
                
                for future in as_completed(futures):
                    nome_plugin, resultado = future.result()
                    if resultado and resultado.get("status") == "ok":
                        resultados_indicadores[nome_plugin] = resultado
            
            # Consolida resultados e loga apenas um resultado final
            if resultados_indicadores:
                self._consolidar_e_logar_resultado_par(par, resultados_indicadores)
                
                # Valida entrada com resultados dos indicadores
                if self.gerenciador_bot:
                    self._processar_indicadores_e_validar(resultados_indicadores, par=par)
        
        except Exception as e:
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            logger.error(
                f"[SmartTrader] Erro ao processar indicadores incrementalmente: {e}",
                exc_info=True
            )
    
    def _consolidar_e_logar_resultado_par(self, par: str, resultados_indicadores: Dict[str, Any]):
        """
        Consolida resultados dos indicadores e loga um único resultado INFO.
        
        Args:
            par: Nome do par (ex: DOTUSDT)
            resultados_indicadores: Resultados de cada indicador
        """
        try:
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            
            # Mapeamento de nomes de plugins para nomes curtos
            nomes_curtos = {
                "PluginIchimoku": "Ichimoku",
                "PluginSupertrend": "Supertrend",
                "PluginBollinger": "Bollinger",
                "PluginVolume": "Volume",
                "PluginEma": "EMA",
                "PluginMacd": "MACD",
                "PluginRsi": "RSI",
                "PluginVwap": "VWAP",
            }
            
            # Conta sinais LONG e SHORT por indicador (consolida por par, não por timeframe)
            contagem_long = 0
            contagem_short = 0
            indicadores_long = []
            indicadores_short = []
            
            for nome_plugin, resultado in resultados_indicadores.items():
                dados = resultado.get("dados", {})
                par_data = dados.get(par, {})
                
                # Verifica se há sinal LONG ou SHORT em qualquer timeframe para este indicador
                tem_long = False
                tem_short = False
                
                for tf, tf_data in par_data.items():
                    if isinstance(tf_data, dict):
                        if tf_data.get("long", False):
                            tem_long = True
                        if tf_data.get("short", False):
                            tem_short = True
                
                # Conta apenas uma vez por indicador (não por timeframe)
                if tem_long:
                    contagem_long += 1
                    nome_curto = nomes_curtos.get(nome_plugin, nome_plugin)
                    if nome_curto not in indicadores_long:
                        indicadores_long.append(nome_curto)
                
                if tem_short:
                    contagem_short += 1
                    nome_curto = nomes_curtos.get(nome_plugin, nome_plugin)
                    if nome_curto not in indicadores_short:
                        indicadores_short.append(nome_curto)
            
            # Determina direção principal
            if contagem_long > contagem_short:
                direcao = "LONG"
                contagem = contagem_long
                indicadores = indicadores_long
            elif contagem_short > contagem_long:
                direcao = "SHORT"
                contagem = contagem_short
                indicadores = indicadores_short
            else:
                direcao = "NEUTRO"
                contagem = 0
                indicadores = []
            
            # Log único consolidado
            if contagem > 0:
                logger.info(
                    f"[PAIR {par}] Resultados: {contagem_long} LONG, {contagem_short} SHORT — "
                    f"indicadores: {', '.join(indicadores) if indicadores else 'nenhum'}"
                )
            else:
                logger.info(
                    f"[PAIR {par}] Resultados: {contagem_long} LONG, {contagem_short} SHORT — sem sinais"
                )
        
        except Exception as e:
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            logger.error(
                f"[PAIR {par}] ERROR — Falha ao consolidar resultados: {e}",
                exc_info=True
            )
    
    def _processar_indicadores_e_validar(self, resultados_plugins: Dict[str, Any], par: Optional[str] = None):
        """
        Processa resultados dos plugins de indicadores e valida entrada.
        
        Args:
            resultados_plugins: Resultados da execução dos plugins
            par: Nome do par sendo processado (opcional, para logs)
        """
        try:
            # Mapeamento dos nomes dos plugins para chaves de indicadores
            mapeamento_indicadores = {
                "PluginIchimoku": "ichimoku",
                "PluginSupertrend": "supertrend",
                "PluginBollinger": "bollinger",
                "PluginVolume": "volume",
                "PluginEma": "ema",
                "PluginMacd": "macd",
                "PluginRsi": "rsi",
                "PluginVwap": "vwap",
            }
            
            # Agrega resultados por par/timeframe
            resultados_por_par_tf = {}
            
            for nome_plugin, resultado in resultados_plugins.items():
                if nome_plugin not in mapeamento_indicadores:
                    continue
                
                chave_indicador = mapeamento_indicadores[nome_plugin]
                
                if not isinstance(resultado, dict) or resultado.get("status") != "ok":
                    continue
                
                dados = resultado.get("dados", {})
                if not isinstance(dados, dict):
                    continue
                
                # Processa cada par e timeframe
                for symbol, dados_par in dados.items():
                    if not isinstance(dados_par, dict):
                        continue
                    
                    if symbol not in resultados_por_par_tf:
                        resultados_por_par_tf[symbol] = {}
                    
                    for timeframe, dados_tf in dados_par.items():
                        if not isinstance(dados_tf, dict):
                            continue
                        
                        if timeframe not in resultados_por_par_tf[symbol]:
                            resultados_por_par_tf[symbol][timeframe] = {
                                "par": symbol,
                                "timeframe": timeframe,
                            }
                        
                        # Adiciona resultado do indicador
                        resultados_por_par_tf[symbol][timeframe][chave_indicador] = {
                            "long": dados_tf.get("long", False),
                            "short": dados_tf.get("short", False),
                        }
            
            # Valida entrada para cada par/timeframe
            for symbol, dados_par in resultados_por_par_tf.items():
                for timeframe, resultados_indicadores in dados_par.items():
                    if self.gerenciador_bot:
                        # Passa o par para validação (usa symbol como par)
                        validacao = self.gerenciador_bot.validar_entrada(resultados_indicadores, par=symbol)
                        
                        # Log já é feito dentro de validar_entrada quando há sinal válido
        
        except Exception as e:
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            logger.error(
                f"[SmartTrader] Erro ao processar indicadores: {e}",
                exc_info=True
            )
    
    def _validar_inicializacao(self) -> bool:
        """Valida se todos os componentes foram inicializados."""
        if not all(
            [
                self.config,
                self.gerenciador_log,
                self.gerenciador_banco,
                self.gerenciador_plugins,
                self.gerenciador_bot,
            ]
        ):
            print("[SmartTrader] ERRO: Sistema não inicializado completamente")
            return False
        return True

    def finalizar(self):
        """Finaliza o sistema de forma segura."""
        try:
            self._em_execucao = False

            logger = None
            if self.gerenciador_log:
                logger = self.gerenciador_log.get_logger("SmartTrader", "bot")

            if logger:
                logger.info("[SmartTrader] Finalizando sistema...")

            # Finaliza na ordem reversa
            if self.gerenciador_bot:
                self.gerenciador_bot.finalizar()

            if self.gerenciador_plugins:
                self.gerenciador_plugins.finalizar()

            if self.gerenciador_banco:
                self.gerenciador_banco.finalizar()

            if logger:
                logger.info("[SmartTrader] Sistema finalizado com sucesso")

            print("[SmartTrader] Sistema finalizado")

        except Exception as e:
            print(f"[SmartTrader] ERRO ao finalizar: {e}")
            if self.gerenciador_log:
                self.gerenciador_log.log_erro_critico(
                    "SmartTrader", f"Erro na finalização: {e}"
                )


def main():
    """Função principal."""
    watcher = SmartTrader()

    # Handler para SIGINT (Ctrl+C)
    def signal_handler(sig, frame):
        print("\n[SmartTrader] Recebido sinal de interrupção...")
        # Marca sistema para parar
        watcher._em_execucao = False
        
        # Solicita cancelamento em todos os plugins
        if watcher.gerenciador_plugins:
            for nome_plugin, plugin in watcher.gerenciador_plugins.plugins.items():
                try:
                    plugin.solicitar_cancelamento()
                except Exception as e:
                    print(f"[SmartTrader] Erro ao solicitar cancelamento em {nome_plugin}: {e}")
        
        # Aguarda um pouco para requisições em andamento terminarem
        import time
        time.sleep(0.5)
        
        # Finaliza sistema
        watcher.finalizar()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Inicializa e executa
    if watcher.inicializar():
        try:
            watcher.executar()
        finally:
            # Finaliza ao sair (se não foi finalizado pelo signal handler)
            if watcher._em_execucao:  # Se ainda está em execução, finaliza
                watcher.finalizar()
    else:
        print("[SmartTrader] Falha na inicialização. Encerrando...")
        sys.exit(1)


if __name__ == "__main__":
    main()
