"""
Helper centralizado para barras de progresso usando Rich.
Reduz verbosidade e melhora UX visual.
"""

from typing import Optional, Any
from contextlib import contextmanager
import sys

try:
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
    from rich.console import Console
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class ProgressHelper:
    """Helper para gerenciar barras de progresso."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and RICH_AVAILABLE
        self.console = Console() if self.enabled else None
        self._current_progress: Optional[Progress] = None
        self._current_task = None
    
    @contextmanager
    def progress_bar(self, total: int, description: str = "Processando"):
        """
        Context manager para barra de progresso.
        
        Args:
            total: Total de itens a processar
            description: Descrição da operação
        """
        if not self.enabled:
            yield None
            return
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("•"),
                TextColumn("[cyan]{task.completed}/{task.total}"),
                TextColumn("•"),
                TimeElapsedColumn(),
                TextColumn("•"),
                TimeRemainingColumn(),
                console=self.console,
                transient=False
            ) as progress:
                self._current_progress = progress
                task = progress.add_task(description, total=total)
                self._current_task = task
                yield task
        finally:
            self._current_progress = None
            self._current_task = None
    
    def update(self, advance: int = 1, description: Optional[str] = None):
        """Atualiza a barra de progresso atual."""
        if not self.enabled or not self._current_progress or not self._current_task:
            return
        
        self._current_progress.update(
            self._current_task,
            advance=advance,
            description=description
        )
    
    def set_total(self, total: int):
        """Define o total da barra de progresso atual."""
        if not self.enabled or not self._current_progress or not self._current_task:
            return
        
        self._current_progress.update(self._current_task, total=total)
    
    def print(self, *args, **kwargs):
        """Print usando rich console se disponível."""
        if self.enabled and self.console:
            self.console.print(*args, **kwargs)
        else:
            print(*args, **kwargs)


# Instância global
_progress_helper = ProgressHelper()


def get_progress_helper() -> ProgressHelper:
    """Retorna a instância global do helper de progresso."""
    return _progress_helper


def disable_progress():
    """Desabilita barras de progresso (útil para testes ou logs)."""
    _progress_helper.enabled = False


def enable_progress():
    """Habilita barras de progresso."""
    _progress_helper.enabled = RICH_AVAILABLE

