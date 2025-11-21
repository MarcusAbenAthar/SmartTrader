"""
Plugins de Inteligência Artificial do sistema Smart_Trader.

Contém plugins que utilizam IA/ML para análise e insights:
- plugin_ia: Análise inteligente com Groq API (2025) e suporte a trades automáticos
"""

from plugins.ia.plugin_ia import PluginIA

__all__ = ["PluginIA"]

