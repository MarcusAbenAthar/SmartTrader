"""
Plugin VWAP (Volume Weighted Average Price) - Sistema Smart Trader.

Calcula VWAP (intraday - reset 00:00 UTC) e retorna sinais LONG/SHORT conforme estratégia:
- LONG: Preço ≤ VWAP × 1.003 (≤ +0.3%)
- SHORT: Preço ≥ VWAP × 0.997 (≥ -0.3%)

__institucional__ = "Smart_Trader Plugin VWAP - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np
import pytz

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginVwap(Plugin):
    """
    Plugin de cálculo de VWAP (Volume Weighted Average Price).
    
    Responsabilidades:
    - Calcular VWAP intraday (reset 00:00 UTC) para cada par/timeframe
    - Retornar sinais LONG/SHORT baseados em proximidade do VWAP
    """
    
    __institucional__ = "Smart_Trader Plugin VWAP - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginVwap"
    plugin_versao = "v1.0.0"
    plugin_schema_versao = "v1.0.0"
    plugin_tipo = TipoPlugin.INDICADOR
    
    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLogProtocol] = None,
        gerenciador_banco: Optional[GerenciadorBancoProtocol] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(gerenciador_log, gerenciador_banco, config)
        
        config_vwap = self.config.get("indicadores", {}).get("vwap", {})
        self.tolerancia_percentual = config_vwap.get("tolerancia_percentual", 0.003)  # 0.3%
        
        self.plugin_dados_velas = None
        self.timezone_utc = pytz.UTC
    
    def definir_plugin_dados_velas(self, plugin_dados_velas):
        self.plugin_dados_velas = plugin_dados_velas
    
    def _inicializar_interno(self) -> bool:
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Inicializado. "
                    f"VWAP intraday (reset 00:00 UTC), Tolerância: ±{self.tolerancia_percentual*100:.1f}%"
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro na inicialização: {e}", exc_info=True)
            return False
    
    def _calcular_vwap(self, df: pd.DataFrame) -> pd.Series:
        """
        Calcula VWAP com reset diário (00:00 UTC).
        
        Args:
            df: DataFrame com colunas timestamp, high, low, close, volume
        
        Returns:
            pd.Series: Valores de VWAP
        """
        # Converte timestamps para datetime UTC
        timestamps = pd.to_datetime(df["timestamp"], unit='ms', utc=True)
        df_with_dates = df.copy()
        df_with_dates["date_utc"] = timestamps.dt.date
        
        # Calcula preço típico (HLC/3)
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        
        # Calcula VWAP por dia
        vwap = pd.Series(index=df.index, dtype=float)
        
        # Agrupa por data e calcula VWAP acumulado por dia
        for date in df_with_dates["date_utc"].unique():
            mask = df_with_dates["date_utc"] == date
            df_day = df_with_dates[mask]
            
            if len(df_day) == 0:
                continue
            
            # VWAP = Σ(Preço Típico × Volume) / Σ(Volume)
            typical_price_day = typical_price[mask]
            volume_day = df["volume"][mask]
            
            pv = (typical_price_day * volume_day).cumsum()
            v = volume_day.cumsum()
            
            vwap_day = pv / v
            vwap[mask] = vwap_day
        
        return vwap
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] ▶ Iniciando execução do indicador VWAP")
            
            if self.cancelamento_solicitado():
                if self.logger:
                    self.logger.debug(f"[{self.PLUGIN_NAME}] Cancelamento solicitado")
                return {"status": StatusExecucao.CANCELADO.value, "mensagem": "Cancelamento solicitado"}
            
            # Obtém dados de velas
            if not dados_entrada and self.plugin_dados_velas:
                dados_velas = self.plugin_dados_velas.dados_completos.get("crus", {})
                if self.logger:
                    self.logger.debug(f"[{self.PLUGIN_NAME}] Dados obtidos do PluginDadosVelas: {len(dados_velas)} pares")
            elif dados_entrada:
                dados_velas = dados_entrada
                if self.logger:
                    self.logger.debug(f"[{self.PLUGIN_NAME}] Dados recebidos como entrada: {len(dados_velas)} pares")
            else:
                if self.logger:
                    self.logger.error(f"[{self.PLUGIN_NAME}] Dados de velas não disponíveis")
                return {"status": StatusExecucao.ERRO.value, "mensagem": "Dados de velas não disponíveis"}
            
            if not dados_velas:
                return {"status": StatusExecucao.ERRO.value, "mensagem": "Nenhum dado de vela encontrado"}
            
            resultados = {}
            
            for symbol, dados_par in dados_velas.items():
                if not isinstance(dados_par, dict):
                    continue
                
                resultados[symbol] = {}
                
                for timeframe, dados_tf in dados_par.items():
                    if not isinstance(dados_tf, dict) or "velas" not in dados_tf:
                        continue
                    
                    velas = dados_tf.get("velas", [])
                    if not velas or len(velas) < 2:
                        resultados[symbol][timeframe] = {
                            "vwap": None, "preco": None,
                            "long": False, "short": False,
                            "erro": "Velas insuficientes"
                        }
                        continue
                    
                    try:
                        df = pd.DataFrame(velas)
                        
                        vwap_series = self._calcular_vwap(df)
                        
                        vwap_atual = float(vwap_series.iloc[-1]) if not pd.isna(vwap_series.iloc[-1]) else None
                        preco_atual = float(df["close"].iloc[-1])
                        
                        # Determina sinais
                        long = False
                        short = False
                        
                        if vwap_atual is not None and vwap_atual > 0:
                            # Calcula distância percentual
                            distancia_percentual = (preco_atual - vwap_atual) / vwap_atual
                            
                            # LONG: Preço ≤ VWAP × 1.003 (≤ +0.3%)
                            if distancia_percentual <= self.tolerancia_percentual:
                                long = True
                            
                            # SHORT: Preço ≥ VWAP × 0.997 (≥ -0.3%)
                            if distancia_percentual >= -self.tolerancia_percentual:
                                short = True
                        
                        resultados[symbol][timeframe] = {
                            "vwap": vwap_atual,
                            "preco": preco_atual,
                            "distancia_percentual": (preco_atual - vwap_atual) / vwap_atual * 100 if vwap_atual and vwap_atual > 0 else None,
                            "long": long,
                            "short": short,
                        }
                        
                        if (long or short) and self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] {symbol} {timeframe}: "
                                f"Preço={preco_atual:.2f}, VWAP={vwap_atual:.2f}, "
                                f"Distância={resultados[symbol][timeframe]['distancia_percentual']:.2f}%, "
                                f"LONG={long}, SHORT={short}"
                            )
                    
                    except Exception as e:
                        if self.logger:
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] Erro ao calcular VWAP para {symbol} {timeframe}: {e}",
                                exc_info=True
                            )
                        resultados[symbol][timeframe] = {
                            "vwap": None, "preco": None,
                            "long": False, "short": False,
                            "erro": str(e)
                        }
            
            self.dados_completos["crus"] = dados_velas
            self.dados_completos["analisados"] = resultados
            
            if self.logger:
                total_pares = len(resultados)
                total_sinais_long = sum(1 for par_data in resultados.values() 
                                       for tf_data in par_data.values() 
                                       if isinstance(tf_data, dict) and tf_data.get("long", False))
                total_sinais_short = sum(1 for par_data in resultados.values() 
                                        for tf_data in par_data.values() 
                                        if isinstance(tf_data, dict) and tf_data.get("short", False))
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] ✓ Execução concluída: {total_pares} pares processados, "
                    f"{total_sinais_long} LONG, {total_sinais_short} SHORT"
                )
            
            return {
                "status": StatusExecucao.OK.value,
                "dados": resultados,
                "plugin": self.PLUGIN_NAME,
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro na execução: {e}", exc_info=True)
            return {"status": StatusExecucao.ERRO.value, "mensagem": f"Erro: {e}", "erro": str(e)}

