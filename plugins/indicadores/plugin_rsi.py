"""
Plugin RSI (Relative Strength Index) - Sistema Smart Trader.

Calcula RSI (14) e retorna sinais LONG/SHORT conforme estratégia:
- LONG: RSI ≤ 35 (ideal ≤ 30)
- SHORT: RSI ≥ 65 (ideal ≥ 70)

__institucional__ = "Smart_Trader Plugin RSI - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd
import numpy as np

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginRsi(Plugin):
    """
    Plugin de cálculo de RSI (Relative Strength Index).
    
    Responsabilidades:
    - Calcular RSI(14) para cada par/timeframe
    - Retornar sinais LONG/SHORT baseados em RSI
    - Integrar com dados de velas do PluginDadosVelas
    
    Características:
    - Período configurável (padrão: 14)
    - Limites configuráveis para LONG/SHORT
    """
    
    __institucional__ = "Smart_Trader Plugin RSI - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginRsi"
    plugin_versao = "v1.0.0"
    plugin_schema_versao = "v1.0.0"
    plugin_tipo = TipoPlugin.INDICADOR
    
    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLogProtocol] = None,
        gerenciador_banco: Optional[GerenciadorBancoProtocol] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o PluginRsi.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            gerenciador_banco: Instância do GerenciadorBanco
            config: Configuração do sistema
        """
        super().__init__(gerenciador_log, gerenciador_banco, config)
        
        # Configurações do RSI
        config_rsi = self.config.get("indicadores", {}).get("rsi", {})
        self.periodo = config_rsi.get("periodo", 14)
        self.limite_long = config_rsi.get("limite_long", 35)  # RSI ≤ 35
        self.limite_short = config_rsi.get("limite_short", 65)  # RSI ≥ 65
        
        # Referência ao plugin de dados de velas (será injetada)
        self.plugin_dados_velas = None
        self.plugin_banco_dados = None
        self.testnet = self.config.get("bybit", {}).get("testnet", False)
        self.exchange_name = "bybit"
    
    def definir_plugin_dados_velas(self, plugin_dados_velas):
        """
        Define referência ao plugin de dados de velas.
        
        Args:
            plugin_dados_velas: Instância do PluginDadosVelas
        """
        self.plugin_dados_velas = plugin_dados_velas
    
    def definir_plugin_banco_dados(self, plugin_banco_dados):
        """Define referência ao PluginBancoDados."""
        self.plugin_banco_dados = plugin_banco_dados
    
    def _inicializar_interno(self) -> bool:
        """
        Inicializa recursos específicos do plugin.
        
        Returns:
            bool: True se inicializado com sucesso
        """
        try:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Inicializado. "
                    f"Período: {self.periodo}, "
                    f"Limites: LONG≤{self.limite_long}, SHORT≥{self.limite_short}"
                )
            
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro na inicialização: {e}",
                    exc_info=True
                )
            return False
    
    def _calcular_rsi(self, precos: pd.Series, periodo: int = None) -> pd.Series:
        """
        Calcula RSI (Relative Strength Index).
        
        Args:
            precos: Série de preços (geralmente close)
            periodo: Período do RSI (padrão: self.periodo)
        
        Returns:
            pd.Series: Valores de RSI
        """
        if periodo is None:
            periodo = self.periodo
        
        if len(precos) < periodo + 1:
            return pd.Series([np.nan] * len(precos), index=precos.index)
        
        # Calcula variações
        delta = precos.diff()
        
        # Separa ganhos e perdas
        ganhos = delta.where(delta > 0, 0.0)
        perdas = -delta.where(delta < 0, 0.0)
        
        # Calcula média móvel exponencial (EWMA)
        avg_ganhos = ganhos.ewm(alpha=1/periodo, adjust=False).mean()
        avg_perdas = perdas.ewm(alpha=1/periodo, adjust=False).mean()
        
        # Calcula RS e RSI
        rs = avg_ganhos / avg_perdas
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executa o cálculo de RSI para todos os pares/timeframes.
        
        Args:
            dados_entrada: Dados de entrada (opcional, se não fornecido busca do PluginDadosVelas)
                Formato esperado: {
                    "BTCUSDT": {
                        "15m": {"velas": [...]},
                        "1h": {"velas": [...]},
                        "4h": {"velas": [...]}
                    },
                    ...
                }
        
        Returns:
            dict: Resultados do RSI por par/timeframe
                Formato: {
                    "status": "ok",
                    "dados": {
                        "BTCUSDT": {
                            "15m": {"rsi": 45.2, "long": False, "short": False},
                            ...
                        }
                    }
                }
        """
        try:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Iniciando execução...")
            
            if self.cancelamento_solicitado():
                return {
                    "status": StatusExecucao.CANCELADO.value,
                    "mensagem": "Cancelamento solicitado"
                }
            
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
                    self.logger.warning(f"[{self.PLUGIN_NAME}] Dados de velas não disponíveis")
                return {
                    "status": StatusExecucao.ERRO.value,
                    "mensagem": "Dados de velas não disponíveis"
                }
            
            if not dados_velas:
                return {
                    "status": StatusExecucao.ERRO.value,
                    "mensagem": "Nenhum dado de vela encontrado"
                }
            
            resultados = {}
            
            # Processa cada par e timeframe
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
                            "rsi": None,
                            "long": False,
                            "short": False,
                            "erro": "Velas insuficientes"
                        }
                        continue
                    
                    try:
                        # Converte para DataFrame
                        df = pd.DataFrame(velas)
                        precos = pd.Series(df["close"].values)
                        
                        # Calcula RSI
                        rsi_series = self._calcular_rsi(precos, self.periodo)
                        rsi_atual = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None
                        
                        # Determina sinais
                        long = False
                        short = False
                        
                        if rsi_atual is not None:
                            # LONG: RSI ≤ 35 (ideal ≤ 30)
                            if rsi_atual <= self.limite_long:
                                long = True
                            
                            # SHORT: RSI ≥ 65 (ideal ≥ 70)
                            if rsi_atual >= self.limite_short:
                                short = True
                        
                        resultados[symbol][timeframe] = {
                            "preco": float(df["close"].iloc[-1]),
                            "rsi": rsi_atual,
                            "long": long,
                            "short": short,
                            "periodo": self.periodo,
                        }
                        
                        # Salva dados no banco
                        self._salvar_dados_banco(symbol, timeframe, df, resultados[symbol][timeframe])
                        
                        # Log se sinal detectado
                        if (long or short) and self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] {symbol} {timeframe}: "
                                f"RSI={rsi_atual:.2f}, LONG={long}, SHORT={short}"
                            )
                    
                    except Exception as e:
                        if self.logger:
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] Erro ao calcular RSI para {symbol} {timeframe}: {e}",
                                exc_info=True
                            )
                        resultados[symbol][timeframe] = {
                            "rsi": None,
                            "long": False,
                            "short": False,
                            "erro": str(e)
                        }
            
            # Armazena dados
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
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro na execução: {e}",
                    exc_info=True
                )
            return {
                "status": StatusExecucao.ERRO.value,
                "mensagem": f"Erro: {e}",
                "erro": str(e)
            }
    
    def _salvar_dados_banco(self, symbol: str, timeframe: str, df: pd.DataFrame, resultado: Dict[str, Any]):
        """Salva dados do RSI no banco de dados."""
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
            
            dados_rsi = {
                "exchange": self.exchange_name,
                "ativo": symbol,
                "timeframe": timeframe,
                "open_time": open_time,
                "preco": resultado.get("preco"),
                "rsi": resultado.get("rsi"),
                "long": resultado.get("long", False),
                "short": resultado.get("short", False),
                "testnet": self.testnet
            }
            
            self.plugin_banco_dados.inserir("indicadores_rsi", [dados_rsi])
            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao salvar dados no banco para {symbol} {timeframe}: {e}")

