"""
Plugins de indicadores técnicos.

Contém os 8 indicadores do sistema 6/8:
1. Ichimoku Cloud (plugin_ichimoku.py)
2. Supertrend (plugin_supertrend.py)
3. Bollinger Bands + Squeeze (plugin_bollinger.py)
4. Volume + Breakout (plugin_volume.py)
5. EMA Crossover (plugin_ema.py)
6. MACD (plugin_macd.py)
7. RSI (plugin_rsi.py)
8. VWAP (plugin_vwap.py)

E plugins de dados e validação:
- PluginDadosVelas (plugin_dados_velas.py)
"""

from plugins.indicadores.plugin_dados_velas import PluginDadosVelas

__all__ = ["PluginDadosVelas"]

