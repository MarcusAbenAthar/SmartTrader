"""
Ponto de entrada principal do sistema Smart_Trader.

Orquestra inicialização e execução dos gerenciadores e plugins.
Sistema 6/8 - Trading Bot com 8 indicadores técnicos.
"""

import sys
import signal
from typing import Optional
from plugins.gerenciadores.gerenciador_log import GerenciadorLog
from plugins.gerenciadores.gerenciador_banco import GerenciadorBanco
from plugins.gerenciadores.gerenciador_plugins import GerenciadorPlugins
from plugins.gerenciadores.gerenciador_bot import GerenciadorBot
from plugins.conexoes.plugin_bybit_conexao import PluginBybitConexao
from plugins.indicadores.plugin_dados_velas import PluginDadosVelas
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
            from plugins.gerenciadores.plugin_banco_dados import PluginBancoDados
            
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
            print("[SmartTrader] PluginDadosVelas registrado e conectado")
            
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
        watcher.finalizar()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Inicializa e executa
    if watcher.inicializar():
        watcher.executar()
    else:
        print("[SmartTrader] Falha na inicialização. Encerrando...")
        sys.exit(1)

    # Finaliza ao sair
    watcher.finalizar()


if __name__ == "__main__":
    main()
