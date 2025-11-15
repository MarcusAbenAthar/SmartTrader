"""
Plugin Supertrend - Sistema Smart Trader.

Calcula Supertrend (10, 3) e retorna sinais LONG/SHORT conforme estratégia:
- LONG: Linha VERDE e ≤ Preço
- SHORT: Linha VERMELHA e ≥ Preço

__institucional__ = "Smart_Trader Plugin Supertrend - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginSupertrend(Plugin):
    """
    Plugin de cálculo de Supertrend.
    
    Responsabilidades:
    - Calcular Supertrend(10, 3) para cada par/timeframe
    - Retornar sinais LONG/SHORT baseados na cor da linha e posição do preço
    """
    
    __institucional__ = "Smart_Trader Plugin Supertrend - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginSupertrend"
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
        
        config_supertrend = self.config.get("indicadores", {}).get("supertrend", {})
        self.periodo = config_supertrend.get("periodo", 10)
        self.multiplier = config_supertrend.get("multiplier", 3)
        
        self.plugin_dados_velas = None
    
    def definir_plugin_dados_velas(self, plugin_dados_velas):
        self.plugin_dados_velas = plugin_dados_velas
    
    def _inicializar_interno(self) -> bool:
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Inicializado. Supertrend({self.periodo}, {self.multiplier})"
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro na inicialização: {e}", exc_info=True)
            return False
    
    def _calcular_supertrend(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        Calcula Supertrend.
        
        Args:
            df: DataFrame com colunas high, low, close
        
        Returns:
            dict: {"supertrend": Series, "direcao": Series} onde direcao = 1 (verde/alta) ou -1 (vermelha/baixa)
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # Calcula ATR (Average True Range)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.periodo).mean()
        
        # Calcula bandas básicas
        hl_avg = (high + low) / 2
        upper_band = hl_avg + (self.multiplier * atr)
        lower_band = hl_avg - (self.multiplier * atr)
        
        # Inicializa arrays
        supertrend = pd.Series(index=df.index, dtype=float)
        direcao = pd.Series(index=df.index, dtype=int)
        
        # Calcula Supertrend
        for i in range(len(df)):
            if i == 0:
                supertrend.iloc[i] = upper_band.iloc[i]
                direcao.iloc[i] = -1  # Vermelho (baixa)
            else:
                # Atualiza bandas finais
                if close.iloc[i] <= supertrend.iloc[i-1]:
                    supertrend.iloc[i] = upper_band.iloc[i]
                    direcao.iloc[i] = -1  # Vermelho
                else:
                    supertrend.iloc[i] = lower_band.iloc[i]
                    direcao.iloc[i] = 1  # Verde
                
                # Ajusta bandas finais
                if supertrend.iloc[i] == upper_band.iloc[i] and supertrend.iloc[i-1] == lower_band.iloc[i-1]:
                    supertrend.iloc[i] = supertrend.iloc[i-1]
                elif supertrend.iloc[i] == lower_band.iloc[i] and supertrend.iloc[i-1] == upper_band.iloc[i-1]:
                    supertrend.iloc[i] = supertrend.iloc[i-1]
                
                # Ajusta direção se necessário
                if close.iloc[i] > supertrend.iloc[i]:
                    direcao.iloc[i] = 1  # Verde
                elif close.iloc[i] < supertrend.iloc[i]:
                    direcao.iloc[i] = -1  # Vermelho
                else:
                    direcao.iloc[i] = direcao.iloc[i-1]
        
        return {
            "supertrend": supertrend,
            "direcao": direcao,
        }
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] ▶ Iniciando execução do indicador Supertrend")
            
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
                    if not velas or len(velas) < self.periodo + 1:
                        resultados[symbol][timeframe] = {
                            "supertrend": None, "direcao": None,
                            "long": False, "short": False,
                            "erro": "Velas insuficientes"
                        }
                        continue
                    
                    try:
                        df = pd.DataFrame(velas)
                        
                        supertrend_data = self._calcular_supertrend(df)
                        
                        preco_atual = float(df["close"].iloc[-1])
                        supertrend_atual = float(supertrend_data["supertrend"].iloc[-1]) if not pd.isna(supertrend_data["supertrend"].iloc[-1]) else None
                        direcao_atual = int(supertrend_data["direcao"].iloc[-1]) if not pd.isna(supertrend_data["direcao"].iloc[-1]) else None
                        
                        # Determina sinais
                        long = False
                        short = False
                        
                        if supertrend_atual is not None and direcao_atual is not None:
                            # LONG: Linha VERDE (direcao=1) e ≤ Preço
                            if direcao_atual == 1 and preco_atual >= supertrend_atual:
                                long = True
                            
                            # SHORT: Linha VERMELHA (direcao=-1) e ≥ Preço
                            if direcao_atual == -1 and preco_atual <= supertrend_atual:
                                short = True
                        
                        resultados[symbol][timeframe] = {
                            "supertrend": supertrend_atual,
                            "direcao": "VERDE" if direcao_atual == 1 else "VERMELHA" if direcao_atual == -1 else None,
                            "long": long,
                            "short": short,
                        }
                        
                        if (long or short) and self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] {symbol} {timeframe}: "
                                f"Preço={preco_atual:.2f}, Supertrend={supertrend_atual:.2f}, "
                                f"Direção={resultados[symbol][timeframe]['direcao']}, "
                                f"LONG={long}, SHORT={short}"
                            )
                    
                    except Exception as e:
                        if self.logger:
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] Erro ao calcular Supertrend para {symbol} {timeframe}: {e}",
                                exc_info=True
                            )
                        resultados[symbol][timeframe] = {
                            "supertrend": None, "direcao": None,
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

