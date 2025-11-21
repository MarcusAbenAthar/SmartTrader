"""
Plugin MACD (Moving Average Convergence Divergence) - Sistema Smart Trader.

Calcula MACD (12,26,9) e retorna sinais LONG/SHORT conforme estratégia:
- LONG: Linha MACD > Sinal E Histograma atual > anterior
- SHORT: Linha MACD < Sinal E Histograma atual < anterior

__institucional__ = "Smart_Trader Plugin MACD - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginMacd(Plugin):
    """
    Plugin de cálculo de MACD (Moving Average Convergence Divergence).
    
    Responsabilidades:
    - Calcular MACD(12,26,9) para cada par/timeframe
    - Retornar sinais LONG/SHORT baseados em MACD
    - Integrar com dados de velas do PluginDadosVelas
    """
    
    __institucional__ = "Smart_Trader Plugin MACD - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginMacd"
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
        
        # Configurações do MACD
        config_macd = self.config.get("indicadores", {}).get("macd", {})
        self.rapida = config_macd.get("rapida", 12)
        self.lenta = config_macd.get("lenta", 26)
        self.sinal = config_macd.get("sinal", 9)
        
        self.plugin_dados_velas = None
        self.plugin_banco_dados = None
        self.testnet = self.config.get("bybit", {}).get("testnet", False)
        self.exchange_name = "bybit"
    
    def definir_plugin_dados_velas(self, plugin_dados_velas):
        self.plugin_dados_velas = plugin_dados_velas
    
    def definir_plugin_banco_dados(self, plugin_banco_dados):
        """Define referência ao PluginBancoDados."""
        self.plugin_banco_dados = plugin_banco_dados
    
    def _inicializar_interno(self) -> bool:
        try:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Inicializado. "
                    f"MACD({self.rapida},{self.lenta},{self.sinal})"
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro na inicialização: {e}", exc_info=True)
            return False
    
    def _calcular_macd(self, precos: pd.Series) -> Dict[str, pd.Series]:
        """
        Calcula MACD, Signal e Histogram.
        
        Returns:
            dict: {"macd": Series, "signal": Series, "histogram": Series}
        """
        if len(precos) < self.lenta + self.sinal:
            return {
                "macd": pd.Series([np.nan] * len(precos), index=precos.index),
                "signal": pd.Series([np.nan] * len(precos), index=precos.index),
                "histogram": pd.Series([np.nan] * len(precos), index=precos.index),
            }
        
        # Calcula EMAs
        ema_rapida = precos.ewm(span=self.rapida, adjust=False).mean()
        ema_lenta = precos.ewm(span=self.lenta, adjust=False).mean()
        
        # MACD = EMA rápida - EMA lenta
        macd = ema_rapida - ema_lenta
        
        # Signal = EMA do MACD
        signal = macd.ewm(span=self.sinal, adjust=False).mean()
        
        # Histogram = MACD - Signal
        histogram = macd - signal
        
        return {
            "macd": macd,
            "signal": signal,
            "histogram": histogram,
        }
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] ▶ Iniciando execução do indicador MACD")
            
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
                    if not velas or len(velas) < self.lenta + self.sinal:
                        resultados[symbol][timeframe] = {
                            "macd": None, "signal": None, "histogram": None,
                            "long": False, "short": False,
                            "erro": "Velas insuficientes"
                        }
                        continue
                    
                    try:
                        df = pd.DataFrame(velas)
                        precos = pd.Series(df["close"].values)
                        
                        macd_data = self._calcular_macd(precos)
                        
                        macd_atual = float(macd_data["macd"].iloc[-1]) if not pd.isna(macd_data["macd"].iloc[-1]) else None
                        signal_atual = float(macd_data["signal"].iloc[-1]) if not pd.isna(macd_data["signal"].iloc[-1]) else None
                        histogram_atual = float(macd_data["histogram"].iloc[-1]) if not pd.isna(macd_data["histogram"].iloc[-1]) else None
                        histogram_anterior = float(macd_data["histogram"].iloc[-2]) if len(macd_data["histogram"]) >= 2 and not pd.isna(macd_data["histogram"].iloc[-2]) else None
                        
                        # Determina sinais
                        long = False
                        short = False
                        
                        if all([macd_atual is not None, signal_atual is not None, histogram_atual is not None, histogram_anterior is not None]):
                            # LONG: Linha MACD > Sinal E Histograma atual > anterior
                            if macd_atual > signal_atual and histogram_atual > histogram_anterior:
                                long = True
                            
                            # SHORT: Linha MACD < Sinal E Histograma atual < anterior
                            if macd_atual < signal_atual and histogram_atual < histogram_anterior:
                                short = True
                        
                        resultados[symbol][timeframe] = {
                            "preco": float(df["close"].iloc[-1]),
                            "macd": macd_atual,
                            "signal": signal_atual,
                            "histogram": histogram_atual,
                            "long": long,
                            "short": short,
                        }
                        
                        # Salva dados no banco
                        self._salvar_dados_banco(symbol, timeframe, df, resultados[symbol][timeframe])
                        
                        if (long or short) and self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] {symbol} {timeframe}: "
                                f"MACD={macd_atual:.4f}, Signal={signal_atual:.4f}, "
                                f"LONG={long}, SHORT={short}"
                            )
                    
                    except Exception as e:
                        if self.logger:
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] Erro ao calcular MACD para {symbol} {timeframe}: {e}",
                                exc_info=True
                            )
                        resultados[symbol][timeframe] = {
                            "macd": None, "signal": None, "histogram": None,
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
    
    def _salvar_dados_banco(self, symbol: str, timeframe: str, df: pd.DataFrame, resultado: Dict[str, Any]):
        """Salva dados do MACD no banco de dados."""
        try:
            if not self.plugin_banco_dados:
                return
            
            if len(df) == 0:
                return
            
            ultima_vela = df.iloc[-1]
            open_time = None
            
            if "timestamp" in ultima_vela:
                from datetime import datetime
                timestamp = ultima_vela["timestamp"]
                if isinstance(timestamp, (int, float)):
                    open_time = datetime.fromtimestamp(timestamp / 1000)
                elif isinstance(timestamp, datetime):
                    open_time = timestamp
            elif "datetime" in df.columns:
                open_time = ultima_vela["datetime"]
            
            if not open_time:
                return
            
            dados_macd = {
                "exchange": self.exchange_name,
                "ativo": symbol,
                "timeframe": timeframe,
                "open_time": open_time,
                "preco": resultado.get("preco"),
                "macd_line": resultado.get("macd"),
                "signal_line": resultado.get("signal"),
                "histogram": resultado.get("histogram"),
                "long": resultado.get("long", False),
                "short": resultado.get("short", False),
                "testnet": self.testnet
            }
            
            self.plugin_banco_dados.inserir("indicadores_macd", [dados_macd])
            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao salvar dados no banco para {symbol} {timeframe}: {e}")

