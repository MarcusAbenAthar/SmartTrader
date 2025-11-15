"""
Plugin Volume + Breakout - Sistema Smart Trader.

Calcula Volume + Breakout e retorna sinais LONG/SHORT conforme estratégia:
- LONG: Volume > 2.0 × média(20) E Preço > máxima(20)
- SHORT: Volume > 2.0 × média(20) E Preço < mínima(20)

__institucional__ = "Smart_Trader Plugin Volume - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginVolume(Plugin):
    """
    Plugin de cálculo de Volume + Breakout.
    
    Responsabilidades:
    - Calcular média de volume(20) e máximas/mínimas(20) para cada par/timeframe
    - Detectar breakouts com volume e retornar sinais LONG/SHORT
    """
    
    __institucional__ = "Smart_Trader Plugin Volume - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginVolume"
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
        
        config_volume = self.config.get("indicadores", {}).get("volume", {})
        self.periodo_media = config_volume.get("periodo_media", 20)
        self.multiplier_breakout = config_volume.get("multiplier_breakout", 2.0)
        self.periodo_maxima = config_volume.get("periodo_maxima", 20)
        
        self.plugin_dados_velas = None
    
    def definir_plugin_dados_velas(self, plugin_dados_velas):
        self.plugin_dados_velas = plugin_dados_velas
    
    def _inicializar_interno(self) -> bool:
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Inicializado. "
                    f"Volume > {self.multiplier_breakout}×média({self.periodo_media}), "
                    f"Breakout: Preço vs máx/mín({self.periodo_maxima})"
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro na inicialização: {e}", exc_info=True)
            return False
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] ▶ Iniciando execução do indicador Volume")
            
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
                    if not velas or len(velas) < max(self.periodo_media, self.periodo_maxima):
                        resultados[symbol][timeframe] = {
                            "volume_atual": None, "volume_media": None,
                            "preco_atual": None, "preco_maxima": None, "preco_minima": None,
                            "long": False, "short": False,
                            "erro": "Velas insuficientes"
                        }
                        continue
                    
                    try:
                        df = pd.DataFrame(velas)
                        
                        volume = pd.Series(df["volume"].values)
                        precos = pd.Series(df["close"].values)
                        high = pd.Series(df["high"].values)
                        low = pd.Series(df["low"].values)
                        
                        # Calcula média de volume
                        volume_media = volume.rolling(window=self.periodo_media).mean()
                        volume_atual = float(volume.iloc[-1])
                        volume_media_atual = float(volume_media.iloc[-1]) if not pd.isna(volume_media.iloc[-1]) else None
                        
                        # Calcula máximas e mínimas
                        preco_maxima = high.rolling(window=self.periodo_maxima).max()
                        preco_minima = low.rolling(window=self.periodo_maxima).min()
                        preco_maxima_atual = float(preco_maxima.iloc[-1]) if not pd.isna(preco_maxima.iloc[-1]) else None
                        preco_minima_atual = float(preco_minima.iloc[-1]) if not pd.isna(preco_minima.iloc[-1]) else None
                        preco_atual = float(precos.iloc[-1])
                        
                        # Determina sinais
                        long = False
                        short = False
                        
                        if all([volume_atual, volume_media_atual, preco_atual, preco_maxima_atual, preco_minima_atual]):
                            # Verifica se volume > 2.0 × média
                            volume_breakout = volume_atual > (self.multiplier_breakout * volume_media_atual)
                            
                            if volume_breakout:
                                # LONG: Volume > 2.0×média E Preço > máxima(20)
                                if preco_atual > preco_maxima_atual:
                                    long = True
                                
                                # SHORT: Volume > 2.0×média E Preço < mínima(20)
                                if preco_atual < preco_minima_atual:
                                    short = True
                        
                        resultados[symbol][timeframe] = {
                            "volume_atual": volume_atual,
                            "volume_media": volume_media_atual,
                            "volume_multiplier": (volume_atual / volume_media_atual) if volume_media_atual and volume_media_atual > 0 else None,
                            "preco_atual": preco_atual,
                            "preco_maxima": preco_maxima_atual,
                            "preco_minima": preco_minima_atual,
                            "long": long,
                            "short": short,
                        }
                        
                        if (long or short) and self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] {symbol} {timeframe}: "
                                f"Volume={volume_atual:.2f} ({resultados[symbol][timeframe]['volume_multiplier']:.2f}×média), "
                                f"Preço={preco_atual:.2f}, Máx={preco_maxima_atual:.2f}, Mín={preco_minima_atual:.2f}, "
                                f"LONG={long}, SHORT={short}"
                            )
                    
                    except Exception as e:
                        if self.logger:
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] Erro ao calcular Volume para {symbol} {timeframe}: {e}",
                                exc_info=True
                            )
                        resultados[symbol][timeframe] = {
                            "volume_atual": None, "volume_media": None,
                            "preco_atual": None, "preco_maxima": None, "preco_minima": None,
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

