"""
Plugins do sistema Bybit_Watcher.

Este pacote contém todos os plugins organizados em:
- indicadores: Plugins de indicadores técnicos
- gerenciadores: Plugins de gerenciamento do sistema
"""

__version__ = "1.0.0"

# Exporta componentes principais para uso facilitado
from plugins.base_plugin import Plugin, execucao_segura

__all__ = [
    "Plugin",
    "execucao_segura",
]

