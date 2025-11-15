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
from plugins.indicadores.plugin_ichimoku import PluginIchimoku
from plugins.indicadores.plugin_supertrend import PluginSupertrend
from plugins.indicadores.plugin_bollinger import PluginBollinger
from plugins.indicadores.plugin_volume import PluginVolume
from plugins.indicadores.plugin_ema import PluginEma
from plugins.indicadores.plugin_macd import PluginMacd
from plugins.indicadores.plugin_rsi import PluginRsi
from plugins.indicadores.plugin_vwap import PluginVwap

__all__ = [
    "PluginDadosVelas",
    "PluginIchimoku",
    "PluginSupertrend",
    "PluginBollinger",
    "PluginVolume",
    "PluginEma",
    "PluginMacd",
    "PluginRsi",
    "PluginVwap",
]

