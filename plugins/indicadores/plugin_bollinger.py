"""
Plugin Bollinger Bands + Squeeze - Sistema Smart Trader.

Calcula Bollinger Bands (20, 2) + Squeeze e retorna sinais LONG/SHORT conforme estratégia:
- SQUEEZE: BB Width < 0.04 por ≥5 velas consecutivas
- LONG: Preço FECHA ACIMA da banda superior (após squeeze)
- SHORT: Preço FECHA ABAIXO da banda inferior (após squeeze)

__institucional__ = "Smart_Trader Plugin Bollinger - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginBollinger(Plugin):
    """
    Plugin de cálculo de Bollinger Bands + Squeeze.
    
    Responsabilidades:
    - Calcular Bollinger Bands(20, 2) para cada par/timeframe
    - Detectar Squeeze (BB Width < 0.04 por ≥5 velas)
    - Retornar sinais LONG/SHORT baseados em rompimento após squeeze
    """
    
    __institucional__ = "Smart_Trader Plugin Bollinger - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginBollinger"
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
        
        config_bollinger = self.config.get("indicadores", {}).get("bollinger", {})
        self.periodo = config_bollinger.get("periodo", 20)
        self.desvio_padrao = config_bollinger.get("desvio_padrao", 2)
        self.squeeze_width_max = config_bollinger.get("squeeze_width_max", 0.04)
        self.squeeze_velas_minimas = config_bollinger.get("squeeze_velas_minimas", 5)
        
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
                    f"BB({self.periodo}, {self.desvio_padrao}), "
                    f"Squeeze: Width<{self.squeeze_width_max} por ≥{self.squeeze_velas_minimas} velas"
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro na inicialização: {e}", exc_info=True)
            return False
    
    def _calcular_bollinger(self, precos: pd.Series) -> Dict[str, pd.Series]:
        """
        Calcula Bollinger Bands.
        
        Args:
            precos: Série de preços (close)
        
        Returns:
            dict: {"upper": Series, "middle": Series, "lower": Series, "width": Series}
        """
        # Média móvel simples
        middle = precos.rolling(window=self.periodo).mean()
        
        # Desvio padrão
        std = precos.rolling(window=self.periodo).std()
        
        # Bandas
        upper = middle + (self.desvio_padrao * std)
        lower = middle - (self.desvio_padrao * std)
        
        # BB Width = (Upper - Lower) / Middle
        width = (upper - lower) / middle
        
        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "width": width,
        }
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] ▶ Iniciando execução do indicador Bollinger")
            
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
                    if not velas or len(velas) < self.periodo + self.squeeze_velas_minimas:
                        resultados[symbol][timeframe] = {
                            "squeeze": False, "squeeze_velas": 0,
                            "long": False, "short": False,
                            "erro": "Velas insuficientes"
                        }
                        continue
                    
                    try:
                        df = pd.DataFrame(velas)
                        precos = pd.Series(df["close"].values)
                        
                        bb = self._calcular_bollinger(precos)
                        
                        # Verifica squeeze (BB Width < 0.04 por ≥5 velas consecutivas)
                        width_atual = bb["width"].iloc[-self.squeeze_velas_minimas:].values
                        squeeze_detectado = False
                        squeeze_velas = 0
                        
                        if len(width_atual) >= self.squeeze_velas_minimas:
                            # Conta quantas velas consecutivas têm width < squeeze_width_max
                            contador = 0
                            for w in reversed(width_atual):
                                if not pd.isna(w) and w < self.squeeze_width_max:
                                    contador += 1
                                else:
                                    break
                            
                            if contador >= self.squeeze_velas_minimas:
                                squeeze_detectado = True
                                squeeze_velas = contador
                        
                        # Determina sinais (apenas se squeeze detectado)
                        long = False
                        short = False
                        
                        if squeeze_detectado:
                            preco_fechamento = float(df["close"].iloc[-1])
                            upper_atual = float(bb["upper"].iloc[-1]) if not pd.isna(bb["upper"].iloc[-1]) else None
                            lower_atual = float(bb["lower"].iloc[-1]) if not pd.isna(bb["lower"].iloc[-1]) else None
                            
                            if upper_atual is not None and lower_atual is not None:
                                # LONG: Preço FECHA ACIMA da banda superior
                                if preco_fechamento > upper_atual:
                                    long = True
                                
                                # SHORT: Preço FECHA ABAIXO da banda inferior
                                if preco_fechamento < lower_atual:
                                    short = True
                        
                        resultados[symbol][timeframe] = {
                            "preco": float(df["close"].iloc[-1]),
                            "upper": float(bb["upper"].iloc[-1]) if not pd.isna(bb["upper"].iloc[-1]) else None,
                            "middle": float(bb["middle"].iloc[-1]) if not pd.isna(bb["middle"].iloc[-1]) else None,
                            "lower": float(bb["lower"].iloc[-1]) if not pd.isna(bb["lower"].iloc[-1]) else None,
                            "width": float(bb["width"].iloc[-1]) if not pd.isna(bb["width"].iloc[-1]) else None,
                            "squeeze": squeeze_detectado,
                            "squeeze_velas": squeeze_velas,
                            "long": long,
                            "short": short,
                        }
                        
                        # Salva dados no banco
                        self._salvar_dados_banco(symbol, timeframe, df, resultados[symbol][timeframe])
                        
                        if (long or short) and self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] {symbol} {timeframe}: "
                                f"Squeeze={squeeze_detectado} ({squeeze_velas} velas), "
                                f"Width={resultados[symbol][timeframe]['width']:.4f}, "
                                f"LONG={long}, SHORT={short}"
                            )
                    
                    except Exception as e:
                        if self.logger:
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] Erro ao calcular Bollinger para {symbol} {timeframe}: {e}",
                                exc_info=True
                            )
                        resultados[symbol][timeframe] = {
                            "squeeze": False, "squeeze_velas": 0,
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
        """Salva dados do Bollinger no banco de dados."""
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
            
            dados_bollinger = {
                "exchange": self.exchange_name,
                "ativo": symbol,
                "timeframe": timeframe,
                "open_time": open_time,
                "preco": resultado.get("preco"),
                "upper_band": resultado.get("upper"),
                "middle_band": resultado.get("middle"),
                "lower_band": resultado.get("lower"),
                "bb_width": resultado.get("width"),
                "squeeze": resultado.get("squeeze", False),
                "long": resultado.get("long", False),
                "short": resultado.get("short", False),
                "testnet": self.testnet
            }
            
            self.plugin_banco_dados.inserir("indicadores_bollinger", [dados_bollinger])
            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao salvar dados no banco para {symbol} {timeframe}: {e}")

