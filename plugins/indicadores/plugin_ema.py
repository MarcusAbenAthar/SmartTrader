"""
Plugin EMA Crossover - Sistema Smart Trader.

Calcula EMA Crossover (9/21) e retorna sinais LONG/SHORT conforme estratégia:
- LONG: EMA9 cruza ACIMA da EMA21 (vela atual ou anterior)
- SHORT: EMA9 cruza ABAIXO da EMA21

__institucional__ = "Smart_Trader Plugin EMA - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginEma(Plugin):
    """
    Plugin de cálculo de EMA Crossover.
    
    Responsabilidades:
    - Calcular EMA(9) e EMA(21) para cada par/timeframe
    - Detectar cruzamentos e retornar sinais LONG/SHORT
    """
    
    __institucional__ = "Smart_Trader Plugin EMA - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginEma"
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
        
        config_ema = self.config.get("indicadores", {}).get("ema", {})
        self.rapida = config_ema.get("rapida", 9)
        self.lenta = config_ema.get("lenta", 21)
        
        self.plugin_dados_velas = None
    
    def definir_plugin_dados_velas(self, plugin_dados_velas):
        self.plugin_dados_velas = plugin_dados_velas
    
    def _inicializar_interno(self) -> bool:
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Inicializado. EMA({self.rapida}/{self.lenta})"
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro na inicialização: {e}", exc_info=True)
            return False
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] ▶ Iniciando execução do indicador EMA")
            
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
                    if not velas or len(velas) < self.lenta:
                        resultados[symbol][timeframe] = {
                            "ema_rapida": None, "ema_lenta": None,
                            "long": False, "short": False,
                            "erro": "Velas insuficientes"
                        }
                        continue
                    
                    try:
                        df = pd.DataFrame(velas)
                        precos = pd.Series(df["close"].values)
                        
                        # Calcula EMAs
                        ema_rapida = precos.ewm(span=self.rapida, adjust=False).mean()
                        ema_lenta = precos.ewm(span=self.lenta, adjust=False).mean()
                        
                        ema_rapida_atual = float(ema_rapida.iloc[-1]) if not pd.isna(ema_rapida.iloc[-1]) else None
                        ema_lenta_atual = float(ema_lenta.iloc[-1]) if not pd.isna(ema_lenta.iloc[-1]) else None
                        ema_rapida_anterior = float(ema_rapida.iloc[-2]) if len(ema_rapida) >= 2 and not pd.isna(ema_rapida.iloc[-2]) else None
                        ema_lenta_anterior = float(ema_lenta.iloc[-2]) if len(ema_lenta) >= 2 and not pd.isna(ema_lenta.iloc[-2]) else None
                        
                        # Determina sinais
                        long = False
                        short = False
                        
                        if all([ema_rapida_atual, ema_lenta_atual, ema_rapida_anterior, ema_lenta_anterior]):
                            # LONG: EMA9 cruza ACIMA da EMA21
                            # Verifica se cruzou na vela atual ou anterior
                            if (ema_rapida_atual > ema_lenta_atual and ema_rapida_anterior <= ema_lenta_anterior) or \
                               (ema_rapida_atual > ema_lenta_atual):
                                long = True
                            
                            # SHORT: EMA9 cruza ABAIXO da EMA21
                            if (ema_rapida_atual < ema_lenta_atual and ema_rapida_anterior >= ema_lenta_anterior) or \
                               (ema_rapida_atual < ema_lenta_atual):
                                short = True
                        
                        resultados[symbol][timeframe] = {
                            "ema_rapida": ema_rapida_atual,
                            "ema_lenta": ema_lenta_atual,
                            "long": long,
                            "short": short,
                        }
                        
                        if (long or short) and self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] {symbol} {timeframe}: "
                                f"EMA{self.rapida}={ema_rapida_atual:.2f}, EMA{self.lenta}={ema_lenta_atual:.2f}, "
                                f"LONG={long}, SHORT={short}"
                            )
                    
                    except Exception as e:
                        if self.logger:
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] Erro ao calcular EMA para {symbol} {timeframe}: {e}",
                                exc_info=True
                            )
                        resultados[symbol][timeframe] = {
                            "ema_rapida": None, "ema_lenta": None,
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

