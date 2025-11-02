"""
Gerenciadores do sistema.

Contém os gerenciadores principais:
- GerenciadorLog: Sistema de logs
- GerenciadorBanco: Persistência de dados
- GerenciadorPlugins: Orquestração de plugins
- GerenciadorBot: Controle de trades
"""

# Imports com lazy loading para evitar dependências circulares
__all__ = [
    "GerenciadorLog",
    "GerenciadorBanco",
    "GerenciadorPlugins",
    "GerenciadorBot",
    "GerenciadorBase",
]

