"""
Gerenciador de Logs do sistema.

Centraliza todo o sistema de logging com:
- Formatação padronizada
- Rotação de arquivos por data
- Organização por tipo (bot, banco, sinais, etc.)
- Níveis de log configuráveis
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler


class GerenciadorLog:
    """
    Gerenciador centralizado de logs do sistema.
    
    Organiza logs em diretórios por tipo:
    - logs/bot/      : Logs do bot principal
    - logs/banco/    : Logs de operações de banco
    - logs/dados/    : Logs de processamento de dados
    - logs/sinais/   : Logs de sinais de trading
    - logs/erros/    : Logs de erros críticos
    - logs/rastreamento/: Logs de rastreamento geral
    
    Attributes:
        base_path (Path): Caminho base do diretório de logs
        loggers (dict): Cache de loggers criados
        formato_padrao (str): Formato padrão dos logs
    """

    def __init__(self, base_path: str = "logs"):
        """
        Inicializa o GerenciadorLog.
        
        Args:
            base_path: Caminho base do diretório de logs
        """
        self.base_path = Path(base_path)
        self.loggers: dict = {}
        self.formato_padrao = (
            "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
        )
        self.data_format = "%d-%m-%Y %H:%M:%S"
        
        # Cria diretórios de log se não existirem
        self._criar_estrutura_diretorios()

    def _criar_estrutura_diretorios(self):
        """Cria a estrutura de diretórios de log conforme padrão."""
        diretorios = [
            "bot",
            "banco",
            "dados",
            "sinais",
            "erros",
            "rastreamento",
        ]
        
        for diretorio in diretorios:
            caminho = self.base_path / diretorio
            caminho.mkdir(parents=True, exist_ok=True)

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
        # Cache key único por nome e tipo
        cache_key = f"{nome}_{tipo_log}"
        
        if cache_key in self.loggers:
            return self.loggers[cache_key]
        
        # Cria novo logger
        logger = logging.getLogger(cache_key)
        logger.setLevel(nivel)
        
        # Remove handlers existentes (evita duplicação)
        logger.handlers.clear()
        
        # Handler para arquivo específico por tipo
        arquivo_log = self._obter_caminho_arquivo(tipo_log)
        file_handler = RotatingFileHandler(
            arquivo_log,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(nivel)
        file_formatter = logging.Formatter(
            self.formato_padrao, datefmt=self.data_format
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Handler para console (opcional, apenas INFO e acima)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            self.formato_padrao, datefmt=self.data_format
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # Evita propagação para logger raiz
        logger.propagate = False
        
        # Adiciona ao cache
        self.loggers[cache_key] = logger
        
        return logger

    def _obter_caminho_arquivo(self, tipo_log: str) -> Path:
        """
        Obtém o caminho do arquivo de log para o tipo especificado.
        
        Args:
            tipo_log: Tipo de log (bot, banco, dados, sinais, erros, rastreamento)
            
        Returns:
            Path: Caminho completo do arquivo de log
        """
        data_atual = datetime.now().strftime("%d-%m-%Y")
        
        # Mapeia tipo_log para nome de arquivo
        nomes_arquivo = {
            "bot": f"bot_{data_atual}.log",
            "banco": f"banco_{data_atual}.log",
            "dados": f"dados_{data_atual}.log",
            "sinais": f"sinais_{data_atual}.log",
            "erros": f"erros_{data_atual}.log",
            "rastreamento": f"rastreamento_{data_atual}.log",
        }
        
        nome_arquivo = nomes_arquivo.get(tipo_log, f"{tipo_log}_{data_atual}.log")
        diretorio = self.base_path / tipo_log if tipo_log != "erros" else self.base_path / "erros"
        
        return diretorio / nome_arquivo

    def log_erro_critico(
        self, plugin_name: str, mensagem: str, exc_info: bool = True
    ):
        """
        Registra um erro crítico no log de erros.
        
        Args:
            plugin_name: Nome do plugin que gerou o erro
            mensagem: Mensagem de erro
            exc_info: Se True, inclui stack trace completo
        """
        logger_erros = self.get_logger("ERROS_SISTEMA", "erros", logging.ERROR)
        logger_erros.critical(
            f"[{plugin_name}] [CRITICAL] {mensagem}", exc_info=exc_info
        )

