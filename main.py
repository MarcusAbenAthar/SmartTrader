"""
Ponto de entrada principal do sistema Bybit_Watcher.

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
from utils.main_config import carregar_config


class BybitWatcher:
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
            print("[BybitWatcher] Inicializando sistema...")

            # 1. Carrega configuração
            self.config = carregar_config()
            print("[BybitWatcher] Configuração carregada")

            # 2. Inicializa GerenciadorLog
            self.gerenciador_log = GerenciadorLog(base_path="logs")
            if not self.gerenciador_log.inicializar():
                print("[BybitWatcher] ERRO: Falha ao inicializar GerenciadorLog")
                return False
            print("[BybitWatcher] GerenciadorLog inicializado")

            # 3. Inicializa GerenciadorBanco
            self.gerenciador_banco = GerenciadorBanco(
                gerenciador_log=self.gerenciador_log,
                schema_path=self.config.get("db", {}).get("schema_path", "utils/schema.json"),
            )
            if not self.gerenciador_banco.inicializar():
                print("[BybitWatcher] ERRO: Falha ao inicializar GerenciadorBanco")
                return False
            print("[BybitWatcher] GerenciadorBanco inicializado")

            # 4. Inicializa GerenciadorPlugins
            self.gerenciador_plugins = GerenciadorPlugins(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
            )
            if not self.gerenciador_plugins.inicializar():
                print("[BybitWatcher] ERRO: Falha ao inicializar GerenciadorPlugins")
                return False
            print("[BybitWatcher] GerenciadorPlugins inicializado")

            # 5. Inicializa GerenciadorBot
            self.gerenciador_bot = GerenciadorBot(
                gerenciador_log=self.gerenciador_log,
                config=self.config,
            )
            if not self.gerenciador_bot.inicializar():
                print("[BybitWatcher] ERRO: Falha ao inicializar GerenciadorBot")
                return False
            print("[BybitWatcher] GerenciadorBot inicializado")

            print("[BybitWatcher] Sistema inicializado com sucesso!")
            return True

        except Exception as e:
            print(f"[BybitWatcher] ERRO CRÍTICO na inicialização: {e}")
            if self.gerenciador_log:
                self.gerenciador_log.log_erro_critico(
                    "BybitWatcher", f"Erro na inicialização: {e}"
                )
            return False

    def executar(self):
        """Executa o ciclo principal do sistema."""
        try:
            if not self._validar_inicializacao():
                return

            self._em_execucao = True
            logger = self.gerenciador_log.get_logger("BybitWatcher", "bot")

            logger.info("[BybitWatcher] Iniciando ciclo de execução...")

            # Por enquanto apenas estrutura - será expandido quando plugins
            # de indicadores estiverem implementados
            ciclo_interval = self.config.get("bot", {}).get("cycle_interval", 5)

            logger.info(
                f"[BybitWatcher] Sistema pronto. "
                f"Ciclo de execução configurado para {ciclo_interval}s"
            )
            logger.info(
                "[BybitWatcher] Aguardando implementação dos plugins de indicadores..."
            )

            # TODO: Implementar loop principal quando plugins estiverem prontos
            # while self._em_execucao:
            #     resultados = self.gerenciador_plugins.executar_plugins()
            #     validacao = self.gerenciador_bot.validar_entrada(resultados)
            #     if validacao["valido"]:
            #         # Executa trade...
            #     time.sleep(ciclo_interval)

        except KeyboardInterrupt:
            logger = self.gerenciador_log.get_logger("BybitWatcher", "bot")
            logger.info("[BybitWatcher] Interrompido pelo usuário")
        except Exception as e:
            logger = self.gerenciador_log.get_logger("BybitWatcher", "bot")
            logger.critical(
                f"[BybitWatcher] Erro crítico na execução: {e}", exc_info=True
            )

    def _validar_inicializacao(self) -> bool:
        """Valida se todos os componentes foram inicializados."""
        if not all([
            self.config,
            self.gerenciador_log,
            self.gerenciador_banco,
            self.gerenciador_plugins,
            self.gerenciador_bot,
        ]):
            print("[BybitWatcher] ERRO: Sistema não inicializado completamente")
            return False
        return True

    def finalizar(self):
        """Finaliza o sistema de forma segura."""
        try:
            self._em_execucao = False

            logger = None
            if self.gerenciador_log:
                logger = self.gerenciador_log.get_logger("BybitWatcher", "bot")

            if logger:
                logger.info("[BybitWatcher] Finalizando sistema...")

            # Finaliza na ordem reversa
            if self.gerenciador_bot:
                self.gerenciador_bot.finalizar()

            if self.gerenciador_plugins:
                self.gerenciador_plugins.finalizar()

            if self.gerenciador_banco:
                self.gerenciador_banco.finalizar()

            if logger:
                logger.info("[BybitWatcher] Sistema finalizado com sucesso")

            print("[BybitWatcher] Sistema finalizado")

        except Exception as e:
            print(f"[BybitWatcher] ERRO ao finalizar: {e}")
            if self.gerenciador_log:
                self.gerenciador_log.log_erro_critico(
                    "BybitWatcher", f"Erro na finalização: {e}"
                )


def main():
    """Função principal."""
    watcher = BybitWatcher()

    # Handler para SIGINT (Ctrl+C)
    def signal_handler(sig, frame):
        print("\n[BybitWatcher] Recebido sinal de interrupção...")
        watcher.finalizar()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Inicializa e executa
    if watcher.inicializar():
        watcher.executar()
    else:
        print("[BybitWatcher] Falha na inicialização. Encerrando...")
        sys.exit(1)

    # Finaliza ao sair
    watcher.finalizar()


if __name__ == "__main__":
    main()

