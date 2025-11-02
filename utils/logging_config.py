"""
Configuração de logging para uso em módulos isolados.

Fornece função get_logger() para inicialização rápida de loggers
antes do GerenciadorLog estar disponível.
"""

import logging
from pathlib import Path


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Cria um logger básico para uso antes do GerenciadorLog estar disponível.
    
    Args:
        name: Nome do módulo/componente
        level: Nível de log (padrão: INFO)
        
    Returns:
        logging.Logger: Logger configurado
    """
    logger = logging.getLogger(name)
    
    # Evita adicionar handlers múltiplos vezes
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Handler para console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%d-%m-%Y %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Evita propagação para logger raiz
    logger.propagate = False
    
    return logger

