"""
Classe base para gerenciadores do sistema.

Fornece interface comum e padrões de inicialização/finalização.
"""

from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime


class GerenciadorBase(ABC):
    """
    Classe base abstrata para todos os gerenciadores do sistema.
    
    Define o ciclo de vida padrão: inicializar -> executar -> finalizar.
    Todos os gerenciadores devem herdar desta classe e implementar os métodos abstratos.
    
    Attributes:
        GERENCIADOR_NAME (str): Nome único do gerenciador (deve ser sobrescrito)
        _inicializado (bool): Flag indicando se o gerenciador foi inicializado
        _em_execucao (bool): Flag indicando se o gerenciador está em execução
    """

    GERENCIADOR_NAME: str = "GerenciadorBase"

    def __init__(self):
        """Inicializa o gerenciador base."""
        self._inicializado: bool = False
        self._em_execucao: bool = False
        self._timestamp_inicio: Optional[datetime] = None

    @abstractmethod
    def inicializar(self) -> bool:
        """
        Inicializa o gerenciador e prepara recursos.
        
        Returns:
            bool: True se inicializado com sucesso, False caso contrário.
        """
        pass

    @abstractmethod
    def executar(self, *args, **kwargs):
        """
        Executa a lógica principal do gerenciador.
        
        Args:
            *args: Argumentos posicionais variáveis
            **kwargs: Argumentos nomeados variáveis
            
        Returns:
            Resultado da execução (tipo depende da implementação)
        """
        pass

    @abstractmethod
    def finalizar(self) -> bool:
        """
        Finaliza o gerenciador e libera recursos.
        
        Returns:
            bool: True se finalizado com sucesso, False caso contrário.
        """
        pass

    @property
    def esta_inicializado(self) -> bool:
        """Verifica se o gerenciador está inicializado."""
        return self._inicializado

    @property
    def esta_em_execucao(self) -> bool:
        """Verifica se o gerenciador está em execução."""
        return self._em_execucao

    def __enter__(self):
        """Context manager: inicializa ao entrar."""
        if not self._inicializado:
            self.inicializar()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: finaliza ao sair."""
        if self._inicializado:
            self.finalizar()
        return False  # Não suprime exceções

