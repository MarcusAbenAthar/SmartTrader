"""
Plugin Ichimoku Cloud - Sistema Smart Trader.

Calcula Ichimoku Cloud (9,26,52,26) e retorna sinais LONG/SHORT conforme estratégia:
- LONG: Preço > máx(Senkou A, Senkou B)
- SHORT: Preço < mín(Senkou A, Senkou B)

__institucional__ = "Smart_Trader Plugin Ichimoku - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginIchimoku(Plugin):
    """
    Plugin de cálculo de Ichimoku Cloud.
    
    Responsabilidades:
    - Calcular Ichimoku Cloud (9,26,52,26) para cada par/timeframe
    - Retornar sinais LONG/SHORT baseados na posição do preço em relação à nuvem
    """
    
    __institucional__ = "Smart_Trader Plugin Ichimoku - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginIchimoku"
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
        
        config_ichimoku = self.config.get("indicadores", {}).get("ichimoku", {})
        self.tenkan = config_ichimoku.get("tenkan", 9)
        self.kijun = config_ichimoku.get("kijun", 26)
        self.senkou_b = config_ichimoku.get("senkou_b", 52)
        self.chikou = config_ichimoku.get("chikou", 26)
        
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
                    f"Ichimoku({self.tenkan},{self.kijun},{self.senkou_b},{self.chikou})"
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro na inicialização: {e}", exc_info=True)
            return False
    
    def _calcular_ichimoku(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Calcula componentes do Ichimoku Cloud.
        
        Args:
            df: DataFrame com colunas high, low, close
        
        Returns:
            dict: Componentes do Ichimoku
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # Tenkan-sen (linha de conversão) = (máx(9) + mín(9)) / 2
        tenkan_high = high.rolling(window=self.tenkan).max()
        tenkan_low = low.rolling(window=self.tenkan).min()
        tenkan = (tenkan_high + tenkan_low) / 2
        
        # Kijun-sen (linha de base) = (máx(26) + mín(26)) / 2
        kijun_high = high.rolling(window=self.kijun).max()
        kijun_low = low.rolling(window=self.kijun).min()
        kijun = (kijun_high + kijun_low) / 2
        
        # Senkou Span A (primeira linha da nuvem) = (Tenkan + Kijun) / 2, deslocado 26 períodos
        senkou_a = ((tenkan + kijun) / 2).shift(self.kijun)
        
        # Senkou Span B (segunda linha da nuvem) = (máx(52) + mín(52)) / 2, deslocado 26 períodos
        senkou_b_high = high.rolling(window=self.senkou_b).max()
        senkou_b_low = low.rolling(window=self.senkou_b).min()
        senkou_b = ((senkou_b_high + senkou_b_low) / 2).shift(self.kijun)
        
        # Chikou Span = Close deslocado 26 períodos para trás
        chikou = close.shift(-self.chikou)
        
        return {
            "tenkan": tenkan,
            "kijun": kijun,
            "senkou_a": senkou_a,
            "senkou_b": senkou_b,
            "chikou": chikou,
        }
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] ▶ Iniciando execução do indicador Ichimoku")
            
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
                    if not velas or len(velas) < self.senkou_b + self.kijun:
                        resultados[symbol][timeframe] = {
                            "long": False, "short": False,
                            "erro": "Velas insuficientes"
                        }
                        continue
                    
                    try:
                        df = pd.DataFrame(velas)
                        
                        ichimoku = self._calcular_ichimoku(df)
                        
                        preco_atual = float(df["close"].iloc[-1])
                        senkou_a_atual = float(ichimoku["senkou_a"].iloc[-1]) if not pd.isna(ichimoku["senkou_a"].iloc[-1]) else None
                        senkou_b_atual = float(ichimoku["senkou_b"].iloc[-1]) if not pd.isna(ichimoku["senkou_b"].iloc[-1]) else None
                        
                        # Determina sinais
                        long = False
                        short = False
                        
                        if senkou_a_atual is not None and senkou_b_atual is not None:
                            # LONG: Preço > máx(Senkou A, Senkou B)
                            if preco_atual > max(senkou_a_atual, senkou_b_atual):
                                long = True
                            
                            # SHORT: Preço < mín(Senkou A, Senkou B)
                            if preco_atual < min(senkou_a_atual, senkou_b_atual):
                                short = True
                        
                        # Obtém valores completos do Ichimoku
                        tenkan_atual = float(ichimoku["tenkan"].iloc[-1]) if not pd.isna(ichimoku["tenkan"].iloc[-1]) else None
                        kijun_atual = float(ichimoku["kijun"].iloc[-1]) if not pd.isna(ichimoku["kijun"].iloc[-1]) else None
                        chikou_atual = float(ichimoku["chikou"].iloc[-1]) if not pd.isna(ichimoku["chikou"].iloc[-1]) else None
                        
                        resultados[symbol][timeframe] = {
                            "preco": preco_atual,
                            "senkou_a": senkou_a_atual,
                            "senkou_b": senkou_b_atual,
                            "tenkan": tenkan_atual,
                            "kijun": kijun_atual,
                            "chikou": chikou_atual,
                            "long": long,
                            "short": short,
                        }
                        
                        # Salva dados no banco
                        self._salvar_dados_banco(symbol, timeframe, df, resultados[symbol][timeframe])
                        
                        if (long or short) and self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] {symbol} {timeframe}: "
                                f"Preço={preco_atual:.2f}, SenkouA={senkou_a_atual:.2f}, SenkouB={senkou_b_atual:.2f}, "
                                f"LONG={long}, SHORT={short}"
                            )
                    
                    except Exception as e:
                        if self.logger:
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] Erro ao calcular Ichimoku para {symbol} {timeframe}: {e}",
                                exc_info=True
                            )
                        resultados[symbol][timeframe] = {
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
        """
        Salva dados do Ichimoku no banco de dados.
        
        Args:
            symbol: Símbolo do par (ex: "BTCUSDT")
            timeframe: Timeframe (ex: "15m")
            df: DataFrame com velas
            resultado: Resultado do cálculo do indicador
        """
        try:
            if not self.plugin_banco_dados:
                return
            
            # Obtém open_time da última vela
            if len(df) == 0:
                return
            
            ultima_vela = df.iloc[-1]
            open_time = None
            
            # Tenta obter timestamp da última vela
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
            
            # Prepara dados para inserção
            dados_ichimoku = {
                "exchange": self.exchange_name,
                "ativo": symbol,
                "timeframe": timeframe,
                "open_time": open_time,
                "preco": resultado.get("preco"),
                "senkou_a": resultado.get("senkou_a"),
                "senkou_b": resultado.get("senkou_b"),
                "tenkan": resultado.get("tenkan"),
                "kijun": resultado.get("kijun"),
                "chikou": resultado.get("chikou"),
                "long": resultado.get("long", False),
                "short": resultado.get("short", False),
                "testnet": self.testnet
            }
            
            # Insere no banco (usa upsert automático via constraint unique)
            self.plugin_banco_dados.inserir("indicadores_ichimoku", [dados_ichimoku])
            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao salvar dados no banco para {symbol} {timeframe}: {e}")

