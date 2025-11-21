"""
Plugin Gerenciador de Padrões de Trading - Sistema Smart Trader.

Orquestra a detecção de padrões técnicos de trading (Top 30).
Implementa validação temporal, filtro de regime e confidence decay.

__institucional__ = "Smart_Trader Plugin Gerenciador Padrões - Sistema 6/8 Unificado"

Conforme proxima_atualizacao.md:
- Top 10 padrões implementados primeiro
- Validação temporal (Walk-Forward, Rolling Window, OOS)
- Filtro de Regime de Mercado (Trending vs Range)
- Confidence Decay (decaimento de confiança)
- Telemetria completa
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from enum import Enum
import math
import logging

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class RegimeMercado(Enum):
    """Enum para regime de mercado."""
    TRENDING = "trending"
    RANGE = "range"
    INDEFINIDO = "indefinido"


class PluginPadroes(Plugin):
    """
    Plugin de detecção de padrões técnicos de trading.
    
    Responsabilidades:
    - Detectar os Top 10 padrões (expandir para 30)
    - Aplicar filtro de regime de mercado
    - Calcular confidence decay
    - Validar padrões temporalmente (Walk-Forward, OOS)
    - Armazenar padrões detectados no banco
    - Fornecer métricas de performance por padrão
    
    Características:
    - Modular: cada padrão é uma função separada
    - Vetorizado: usa Pandas/NumPy para performance
    - Telemetria completa: regime, confidence, métricas
    - Validação temporal obrigatória
    """
    
    __institucional__ = "Smart_Trader Plugin Padrões - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginPadroes"
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
        Inicializa o PluginPadroes.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            gerenciador_banco: Instância do GerenciadorBanco
            config: Configuração do sistema
        """
        super().__init__(gerenciador_log, gerenciador_banco, config)
        
        # Configurações de padrões
        self.config_padroes = self.config.get("padroes", {})
        
        # Thresholds de validação
        self.threshold_frequency = self.config_padroes.get("threshold_frequency", 5)  # ≥ 5 por 1000 velas
        self.threshold_precision = self.config_padroes.get("threshold_precision", 0.40)  # > 40%
        self.threshold_expectancy = self.config_padroes.get("threshold_expectancy", 0.0)  # > 0
        self.threshold_sharpe = self.config_padroes.get("threshold_sharpe", 0.8)  # > 0.8
        self.threshold_confidence = self.config_padroes.get("threshold_confidence", 0.7)  # > 0.7 para execução
        
        # Configuração de validação temporal
        self.walk_forward_treino = self.config_padroes.get("walk_forward_treino", 0.6)  # 60% treino
        self.walk_forward_teste = self.config_padroes.get("walk_forward_teste", 0.4)  # 40% teste
        self.rolling_window_dias = self.config_padroes.get("rolling_window_dias", 180)  # 180 dias
        self.rolling_recalculo_dias = self.config_padroes.get("rolling_recalculo_dias", 30)  # a cada 30 dias
        self.oos_percentual = self.config_padroes.get("oos_percentual", 0.30)  # ≥ 30% OOS
        
        # Confidence decay
        self.confidence_decay_lambda = self.config_padroes.get("confidence_decay_lambda", 0.01)  # λ = 0.01
        
        # Cache de padrões detectados
        self._padroes_detectados: Dict[str, List[Dict[str, Any]]] = {}
        
        # Histórico de wins/losses por padrão (para confidence decay)
        self._historico_performance: Dict[str, List[Dict[str, Any]]] = {}
        
        # Controle de timestamps - última vela analisada por par/timeframe
        # Formato: {f"{symbol}_{timeframe}": timestamp}
        self._ultima_vela_analisada: Dict[str, int] = {}
        
        # Limites de velas por timeframe (Passo 1)
        self._limites_velas = {
            "15m": 20,
            "1h": 15,
            "4h": 10,
        }
        
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
                    f"Top 10 padrões ativos. "
                    f"Threshold confidence: {self.threshold_confidence}"
                )
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.critical(
                    f"[{self.PLUGIN_NAME}] Erro ao inicializar: {e}",
                    exc_info=True,
                )
            return False
    
    @property
    def plugin_tabelas(self) -> Dict[str, Dict[str, Any]]:
        """
        Define as tabelas que este plugin utiliza.
        
        Returns:
            dict: Definições de tabelas
        """
        return {
            "padroes_detectados": {
                "descricao": "Padrões técnicos detectados com telemetria completa",
                "modo_acesso": "own",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "symbol": "VARCHAR(20) NOT NULL",
                    "timeframe": "VARCHAR(5) NOT NULL",
                    "open_time": "TIMESTAMP NOT NULL",
                    "tipo_padrao": "VARCHAR(50) NOT NULL",
                    "direcao": "VARCHAR(10) NOT NULL",  # LONG, SHORT
                    "score": "NUMERIC(5,4) NOT NULL",  # 0.0 a 1.0
                    "confidence": "NUMERIC(5,4) NOT NULL",  # 0.0 a 1.0
                    "regime": "VARCHAR(20) NOT NULL",  # trending, range, indefinido
                    "suggested_sl": "NUMERIC(20,8)",
                    "suggested_tp": "NUMERIC(20,8)",
                    "final_score": "NUMERIC(5,4) NOT NULL",  # technical_score * 0.6 + confidence * 0.4
                    "meta": "JSONB",  # Metadados adicionais
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
            "padroes_metricas": {
                "descricao": "Métricas de performance por padrão (precision, recall, expectancy, etc.)",
                "modo_acesso": "own",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "tipo_padrao": "VARCHAR(50) NOT NULL",
                    "symbol": "VARCHAR(20)",
                    "timeframe": "VARCHAR(5)",
                    "periodo_inicio": "TIMESTAMP NOT NULL",
                    "periodo_fim": "TIMESTAMP NOT NULL",
                    "frequency": "NUMERIC(10,4) NOT NULL",  # Ocorrências por 1000 velas
                    "precision": "NUMERIC(5,4)",  # % de setups que atingiram target
                    "recall": "NUMERIC(5,4)",
                    "expectancy": "NUMERIC(10,4)",  # EV por trade
                    "sharpe_condicional": "NUMERIC(10,4)",  # Retorno médio / desvio por padrão
                    "drawdown_condicional": "NUMERIC(10,4)",  # Max perda por padrão
                    "winrate": "NUMERIC(5,4)",
                    "avg_rr": "NUMERIC(5,4)",  # Risk:Reward médio
                    "total_trades": "INTEGER DEFAULT 0",
                    "trades_win": "INTEGER DEFAULT 0",
                    "trades_loss": "INTEGER DEFAULT 0",
                    "tipo_validacao": "VARCHAR(20)",  # in_sample, out_of_sample, walk_forward, rolling
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
            "padroes_confidence": {
                "descricao": "Histórico de confidence decay por padrão",
                "modo_acesso": "own",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "tipo_padrao": "VARCHAR(50) NOT NULL",
                    "symbol": "VARCHAR(20)",
                    "timeframe": "VARCHAR(5)",
                    "data_ultimo_win": "TIMESTAMP",
                    "days_since_last_win": "INTEGER",
                    "base_score": "NUMERIC(5,4) NOT NULL",
                    "confidence_score": "NUMERIC(5,4) NOT NULL",
                    "em_quarentena": "BOOLEAN DEFAULT FALSE",  # confidence < 0.5
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
        }
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executa detecção de padrões para dados de velas fornecidos.
        
        Args:
            dados_entrada: Dicionário com dados de velas por par/timeframe
                Formato esperado:
                {
                    "BTCUSDT": {
                        "15m": {
                            "velas": [...],
                            "quantidade": 60,
                            ...
                        },
                        ...
                    },
                    ...
                }
        
        Returns:
            dict: Resultado com padrões detectados
        """
        try:
            if not dados_entrada:
                return {
                    "status": "erro",
                    "mensagem": "Dados de entrada não fornecidos",
                    "plugin": self.PLUGIN_NAME,
                }
            
            # Limpa cache de padrões anteriores
            self._padroes_detectados.clear()
            
            # Processa cada par e timeframe
            padroes_detectados_total = []
            
            for symbol, dados_par in dados_entrada.items():
                if not isinstance(dados_par, dict):
                    continue
                
                # Prepara dados de múltiplos timeframes para Multi-timeframe confirmation
                dados_multi_tf = {}  # {timeframe: DataFrame}
                ultima_vela_nova_por_tf = {}  # {timeframe: timestamp} - armazena última vela nova por timeframe
                
                for timeframe, dados_tf in dados_par.items():
                    if not isinstance(dados_tf, dict) or "velas" not in dados_tf:
                        continue
                    
                    velas = dados_tf.get("velas", [])
                    if not velas:
                        continue
                    
                    # PASSO 2: Filtra velas por timestamp (só analisa velas novas)
                    cache_key = f"{symbol}_{timeframe}"
                    ultima_timestamp = self._ultima_vela_analisada.get(cache_key, 0)
                    
                    # CORREÇÃO CRÍTICA: Na primeira execução (ultima_timestamp == 0), 
                    # só processa a ÚLTIMA vela, não todas as velas do histórico
                    if ultima_timestamp == 0:
                        # Primeira execução: só processa a última vela fechada
                        if not velas:
                            continue
                        ultima_vela = velas[-1]
                        ultima_vela_timestamp = ultima_vela.get("timestamp", 0)
                        if ultima_vela_timestamp == 0:
                            continue
                        
                        # Usa histórico limitado para contexto técnico, mas só detecta na última vela
                        limite = self._limites_velas.get(timeframe, 20)
                        velas_historico = velas[-limite:] if len(velas) > limite else velas
                        df = self._velas_para_dataframe(velas_historico)
                        dados_multi_tf[timeframe] = df
                        ultima_vela_nova_por_tf[timeframe] = ultima_vela_timestamp
                        # Marca como analisada ANTES de processar
                        self._ultima_vela_analisada[cache_key] = ultima_vela_timestamp
                    else:
                        # Execuções subsequentes: só processa velas novas
                        velas_novas = [v for v in velas if v.get("timestamp", 0) > ultima_timestamp]
                        
                        # Se não há velas novas, PULA este par/timeframe completamente
                        if not velas_novas:
                            if self.logger:
                                self.logger.debug(
                                    f"[{self.PLUGIN_NAME}] Pulando {symbol} {timeframe} - "
                                    f"sem velas novas (última analisada: {ultima_timestamp})"
                                )
                            continue  # Pula este timeframe - não há velas novas para processar
                        
                        # PASSO 1: Limita quantidade de velas por timeframe
                        # IMPORTANTE: Usa as últimas N velas do histórico completo para contexto,
                        # mas só detecta padrões na última vela nova
                        limite = self._limites_velas.get(timeframe, 20)
                        
                        # Pega as últimas N velas do histórico completo para contexto técnico
                        # (indicadores precisam de histórico)
                        velas_historico = velas[-limite:] if len(velas) > limite else velas
                        
                        # Converte para DataFrame
                        df = self._velas_para_dataframe(velas_historico)
                        dados_multi_tf[timeframe] = df
                        
                        # Identifica a última vela nova (será usada para filtrar padrões)
                        ultima_vela_nova_timestamp = max(v.get("timestamp", 0) for v in velas_novas)
                        ultima_vela_nova_por_tf[timeframe] = ultima_vela_nova_timestamp
                        
                        # Atualiza última vela analisada ANTES de processar (evita reprocessamento)
                        if ultima_vela_nova_timestamp > ultima_timestamp:
                            self._ultima_vela_analisada[cache_key] = ultima_vela_nova_timestamp
                
                # Processa cada timeframe
                for timeframe, df in dados_multi_tf.items():
                    # Recupera a última vela nova para este timeframe
                    ultima_vela_nova_timestamp = ultima_vela_nova_por_tf.get(timeframe)
                    if ultima_vela_nova_timestamp is None:
                        continue  # Não deveria acontecer, mas por segurança
                    # Detecta regime de mercado
                    regime = self._detectar_regime(df)
                    
                    # Log reduzido - apenas DEBUG
                    # if self.gerenciador_log:
                    #     self.gerenciador_log.log_evento(...)
                    
                    # PASSO 3: Identifica última vela fechada (candle atual)
                    # A última vela do DataFrame é a última vela fechada
                    if len(df) == 0:
                        continue
                    
                    ultima_vela_fechada = df.iloc[-1]
                    ultima_vela_fechada_timestamp = int(ultima_vela_fechada["timestamp"])
                    ultima_vela_fechada_datetime = ultima_vela_fechada["datetime"]
                    
                    # PASSO 3 CRÍTICO: Só processa se a última vela é uma vela NOVA
                    # A última vela do DataFrame deve ser a última vela nova identificada
                    if ultima_vela_fechada_timestamp != ultima_vela_nova_timestamp:
                        # DataFrame não termina na última vela nova - pode haver problema
                        # Mas continua processando, pois o filtro abaixo vai garantir que só mantemos padrões da última vela nova
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] AVISO: DataFrame não termina na última vela nova "
                                f"({symbol} {timeframe}: última_df={ultima_vela_fechada_timestamp}, "
                                f"última_nova={ultima_vela_nova_timestamp})"
                            )
                    
                    # Detecta padrões (Top 30)
                    # Passa dados_multi_tf para permitir acesso a múltiplos timeframes
                    padroes = self._detectar_padroes_top30(df, symbol, timeframe, regime, dados_multi_tf=dados_multi_tf)
                    
                    # PASSO 3: Filtra padrões - só mantém os do candle atual (última vela NOVA)
                    # CRÍTICO: Só mantém padrões da última vela nova identificada
                    padroes_filtrados = []
                    padroes_rejeitados = 0
                    
                    # Encontra a última vela nova no DataFrame para comparação
                    ultima_vela_nova_row = None
                    for idx, row in df.iterrows():
                        if int(row["timestamp"]) == ultima_vela_nova_timestamp:
                            ultima_vela_nova_row = row
                            break
                    
                    if ultima_vela_nova_row is None:
                        # Se não encontrou a última vela nova no DataFrame, pula todos os padrões
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] AVISO: Última vela nova ({ultima_vela_nova_timestamp}) "
                                f"não encontrada no DataFrame para {symbol} {timeframe}"
                            )
                        padroes = []
                    else:
                        ultima_vela_nova_datetime = pd.to_datetime(ultima_vela_nova_row["datetime"])
                        
                        for padrao in padroes:
                            padrao_open_time = padrao.get("open_time")
                            
                            # Converte open_time para datetime para comparação
                            padrao_dt = None
                            try:
                                if isinstance(padrao_open_time, (pd.Timestamp, datetime)):
                                    padrao_dt = pd.to_datetime(padrao_open_time)
                                elif isinstance(padrao_open_time, str):
                                    padrao_dt = pd.to_datetime(padrao_open_time)
                                elif isinstance(padrao_open_time, (int, float)):
                                    # Assume timestamp em milissegundos se > 1e10, senão segundos
                                    ts = padrao_open_time / 1000 if padrao_open_time > 1e10 else padrao_open_time
                                    padrao_dt = pd.to_datetime(ts, unit='s')
                            except Exception:
                                padroes_rejeitados += 1
                                continue  # Se não conseguir converter, pula este padrão
                            
                            # Compara datetime: só mantém se for da última vela nova (diferença < 1 segundo)
                            if padrao_dt is not None:
                                diff = abs((padrao_dt - ultima_vela_nova_datetime).total_seconds())
                                if diff < 1.0:  # Mesma vela se diferença < 1 segundo
                                    padroes_filtrados.append(padrao)
                                else:
                                    padroes_rejeitados += 1
                            else:
                                padroes_rejeitados += 1
                        
                        padroes = padroes_filtrados
                        
                        # Log INFO: mostra quantos padrões foram filtrados (mais visível para debug)
                        if self.logger:
                            if padroes:
                                tipos = [p.get("tipo_padrao", "unknown") for p in padroes]
                                self.logger.info(
                                    f"[{self.PLUGIN_NAME}] Filtro: {len(padroes)} padrão(ões) mantido(s) "
                                    f"({', '.join(set(tipos))}), {padroes_rejeitados} rejeitado(s) "
                                    f"para {symbol} {timeframe} (última vela: {ultima_vela_nova_timestamp})"
                                )
                            elif padroes_rejeitados > 0:
                                self.logger.debug(
                                    f"[{self.PLUGIN_NAME}] Filtro: {padroes_rejeitados} padrão(ões) rejeitado(s) "
                                    f"para {symbol} {timeframe} (não são da última vela: {ultima_vela_nova_timestamp})"
                                )
                    
                    # Log DEBUG: Detalhamento de padrões detectados
                    if self.logger and padroes:
                        tipos_detectados = [p.get("tipo_padrao", "unknown") for p in padroes]
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] DEBUG — Padrões detectados para {symbol} {timeframe}: {', '.join(set(tipos_detectados))}"
                        )
                    
                    # Aplica confidence decay
                    padroes_com_confidence = self._aplicar_confidence_decay(padroes, symbol, timeframe)
                    
                    # Calcula score final
                    padroes_finais = self._calcular_score_final(padroes_com_confidence)
                    
                    # Calcula ensemble_score (combinação de padrões convergentes)
                    padroes_com_ensemble = self.calcular_ensemble_score(padroes_finais)
                    
                    # Log TRACE: Cálculos internos de ensemble
                    if self.logger and padroes_com_ensemble:
                        padroes_com_convergencia = [p for p in padroes_com_ensemble if p.get("ensemble_count", 1) > 1]
                        if padroes_com_convergencia:
                            for p in padroes_com_convergencia[:3]:  # Loga apenas os 3 primeiros para não poluir
                                self.logger.debug(
                                    f"[{self.PLUGIN_NAME}] TRACE — Ensemble: {p.get('tipo_padrao')} — "
                                    f"convergencia={p.get('ensemble_count', 1)} padrão(ões), "
                                    f"ensemble_score={p.get('ensemble_score', 0):.3f}, "
                                    f"final_score={p.get('final_score', 0):.3f}"
                                )
                    
                    # Log WARNING: Padrões fracos (score baixo)
                    padroes_fracos = [p for p in padroes_com_ensemble if p.get("final_score", 0) < 0.5]
                    if padroes_fracos and self.gerenciador_log:
                        for padrao_fraco in padroes_fracos:
                            self.gerenciador_log.log_evento(
                                tipo_log="padroes",
                                nome_origem="PluginPadroes",
                                tipo_evento="padrao_fraco",
                                mensagem=f"Padrão fraco detectado: {padrao_fraco.get('tipo_padrao')} — score {padrao_fraco.get('final_score', 0):.2f}",
                                nivel=logging.WARNING,
                                par=symbol,
                                detalhes={"tipo_padrao": padrao_fraco.get("tipo_padrao"), "score": padrao_fraco.get("final_score")}
                            )
                    
                    # Filtra por threshold (usa ensemble_score se disponível, senão final_score)
                    padroes_validos = []
                    for p in padroes_com_ensemble:
                        score_para_filtro = p.get("ensemble_score", p.get("final_score", 0))
                        if score_para_filtro >= self.threshold_confidence:
                            padroes_validos.append(p)
                    
                    # Log reduzido - apenas DEBUG (resumo consolidado no final)
                    # if self.gerenciador_log and padroes_validos:
                    #     ...
                    
                    padroes_detectados_total.extend(padroes_validos)
                    
                    # Armazena em cache
                    cache_key = f"{symbol}_{timeframe}"
                    self._padroes_detectados[cache_key] = padroes_validos
            
            # Persiste padrões no banco
            if padroes_detectados_total:
                self._persistir_padroes(padroes_detectados_total)
            
            # Armazena dados
            self.dados_completos["crus"] = dados_entrada
            self.dados_completos["analisados"] = {
                "padroes_detectados": padroes_detectados_total,
                "total_padroes": len(padroes_detectados_total),
                "resumo_por_tipo": self._resumir_por_tipo(padroes_detectados_total),
            }
            
            return {
                "status": "ok",
                "padroes_detectados": padroes_detectados_total,
                "total": len(padroes_detectados_total),
                "plugin": self.PLUGIN_NAME,
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao executar: {e}",
                    exc_info=True,
                )
            return {
                "status": "erro",
                "mensagem": str(e),
                "plugin": self.PLUGIN_NAME,
            }
    
    def _velas_para_dataframe(self, velas: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Converte lista de velas para DataFrame pandas.
        
        Args:
            velas: Lista de dicionários com dados de velas
        
        Returns:
            pd.DataFrame: DataFrame com colunas: timestamp, open, high, low, close, volume
        """
        dados = []
        for vela in velas:
            dados.append({
                "timestamp": vela.get("timestamp"),
                "datetime": vela.get("datetime"),
                "open": vela.get("open"),
                "high": vela.get("high"),
                "low": vela.get("low"),
                "close": vela.get("close"),
                "volume": vela.get("volume"),
            })
        
        df = pd.DataFrame(dados)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        return df
    
    def _detectar_regime(self, df: pd.DataFrame) -> RegimeMercado:
        """
        Detecta regime de mercado (Trending vs Range).
        
        Conforme proxima_atualizacao.md:
        trend_strength = abs(ema_50 - ema_200) / atr_14
        volatility_regime = bb_width.pct_change().rolling(20).std()
        
        if trend_strength > 1.5 and volatility_regime < 0.3:
            regime = "Trending"
        else:
            regime = "Range"
        
        Args:
            df: DataFrame com dados de velas
        
        Returns:
            RegimeMercado: Regime detectado
        """
        try:
            if len(df) < 200:
                return RegimeMercado.INDEFINIDO
            
            # Calcula EMAs
            df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
            df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
            
            # Calcula ATR(14)
            high_low = df["high"] - df["low"]
            high_close = np.abs(df["high"] - df["close"].shift())
            low_close = np.abs(df["low"] - df["close"].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df["atr_14"] = tr.rolling(window=14).mean()
            
            # Calcula Bollinger Bands width
            df["bb_middle"] = df["close"].rolling(window=20).mean()
            df["bb_std"] = df["close"].rolling(window=20).std()
            df["bb_width"] = (df["bb_std"] * 4) / df["bb_middle"]  # 2 desvios acima e abaixo
            
            # Trend strength
            trend_strength = np.abs(df["ema_50"].iloc[-1] - df["ema_200"].iloc[-1]) / df["atr_14"].iloc[-1]
            
            # Volatility regime
            volatility_regime = df["bb_width"].pct_change().rolling(20).std().iloc[-1]
            
            # Classifica regime
            if pd.isna(trend_strength) or pd.isna(volatility_regime):
                return RegimeMercado.INDEFINIDO
            
            if trend_strength > 1.5 and volatility_regime < 0.3:
                return RegimeMercado.TRENDING
            else:
                return RegimeMercado.RANGE
                
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar regime: {e}"
                )
            return RegimeMercado.INDEFINIDO
    
    def _detectar_padroes_top10(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta os Top 10 padrões de trading.
        
        Args:
            df: DataFrame com dados de velas
            symbol: Símbolo do par (ex: BTCUSDT)
            timeframe: Timeframe (ex: 15m)
            regime: Regime de mercado detectado
        
        Returns:
            list: Lista de padrões detectados
        """
        padroes = []
        
        # 1. Breakout de suporte/resistência com volume
        padroes.extend(self._detectar_breakout_suporte_resistencia(df, symbol, timeframe, regime))
        
        # 2. Pullback válido após breakout
        padroes.extend(self._detectar_pullback_apos_breakout(df, symbol, timeframe, regime))
        
        # 3. EMA crossover (9/21) com confirmação de volume
        padroes.extend(self._detectar_ema_crossover(df, symbol, timeframe, regime))
        
        # 4. RSI divergence (price × RSI)
        padroes.extend(self._detectar_rsi_divergence(df, symbol, timeframe, regime))
        
        # 5. Bollinger Squeeze + rompimento
        padroes.extend(self._detectar_bollinger_squeeze_rompimento(df, symbol, timeframe, regime))
        
        # 6. VWAP rejection / acceptance
        padroes.extend(self._detectar_vwap_rejection_acceptance(df, symbol, timeframe, regime))
        
        # 7. Candlestick Engulfing
        padroes.extend(self._detectar_engulfing(df, symbol, timeframe, regime))
        
        # 8. Hammer / Hanging Man
        padroes.extend(self._detectar_hammer_hanging_man(df, symbol, timeframe, regime))
        
        # 9. Volume spike anomaly
        padroes.extend(self._detectar_volume_spike(df, symbol, timeframe, regime))
        
        # 10. False breakout
        padroes.extend(self._detectar_false_breakout(df, symbol, timeframe, regime))
        
        return padroes
    
    def _detectar_breakout_suporte_resistencia(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta breakout de suporte/resistência com volume confirmado.
        
        Padrão #1 do Top 10.
        """
        padroes = []
        
        try:
            if len(df) < 20:
                return padroes
            
            # Identifica suporte/resistência (máximas e mínimas locais)
            df["high_rolling"] = df["high"].rolling(window=20).max()
            df["low_rolling"] = df["low"].rolling(window=20).min()
            
            # Volume médio
            df["volume_medio"] = df["volume"].rolling(window=20).mean()
            
            # Última vela
            ultima = df.iloc[-1]
            penultima = df.iloc[-2]
            
            # Breakout para cima (resistência)
            if (ultima["close"] > penultima["high_rolling"] and 
                ultima["volume"] > ultima["volume_medio"] * 1.5):
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "breakout_suporte_resistencia",
                    "direcao": "LONG",
                    "score": 0.8,  # Score técnico base
                    "confidence": 1.0,  # Será ajustado por confidence decay
                    "regime": regime.value,
                    "suggested_sl": ultima["low_rolling"],
                    "suggested_tp": ultima["close"] + (ultima["close"] - ultima["low_rolling"]) * 2.3,
                    "meta": {
                        "volume_multiplier": ultima["volume"] / ultima["volume_medio"],
                        "resistance_level": penultima["high_rolling"],
                    }
                })
            
            # Breakout para baixo (suporte)
            if (ultima["close"] < penultima["low_rolling"] and 
                ultima["volume"] > ultima["volume_medio"] * 1.5):
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "breakout_suporte_resistencia",
                    "direcao": "SHORT",
                    "score": 0.8,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["high_rolling"],
                    "suggested_tp": ultima["close"] - (ultima["high_rolling"] - ultima["close"]) * 2.3,
                    "meta": {
                        "volume_multiplier": ultima["volume"] / ultima["volume_medio"],
                        "support_level": penultima["low_rolling"],
                    }
                })
                
        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar breakout: {e}"
                )
        
        return padroes
    
    def _detectar_pullback_apos_breakout(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta pullback válido após breakout (reteste + suporte segurando).
        
        Padrão #2 do Top 10.
        """
        padroes = []
        
        try:
            if len(df) < 30:
                return padroes
            
            # Detecta breakout recente (últimas 10 velas)
            df["high_20"] = df["high"].rolling(window=20).max()
            df["low_20"] = df["low"].rolling(window=20).min()
            
            # Verifica se houve breakout nas últimas 10 velas
            for i in range(max(0, len(df) - 10), len(df) - 1):
                vela_breakout = df.iloc[i]
                vela_atual = df.iloc[-1]
                
                # Breakout para cima seguido de pullback
                if (vela_breakout["close"] > vela_breakout["high_20"] and
                    vela_atual["close"] > vela_breakout["high_20"] * 0.98 and  # Reteste
                    vela_atual["close"] < vela_breakout["close"]):  # Pullback
                    
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": vela_atual["datetime"],
                        "tipo_padrao": "pullback_apos_breakout",
                        "direcao": "LONG",
                        "score": 0.75,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": vela_breakout["high_20"] * 0.995,
                        "suggested_tp": vela_breakout["close"] + (vela_breakout["close"] - vela_breakout["high_20"]) * 2.3,
                        "meta": {
                            "breakout_level": vela_breakout["high_20"],
                            "pullback_percent": (vela_breakout["close"] - vela_atual["close"]) / vela_breakout["close"],
                        }
                    })
                    break
            
        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar pullback: {e}"
                )
        
        return padroes
    
    def _detectar_ema_crossover(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta EMA crossover (9/21) com confirmação de volume.
        
        Padrão #3 do Top 10.
        """
        padroes = []
        
        try:
            if len(df) < 21:
                return padroes
            
            # Calcula EMAs
            df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
            df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
            
            # Volume médio
            df["volume_medio"] = df["volume"].rolling(window=20).mean()
            
            # Detecta crossover
            df["crossover_up"] = (df["ema_9"] > df["ema_21"]) & (df["ema_9"].shift(1) <= df["ema_21"].shift(1))
            df["crossover_down"] = (df["ema_9"] < df["ema_21"]) & (df["ema_9"].shift(1) >= df["ema_21"].shift(1))
            
            ultima = df.iloc[-1]
            
            # Crossover para cima (LONG)
            if ultima["crossover_up"] and ultima["volume"] > ultima["volume_medio"] * 1.2:
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "ema_crossover",
                    "direcao": "LONG",
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["low"],
                    "suggested_tp": ultima["close"] + (ultima["close"] - ultima["low"]) * 2.3,
                    "meta": {
                        "ema_9": float(ultima["ema_9"]),
                        "ema_21": float(ultima["ema_21"]),
                        "volume_multiplier": float(ultima["volume"] / ultima["volume_medio"]),
                    }
                })
            
            # Crossover para baixo (SHORT)
            if ultima["crossover_down"] and ultima["volume"] > ultima["volume_medio"] * 1.2:
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "ema_crossover",
                    "direcao": "SHORT",
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["high"],
                    "suggested_tp": ultima["close"] - (ultima["high"] - ultima["close"]) * 2.3,
                    "meta": {
                        "ema_9": float(ultima["ema_9"]),
                        "ema_21": float(ultima["ema_21"]),
                        "volume_multiplier": float(ultima["volume"] / ultima["volume_medio"]),
                    }
                })
                
        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar EMA crossover: {e}"
                )
        
        return padroes
    
    def _detectar_rsi_divergence(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta RSI divergence (price × RSI) - bullish/bearish.
        
        Padrão #4 do Top 10.
        """
        padroes = []
        
        try:
            if len(df) < 30:
                return padroes
            
            # Calcula RSI(14)
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df["rsi"] = 100 - (100 / (1 + rs))
            
            # Detecta divergências (últimas 10 velas)
            for i in range(max(0, len(df) - 10), len(df) - 5):
                # Bullish divergence: preço faz lower low, RSI faz higher low
                price_low_1 = df["low"].iloc[i]
                price_low_2 = df["low"].iloc[i+5]
                rsi_low_1 = df["rsi"].iloc[i]
                rsi_low_2 = df["rsi"].iloc[i+5]
                
                if (price_low_2 < price_low_1 and rsi_low_2 > rsi_low_1 and 
                    rsi_low_1 < 35):  # RSI oversold
                    ultima = df.iloc[-1]
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "rsi_divergence",
                        "direcao": "LONG",
                        "score": 0.75,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": ultima["low"],
                        "suggested_tp": ultima["close"] + (ultima["close"] - ultima["low"]) * 2.3,
                        "meta": {
                            "rsi_current": float(ultima["rsi"]),
                            "divergence_type": "bullish",
                        }
                    })
                    break
                
                # Bearish divergence: preço faz higher high, RSI faz lower high
                price_high_1 = df["high"].iloc[i]
                price_high_2 = df["high"].iloc[i+5]
                rsi_high_1 = df["rsi"].iloc[i]
                rsi_high_2 = df["rsi"].iloc[i+5]
                
                if (price_high_2 > price_high_1 and rsi_high_2 < rsi_high_1 and 
                    rsi_high_1 > 65):  # RSI overbought
                    ultima = df.iloc[-1]
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "rsi_divergence",
                        "direcao": "SHORT",
                        "score": 0.75,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": ultima["high"],
                        "suggested_tp": ultima["close"] - (ultima["high"] - ultima["close"]) * 2.3,
                        "meta": {
                            "rsi_current": float(ultima["rsi"]),
                            "divergence_type": "bearish",
                        }
                    })
                    break
                    
        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar RSI divergence: {e}"
                )
        
        return padroes
    
    def _detectar_bollinger_squeeze_rompimento(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta Bollinger Squeeze + rompimento (BB width + fechamento fora).
        
        Padrão #5 do Top 10.
        Conforme definicao_estrategia.md: BB Width < 0.04 por ≥5 velas consecutivas.
        """
        padroes = []
        
        try:
            if len(df) < 25:
                return padroes
            
            # Calcula Bollinger Bands
            df["bb_middle"] = df["close"].rolling(window=20).mean()
            df["bb_std"] = df["close"].rolling(window=20).std()
            df["bb_upper"] = df["bb_middle"] + (df["bb_std"] * 2)
            df["bb_lower"] = df["bb_middle"] - (df["bb_std"] * 2)
            df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
            
            # Detecta squeeze (BB Width < 0.04 por ≥5 velas)
            df["squeeze"] = df["bb_width"] < 0.04
            df["squeeze_count"] = df["squeeze"].rolling(window=5).sum()
            
            ultima = df.iloc[-1]
            
            # Squeeze detectado + rompimento para cima
            if (ultima["squeeze_count"] >= 5 and 
                ultima["close"] > ultima["bb_upper"]):
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "bollinger_squeeze_rompimento",
                    "direcao": "LONG",
                    "score": 0.85,  # Alto score (padrão confiável)
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["bb_lower"],
                    "suggested_tp": ultima["close"] + (ultima["close"] - ultima["bb_lower"]) * 2.3,
                    "meta": {
                        "bb_width": float(ultima["bb_width"]),
                        "squeeze_velas": int(ultima["squeeze_count"]),
                    }
                })
            
            # Squeeze detectado + rompimento para baixo
            if (ultima["squeeze_count"] >= 5 and 
                ultima["close"] < ultima["bb_lower"]):
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "bollinger_squeeze_rompimento",
                    "direcao": "SHORT",
                    "score": 0.85,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["bb_upper"],
                    "suggested_tp": ultima["close"] - (ultima["bb_upper"] - ultima["close"]) * 2.3,
                    "meta": {
                        "bb_width": float(ultima["bb_width"]),
                        "squeeze_velas": int(ultima["squeeze_count"]),
                    }
                })
                
        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar Bollinger Squeeze: {e}"
                )
        
        return padroes
    
    def _detectar_vwap_rejection_acceptance(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta VWAP rejection / acceptance (preço testa e volta).
        
        Padrão #6 do Top 10.
        Conforme definicao_estrategia.md: |Preço - VWAP| / VWAP ≤ 0.003 (±0.3%).
        """
        padroes = []
        
        try:
            if len(df) < 20:
                return padroes
            
            # Calcula VWAP (Volume Weighted Average Price)
            # VWAP = sum(price * volume) / sum(volume) para o dia
            # Para simplificar, calculamos VWAP rolling (últimas 20 velas)
            df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3
            df["vwap"] = (df["typical_price"] * df["volume"]).rolling(window=20).sum() / df["volume"].rolling(window=20).sum()
            
            ultima = df.iloc[-1]
            penultima = df.iloc[-2]
            
            # VWAP rejection/acceptance para LONG
            # Preço testou VWAP e voltou acima (rejeição de baixo)
            if (penultima["low"] <= penultima["vwap"] * 1.003 and  # Testou próximo do VWAP
                ultima["close"] > ultima["vwap"] * 1.003):  # Fechou acima
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "vwap_rejection_acceptance",
                    "direcao": "LONG",
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["vwap"] * 0.997,
                    "suggested_tp": ultima["close"] + (ultima["close"] - ultima["vwap"]) * 2.3,
                    "meta": {
                        "vwap": float(ultima["vwap"]),
                        "distance_percent": float((ultima["close"] - ultima["vwap"]) / ultima["vwap"] * 100),
                    }
                })
            
            # VWAP rejection/acceptance para SHORT
            # Preço testou VWAP e voltou abaixo (rejeição de cima)
            if (penultima["high"] >= penultima["vwap"] * 0.997 and  # Testou próximo do VWAP
                ultima["close"] < ultima["vwap"] * 0.997):  # Fechou abaixo
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "vwap_rejection_acceptance",
                    "direcao": "SHORT",
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["vwap"] * 1.003,
                    "suggested_tp": ultima["close"] - (ultima["vwap"] - ultima["close"]) * 2.3,
                    "meta": {
                        "vwap": float(ultima["vwap"]),
                        "distance_percent": float((ultima["vwap"] - ultima["close"]) / ultima["vwap"] * 100),
                    }
                })
                
        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar VWAP rejection: {e}"
                )
        
        return padroes
    
    def _detectar_engulfing(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta Candlestick Engulfing (bull/bear) com volume confirmado.
        
        Padrão #7 do Top 10.
        """
        padroes = []
        
        try:
            if len(df) < 2:
                return padroes
            
            ultima = df.iloc[-1]
            penultima = df.iloc[-2]
            
            # Volume médio
            volume_medio = df["volume"].rolling(window=20).mean().iloc[-1]
            
            # Bullish Engulfing
            if (penultima["close"] < penultima["open"] and  # Vela anterior bearish
                ultima["close"] > ultima["open"] and  # Vela atual bullish
                ultima["open"] < penultima["close"] and  # Engulfing
                ultima["close"] > penultima["open"] and
                ultima["volume"] > volume_medio * 1.2):  # Volume confirmado
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "engulfing",
                    "direcao": "LONG",
                    "score": 0.75,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["low"],
                    "suggested_tp": ultima["close"] + (ultima["close"] - ultima["low"]) * 2.3,
                    "meta": {
                        "pattern_type": "bullish_engulfing",
                        "volume_multiplier": float(ultima["volume"] / volume_medio),
                    }
                })
            
            # Bearish Engulfing
            if (penultima["close"] > penultima["open"] and  # Vela anterior bullish
                ultima["close"] < ultima["open"] and  # Vela atual bearish
                ultima["open"] > penultima["close"] and  # Engulfing
                ultima["close"] < penultima["open"] and
                ultima["volume"] > volume_medio * 1.2):  # Volume confirmado
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "engulfing",
                    "direcao": "SHORT",
                    "score": 0.75,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["high"],
                    "suggested_tp": ultima["close"] - (ultima["high"] - ultima["close"]) * 2.3,
                    "meta": {
                        "pattern_type": "bearish_engulfing",
                        "volume_multiplier": float(ultima["volume"] / volume_medio),
                    }
                })
                
        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar Engulfing: {e}"
                )
        
        return padroes
    
    def _detectar_hammer_hanging_man(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta Hammer / Hanging Man + confirmação no fechamento seguinte.
        
        Padrão #8 do Top 10.
        """
        padroes = []
        
        try:
            if len(df) < 2:
                return padroes
            
            penultima = df.iloc[-2]
            ultima = df.iloc[-1]
            
            # Calcula tamanhos do corpo e sombras
            corpo_penultima = abs(penultima["close"] - penultima["open"])
            sombra_inferior_penultima = min(penultima["open"], penultima["close"]) - penultima["low"]
            sombra_superior_penultima = penultima["high"] - max(penultima["open"], penultima["close"])
            range_penultima = penultima["high"] - penultima["low"]
            
            # Hammer: sombra inferior longa, corpo pequeno, sombra superior pequena
            # Confirmação: fechamento seguinte acima do corpo do hammer
            if (sombra_inferior_penultima > corpo_penultima * 2 and
                sombra_superior_penultima < corpo_penultima * 0.5 and
                range_penultima > 0 and
                ultima["close"] > max(penultima["open"], penultima["close"])):  # Confirmação
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "hammer_hanging_man",
                    "direcao": "LONG",
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": penultima["low"],
                    "suggested_tp": ultima["close"] + (ultima["close"] - penultima["low"]) * 2.3,
                    "meta": {
                        "pattern_type": "hammer",
                        "lower_shadow_ratio": float(sombra_inferior_penultima / range_penultima),
                    }
                })
            
            # Hanging Man: sombra inferior longa, corpo pequeno no topo
            # Confirmação: fechamento seguinte abaixo do corpo do hanging man
            if (sombra_inferior_penultima > corpo_penultima * 2 and
                sombra_superior_penultima < corpo_penultima * 0.5 and
                range_penultima > 0 and
                ultima["close"] < min(penultima["open"], penultima["close"])):  # Confirmação
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "hammer_hanging_man",
                    "direcao": "SHORT",
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": penultima["high"],
                    "suggested_tp": ultima["close"] - (penultima["high"] - ultima["close"]) * 2.3,
                    "meta": {
                        "pattern_type": "hanging_man",
                        "lower_shadow_ratio": float(sombra_inferior_penultima / range_penultima),
                    }
                })
                
        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar Hammer/Hanging Man: {e}"
                )
        
        return padroes
    
    def _detectar_volume_spike(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta Volume spike anomaly (z-score sobre média(20)).
        
        Padrão #9 do Top 10.
        """
        padroes = []
        
        try:
            if len(df) < 20:
                return padroes
            
            # Calcula média e desvio padrão do volume
            df["volume_medio"] = df["volume"].rolling(window=20).mean()
            df["volume_std"] = df["volume"].rolling(window=20).std()
            
            # Z-score do volume
            df["volume_zscore"] = (df["volume"] - df["volume_medio"]) / df["volume_std"]
            
            ultima = df.iloc[-1]
            
            # Volume spike positivo (z-score > 2) + preço subindo
            if (ultima["volume_zscore"] > 2 and 
                ultima["close"] > ultima["open"]):
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "volume_spike",
                    "direcao": "LONG",
                    "score": 0.65,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["low"],
                    "suggested_tp": ultima["close"] + (ultima["close"] - ultima["low"]) * 2.3,
                    "meta": {
                        "volume_zscore": float(ultima["volume_zscore"]),
                        "volume_multiplier": float(ultima["volume"] / ultima["volume_medio"]),
                    }
                })
            
            # Volume spike negativo (z-score > 2) + preço caindo
            if (ultima["volume_zscore"] > 2 and 
                ultima["close"] < ultima["open"]):
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "volume_spike",
                    "direcao": "SHORT",
                    "score": 0.65,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["high"],
                    "suggested_tp": ultima["close"] - (ultima["high"] - ultima["close"]) * 2.3,
                    "meta": {
                        "volume_zscore": float(ultima["volume_zscore"]),
                        "volume_multiplier": float(ultima["volume"] / ultima["volume_medio"]),
                    }
                })
                
        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar Volume spike: {e}"
                )
        
        return padroes
    
    def _detectar_false_breakout(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """
        Detecta False breakout (fechamento de volta dentro da zona em X velas).
        
        Padrão #10 do Top 10.
        """
        padroes = []
        
        try:
            if len(df) < 25:
                return padroes
            
            # Identifica níveis de suporte/resistência
            df["high_20"] = df["high"].rolling(window=20).max()
            df["low_20"] = df["low"].rolling(window=20).min()
            
            # Verifica se houve breakout nas últimas 5 velas que foi revertido
            for i in range(max(0, len(df) - 5), len(df) - 1):
                vela_breakout = df.iloc[i]
                vela_atual = df.iloc[-1]
                
                # False breakout para cima: rompeu resistência mas voltou
                if (vela_breakout["close"] > vela_breakout["high_20"] and
                    vela_atual["close"] < vela_breakout["high_20"]):
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": vela_atual["datetime"],
                        "tipo_padrao": "false_breakout",
                        "direcao": "SHORT",  # Reversão esperada
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": vela_breakout["high_20"] * 1.01,
                        "suggested_tp": vela_atual["close"] - (vela_breakout["high_20"] - vela_atual["close"]) * 2.3,
                        "meta": {
                            "breakout_level": float(vela_breakout["high_20"]),
                            "reversal_percent": float((vela_breakout["high_20"] - vela_atual["close"]) / vela_breakout["high_20"] * 100),
                        }
                    })
                    break
                
                # False breakout para baixo: rompeu suporte mas voltou
                if (vela_breakout["close"] < vela_breakout["low_20"] and
                    vela_atual["close"] > vela_breakout["low_20"]):
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": vela_atual["datetime"],
                        "tipo_padrao": "false_breakout",
                        "direcao": "LONG",  # Reversão esperada
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": vela_breakout["low_20"] * 0.99,
                        "suggested_tp": vela_atual["close"] + (vela_atual["close"] - vela_breakout["low_20"]) * 2.3,
                        "meta": {
                            "breakout_level": float(vela_breakout["low_20"]),
                            "reversal_percent": float((vela_atual["close"] - vela_breakout["low_20"]) / vela_breakout["low_20"] * 100),
                        }
                    })
                    break
                    
        except Exception as e:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Erro ao detectar False breakout: {e}"
                )
        
        return padroes
    
    def _detectar_padroes_top30(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado,
        dados_multi_tf: Optional[Dict[str, pd.DataFrame]] = None
    ) -> List[Dict[str, Any]]:
        """
        Detecta os Top 30 padrões de trading (Top 10 + Próximos 20).
        
        Args:
            df: DataFrame com dados de velas do timeframe atual
            symbol: Símbolo do par (ex: BTCUSDT)
            timeframe: Timeframe atual (ex: 15m)
            regime: Regime de mercado detectado
            dados_multi_tf: Dicionário com DataFrames de múltiplos timeframes {timeframe: DataFrame}
        
        Returns:
            list: Lista de padrões detectados
        """
        padroes = []
        
        # Top 10 padrões
        padroes.extend(self._detectar_padroes_top10(df, symbol, timeframe, regime))
        
        # Próximos 20 padrões (11-30)
        padroes.extend(self._detectar_head_shoulders(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_double_top_bottom(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_triangle(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_flag_pennant(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_wedge(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_rectangle(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_three_soldiers_crows(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_morning_evening_star(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_tweezer(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_harami(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_piercing_dark_cloud(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_gap(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_macd_divergence(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_atr_breakout(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_fibonacci_confluence(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_liquidity_sweep(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_harmonic_patterns(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_volume_price_divergence(df, symbol, timeframe, regime))
        padroes.extend(self._detectar_multi_timeframe(df, symbol, timeframe, regime, dados_multi_tf=dados_multi_tf))
        padroes.extend(self._detectar_order_flow_proxy(df, symbol, timeframe, regime))
        
        return padroes
    
    # ========== PRÓXIMOS 20 PADRÕES (11-30) ==========
    
    def _detectar_head_shoulders(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #11: Head & Shoulders / Inverse H&S (neckline break)."""
        padroes = []
        try:
            if len(df) < 50:
                return padroes
            
            # Detecta 3 picos/vales para H&S
            df["high_rolling"] = df["high"].rolling(window=10).max()
            df["low_rolling"] = df["low"].rolling(window=10).min()
            
            # Busca padrão H&S nas últimas 30 velas
            for i in range(len(df) - 30, len(df) - 5):
                if i < 0:
                    continue
                
                window = df.iloc[i:i+30]
                highs = window["high"].values
                lows = window["low"].values
                
                # Head & Shoulders: 3 picos, o do meio é o mais alto
                peaks = []
                for j in range(1, len(highs) - 1):
                    if highs[j] > highs[j-1] and highs[j] > highs[j+1]:
                        peaks.append((j, highs[j]))
                
                if len(peaks) >= 3:
                    peaks = sorted(peaks, key=lambda x: x[1], reverse=True)
                    if peaks[0][1] > peaks[1][1] * 1.02 and peaks[0][1] > peaks[2][1] * 1.02:
                        # H&S detectado - sinal de reversão bearish
                        ultima = df.iloc[-1]
                        if ultima["close"] < window["low"].min():
                            padroes.append({
                                "symbol": symbol,
                                "timeframe": timeframe,
                                "open_time": ultima["datetime"],
                                "tipo_padrao": "head_shoulders",
                                "direcao": "SHORT",
                                "score": 0.75,
                                "confidence": 1.0,
                                "regime": regime.value,
                                "suggested_sl": peaks[0][1],
                                "suggested_tp": ultima["close"] - (peaks[0][1] - ultima["close"]) * 2.3,
                                "meta": {"pattern_type": "head_shoulders"}
                            })
                            break
                
                # Inverse H&S: 3 vales, o do meio é o mais baixo
                valleys = []
                for j in range(1, len(lows) - 1):
                    if lows[j] < lows[j-1] and lows[j] < lows[j+1]:
                        valleys.append((j, lows[j]))
                
                if len(valleys) >= 3:
                    valleys = sorted(valleys, key=lambda x: x[1])
                    if valleys[0][1] < valleys[1][1] * 0.98 and valleys[0][1] < valleys[2][1] * 0.98:
                        # Inverse H&S detectado - sinal de reversão bullish
                        ultima = df.iloc[-1]
                        if ultima["close"] > window["high"].max():
                            padroes.append({
                                "symbol": symbol,
                                "timeframe": timeframe,
                                "open_time": ultima["datetime"],
                                "tipo_padrao": "head_shoulders",
                                "direcao": "LONG",
                                "score": 0.75,
                                "confidence": 1.0,
                                "regime": regime.value,
                                "suggested_sl": valleys[0][1],
                                "suggested_tp": ultima["close"] + (ultima["close"] - valleys[0][1]) * 2.3,
                                "meta": {"pattern_type": "inverse_head_shoulders"}
                            })
                            break
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar H&S: {e}")
        return padroes
    
    def _detectar_double_top_bottom(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #12: Double Top / Double Bottom."""
        padroes = []
        try:
            if len(df) < 40:
                return padroes
            
            # Busca dois picos/vales similares
            window = df.iloc[-40:]
            highs = window["high"].values
            lows = window["low"].values
            
            # Double Top: dois picos próximos
            peaks = []
            for i in range(1, len(highs) - 1):
                if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                    peaks.append((i, highs[i]))
            
            if len(peaks) >= 2:
                p1, p2 = peaks[-2], peaks[-1]
                if abs(p1[1] - p2[1]) / max(p1[1], p2[1]) < 0.02:  # Dentro de 2%
                    ultima = df.iloc[-1]
                    if ultima["close"] < (p1[1] + p2[1]) / 2 * 0.98:
                        padroes.append({
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "open_time": ultima["datetime"],
                            "tipo_padrao": "double_top_bottom",
                            "direcao": "SHORT",
                            "score": 0.7,
                            "confidence": 1.0,
                            "regime": regime.value,
                            "suggested_sl": max(p1[1], p2[1]) * 1.01,
                            "suggested_tp": ultima["close"] - (max(p1[1], p2[1]) - ultima["close"]) * 2.3,
                            "meta": {"pattern_type": "double_top"}
                        })
            
            # Double Bottom
            valleys = []
            for i in range(1, len(lows) - 1):
                if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                    valleys.append((i, lows[i]))
            
            if len(valleys) >= 2:
                v1, v2 = valleys[-2], valleys[-1]
                if abs(v1[1] - v2[1]) / max(v1[1], v2[1]) < 0.02:
                    ultima = df.iloc[-1]
                    if ultima["close"] > (v1[1] + v2[1]) / 2 * 1.02:
                        padroes.append({
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "open_time": ultima["datetime"],
                            "tipo_padrao": "double_top_bottom",
                            "direcao": "LONG",
                            "score": 0.7,
                            "confidence": 1.0,
                            "regime": regime.value,
                            "suggested_sl": min(v1[1], v2[1]) * 0.99,
                            "suggested_tp": ultima["close"] + (ultima["close"] - min(v1[1], v2[1])) * 2.3,
                            "meta": {"pattern_type": "double_bottom"}
                        })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Double Top/Bottom: {e}")
        return padroes
    
    def _detectar_triangle(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #13: Triangle (Asc/Desc/Sym) (breakout + volume)."""
        padroes = []
        try:
            if len(df) < 30:
                return padroes
            
            window = df.iloc[-30:]
            highs = window["high"].values
            lows = window["low"].values
            
            # Detecta convergência (triângulo)
            high_trend = np.polyfit(range(len(highs)), highs, 1)[0]
            low_trend = np.polyfit(range(len(lows)), lows, 1)[0]
            
            volume_medio = window["volume"].mean()
            ultima = window.iloc[-1]
            
            # Triângulo simétrico: ambos convergindo
            if abs(high_trend) < 0.001 and abs(low_trend) < 0.001:
                # Breakout para cima
                if ultima["close"] > highs.max() * 0.99 and ultima["volume"] > volume_medio * 1.5:
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "triangle",
                        "direcao": "LONG",
                        "score": 0.75,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": lows.min(),
                        "suggested_tp": ultima["close"] + (ultima["close"] - lows.min()) * 2.3,
                        "meta": {"pattern_type": "symmetric_triangle", "breakout_direction": "up"}
                    })
                # Breakout para baixo
                elif ultima["close"] < lows.min() * 1.01 and ultima["volume"] > volume_medio * 1.5:
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "triangle",
                        "direcao": "SHORT",
                        "score": 0.75,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": highs.max(),
                        "suggested_tp": ultima["close"] - (highs.max() - ultima["close"]) * 2.3,
                        "meta": {"pattern_type": "symmetric_triangle", "breakout_direction": "down"}
                    })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Triangle: {e}")
        return padroes
    
    def _detectar_flag_pennant(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #14: Flag / Pennant (continuation)."""
        padroes = []
        try:
            if len(df) < 20:
                return padroes
            
            # Flag: movimento forte seguido de consolidação
            window = df.iloc[-20:]
            first_half = window.iloc[:10]
            second_half = window.iloc[10:]
            
            # Movimento inicial forte
            initial_move = abs(first_half["close"].iloc[-1] - first_half["close"].iloc[0])
            consolidation_range = second_half["high"].max() - second_half["low"].min()
            
            if initial_move > consolidation_range * 2:
                ultima = df.iloc[-1]
                direction = "LONG" if first_half["close"].iloc[-1] > first_half["close"].iloc[0] else "SHORT"
                
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "flag_pennant",
                    "direcao": direction,
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": second_half["low"].min() if direction == "LONG" else second_half["high"].max(),
                    "suggested_tp": None,  # Será calculado baseado no movimento inicial
                    "meta": {"pattern_type": "flag", "initial_move": float(initial_move)}
                })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Flag/Pennant: {e}")
        return padroes
    
    def _detectar_wedge(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #15: Wedge rising / falling (reversão)."""
        padroes = []
        try:
            if len(df) < 25:
                return padroes
            
            window = df.iloc[-25:]
            highs = window["high"].values
            lows = window["low"].values
            
            # Rising Wedge: ambos subindo, mas convergindo
            high_trend = np.polyfit(range(len(highs)), highs, 1)[0]
            low_trend = np.polyfit(range(len(lows)), lows, 1)[0]
            
            if high_trend > 0 and low_trend > 0 and high_trend > low_trend * 1.5:
                # Rising wedge - reversão bearish
                ultima = df.iloc[-1]
                if ultima["close"] < lows.min():
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "wedge",
                        "direcao": "SHORT",
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": highs.max(),
                        "suggested_tp": ultima["close"] - (highs.max() - ultima["close"]) * 2.3,
                        "meta": {"pattern_type": "rising_wedge"}
                    })
            
            # Falling Wedge: ambos descendo, mas convergindo
            if high_trend < 0 and low_trend < 0 and abs(low_trend) > abs(high_trend) * 1.5:
                # Falling wedge - reversão bullish
                ultima = df.iloc[-1]
                if ultima["close"] > highs.max():
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "wedge",
                        "direcao": "LONG",
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": lows.min(),
                        "suggested_tp": ultima["close"] + (ultima["close"] - lows.min()) * 2.3,
                        "meta": {"pattern_type": "falling_wedge"}
                    })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Wedge: {e}")
        return padroes
    
    def _detectar_rectangle(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #16: Rectangle (range breakout)."""
        padroes = []
        try:
            if len(df) < 20:
                return padroes
            
            window = df.iloc[-20:]
            high_range = window["high"].max()
            low_range = window["low"].min()
            range_size = high_range - low_range
            
            # Rectangle: preço oscilando em range
            if range_size / window["close"].mean() < 0.05:  # Range < 5%
                ultima = df.iloc[-1]
                volume_medio = window["volume"].mean()
                
                # Breakout para cima
                if ultima["close"] > high_range and ultima["volume"] > volume_medio * 1.5:
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "rectangle",
                        "direcao": "LONG",
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": low_range,
                        "suggested_tp": ultima["close"] + (ultima["close"] - low_range) * 2.3,
                        "meta": {"pattern_type": "rectangle_breakout_up"}
                    })
                # Breakout para baixo
                elif ultima["close"] < low_range and ultima["volume"] > volume_medio * 1.5:
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "rectangle",
                        "direcao": "SHORT",
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": high_range,
                        "suggested_tp": ultima["close"] - (high_range - ultima["close"]) * 2.3,
                        "meta": {"pattern_type": "rectangle_breakout_down"}
                    })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Rectangle: {e}")
        return padroes
    
    def _detectar_three_soldiers_crows(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #17: Three White Soldiers / Three Black Crows."""
        padroes = []
        try:
            if len(df) < 3:
                return padroes
            
            ultimas_3 = df.iloc[-3:]
            
            # Three White Soldiers: 3 velas bullish consecutivas
            if all(ultimas_3["close"] > ultimas_3["open"]) and \
               all(ultimas_3["close"].iloc[i] > ultimas_3["close"].iloc[i-1] for i in range(1, 3)):
                ultima = df.iloc[-1]
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "three_soldiers_crows",
                    "direcao": "LONG",
                    "score": 0.75,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultimas_3["low"].min(),
                    "suggested_tp": ultima["close"] + (ultima["close"] - ultimas_3["low"].min()) * 2.3,
                    "meta": {"pattern_type": "three_white_soldiers"}
                })
            
            # Three Black Crows: 3 velas bearish consecutivas
            if all(ultimas_3["close"] < ultimas_3["open"]) and \
               all(ultimas_3["close"].iloc[i] < ultimas_3["close"].iloc[i-1] for i in range(1, 3)):
                ultima = df.iloc[-1]
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "three_soldiers_crows",
                    "direcao": "SHORT",
                    "score": 0.75,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultimas_3["high"].max(),
                    "suggested_tp": ultima["close"] - (ultimas_3["high"].max() - ultima["close"]) * 2.3,
                    "meta": {"pattern_type": "three_black_crows"}
                })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Three Soldiers/Crows: {e}")
        return padroes
    
    def _detectar_morning_evening_star(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #18: Morning Star / Evening Star."""
        padroes = []
        try:
            if len(df) < 3:
                return padroes
            
            vela1 = df.iloc[-3]
            vela2 = df.iloc[-2]
            vela3 = df.iloc[-1]
            
            # Morning Star: bearish -> pequena -> bullish
            if (vela1["close"] < vela1["open"] and  # Bearish
                abs(vela2["close"] - vela2["open"]) < (vela1["high"] - vela1["low"]) * 0.3 and  # Pequena
                vela3["close"] > vela3["open"] and  # Bullish
                vela3["close"] > (vela1["open"] + vela1["close"]) / 2):
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": vela3["datetime"],
                    "tipo_padrao": "morning_evening_star",
                    "direcao": "LONG",
                    "score": 0.75,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": vela2["low"],
                    "suggested_tp": vela3["close"] + (vela3["close"] - vela2["low"]) * 2.3,
                    "meta": {"pattern_type": "morning_star"}
                })
            
            # Evening Star: bullish -> pequena -> bearish
            if (vela1["close"] > vela1["open"] and  # Bullish
                abs(vela2["close"] - vela2["open"]) < (vela1["high"] - vela1["low"]) * 0.3 and  # Pequena
                vela3["close"] < vela3["open"] and  # Bearish
                vela3["close"] < (vela1["open"] + vela1["close"]) / 2):
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": vela3["datetime"],
                    "tipo_padrao": "morning_evening_star",
                    "direcao": "SHORT",
                    "score": 0.75,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": vela2["high"],
                    "suggested_tp": vela3["close"] - (vela2["high"] - vela3["close"]) * 2.3,
                    "meta": {"pattern_type": "evening_star"}
                })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Morning/Evening Star: {e}")
        return padroes
    
    def _detectar_tweezer(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #19: Tweezer Tops / Tweezer Bottoms."""
        padroes = []
        try:
            if len(df) < 2:
                return padroes
            
            penultima = df.iloc[-2]
            ultima = df.iloc[-1]
            
            # Tweezer Tops: dois topos iguais
            if abs(penultima["high"] - ultima["high"]) / max(penultima["high"], ultima["high"]) < 0.005:
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "tweezer",
                    "direcao": "SHORT",
                    "score": 0.65,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": max(penultima["high"], ultima["high"]) * 1.01,
                    "suggested_tp": ultima["close"] - (max(penultima["high"], ultima["high"]) - ultima["close"]) * 2.3,
                    "meta": {"pattern_type": "tweezer_tops"}
                })
            
            # Tweezer Bottoms: dois fundos iguais
            if abs(penultima["low"] - ultima["low"]) / max(penultima["low"], ultima["low"]) < 0.005:
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "tweezer",
                    "direcao": "LONG",
                    "score": 0.65,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": min(penultima["low"], ultima["low"]) * 0.99,
                    "suggested_tp": ultima["close"] + (ultima["close"] - min(penultima["low"], ultima["low"])) * 2.3,
                    "meta": {"pattern_type": "tweezer_bottoms"}
                })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Tweezer: {e}")
        return padroes
    
    def _detectar_harami(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #20: Harami / Harami Cross."""
        padroes = []
        try:
            if len(df) < 2:
                return padroes
            
            penultima = df.iloc[-2]
            ultima = df.iloc[-1]
            
            # Harami: vela pequena dentro da vela anterior
            if (ultima["high"] < penultima["high"] and 
                ultima["low"] > penultima["low"] and
                abs(ultima["close"] - ultima["open"]) < abs(penultima["close"] - penultima["open"]) * 0.5):
                
                direction = "LONG" if penultima["close"] < penultima["open"] else "SHORT"  # Reversão
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "harami",
                    "direcao": direction,
                    "score": 0.65,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": penultima["low"] if direction == "LONG" else penultima["high"],
                    "suggested_tp": None,
                    "meta": {"pattern_type": "harami"}
                })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Harami: {e}")
        return padroes
    
    def _detectar_piercing_dark_cloud(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #21: Piercing Line / Dark Cloud Cover."""
        padroes = []
        try:
            if len(df) < 2:
                return padroes
            
            penultima = df.iloc[-2]
            ultima = df.iloc[-1]
            
            # Piercing Line: bearish -> bullish que fecha acima do meio
            if (penultima["close"] < penultima["open"] and
                ultima["close"] > ultima["open"] and
                ultima["close"] > (penultima["open"] + penultima["close"]) / 2 and
                ultima["open"] < penultima["close"]):
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "piercing_dark_cloud",
                    "direcao": "LONG",
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": penultima["low"],
                    "suggested_tp": ultima["close"] + (ultima["close"] - penultima["low"]) * 2.3,
                    "meta": {"pattern_type": "piercing_line"}
                })
            
            # Dark Cloud Cover: bullish -> bearish que fecha abaixo do meio
            if (penultima["close"] > penultima["open"] and
                ultima["close"] < ultima["open"] and
                ultima["close"] < (penultima["open"] + penultima["close"]) / 2 and
                ultima["open"] > penultima["close"]):
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "piercing_dark_cloud",
                    "direcao": "SHORT",
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": penultima["high"],
                    "suggested_tp": ultima["close"] - (penultima["high"] - ultima["close"]) * 2.3,
                    "meta": {"pattern_type": "dark_cloud_cover"}
                })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Piercing/Dark Cloud: {e}")
        return padroes
    
    def _detectar_gap(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #22: Gap types (breakaway / runaway / exhaustion)."""
        padroes = []
        try:
            if len(df) < 2:
                return padroes
            
            penultima = df.iloc[-2]
            ultima = df.iloc[-1]
            
            # Gap para cima
            if ultima["low"] > penultima["high"]:
                gap_size = ultima["low"] - penultima["high"]
                gap_percent = gap_size / penultima["close"] * 100
                
                if gap_percent > 0.5:  # Gap significativo
                    direction = "LONG"
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "gap",
                        "direcao": direction,
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": penultima["high"],
                        "suggested_tp": ultima["close"] + gap_size * 2.3,
                        "meta": {"pattern_type": "breakaway_gap", "gap_percent": float(gap_percent)}
                    })
            
            # Gap para baixo
            elif ultima["high"] < penultima["low"]:
                gap_size = penultima["low"] - ultima["high"]
                gap_percent = gap_size / penultima["close"] * 100
                
                if gap_percent > 0.5:
                    direction = "SHORT"
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "gap",
                        "direcao": direction,
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": penultima["low"],
                        "suggested_tp": ultima["close"] - gap_size * 2.3,
                        "meta": {"pattern_type": "breakaway_gap", "gap_percent": float(gap_percent)}
                    })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Gap: {e}")
        return padroes
    
    def _detectar_macd_divergence(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #23: MACD divergence + histogram reversal."""
        padroes = []
        try:
            if len(df) < 30:
                return padroes
            
            # Calcula MACD
            ema12 = df["close"].ewm(span=12, adjust=False).mean()
            ema26 = df["close"].ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()
            histogram = macd - signal
            
            # Detecta divergência
            ultimas_10 = df.iloc[-10:]
            macd_ultimas = macd.iloc[-10:]
            
            # Bullish divergence: preço faz lower low, MACD faz higher low
            price_low_1 = ultimas_10["low"].iloc[0]
            price_low_2 = ultimas_10["low"].iloc[-1]
            macd_low_1 = macd_ultimas.iloc[0]
            macd_low_2 = macd_ultimas.iloc[-1]
            
            if price_low_2 < price_low_1 and macd_low_2 > macd_low_1 and histogram.iloc[-1] > 0:
                ultima = df.iloc[-1]
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "macd_divergence",
                    "direcao": "LONG",
                    "score": 0.75,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["low"],
                    "suggested_tp": ultima["close"] + (ultima["close"] - ultima["low"]) * 2.3,
                    "meta": {"pattern_type": "macd_bullish_divergence"}
                })
            
            # Bearish divergence: preço faz higher high, MACD faz lower high
            price_high_1 = ultimas_10["high"].iloc[0]
            price_high_2 = ultimas_10["high"].iloc[-1]
            macd_high_1 = macd_ultimas.iloc[0]
            macd_high_2 = macd_ultimas.iloc[-1]
            
            if price_high_2 > price_high_1 and macd_high_2 < macd_high_1 and histogram.iloc[-1] < 0:
                ultima = df.iloc[-1]
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "macd_divergence",
                    "direcao": "SHORT",
                    "score": 0.75,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["high"],
                    "suggested_tp": ultima["close"] - (ultima["high"] - ultima["close"]) * 2.3,
                    "meta": {"pattern_type": "macd_bearish_divergence"}
                })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar MACD divergence: {e}")
        return padroes
    
    def _detectar_atr_breakout(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #24: ATR-based volatility breakout (> k × ATR)."""
        padroes = []
        try:
            if len(df) < 20:
                return padroes
            
            # Calcula ATR
            high_low = df["high"] - df["low"]
            high_close = np.abs(df["high"] - df["close"].shift())
            low_close = np.abs(df["low"] - df["close"].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean()
            
            ultima = df.iloc[-1]
            atr_atual = atr.iloc[-1]
            
            # Breakout > 2 × ATR
            range_atual = ultima["high"] - ultima["low"]
            if range_atual > atr_atual * 2:
                direction = "LONG" if ultima["close"] > ultima["open"] else "SHORT"
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "atr_breakout",
                    "direcao": direction,
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["low"] if direction == "LONG" else ultima["high"],
                    "suggested_tp": ultima["close"] + (atr_atual * 2.3) if direction == "LONG" else ultima["close"] - (atr_atual * 2.3),
                    "meta": {"atr_multiplier": float(range_atual / atr_atual)}
                })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar ATR breakout: {e}")
        return padroes
    
    def _detectar_fibonacci_confluence(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #25: Fibonacci retracement confluence (61.8% + suporte)."""
        padroes = []
        try:
            if len(df) < 50:
                return padroes
            
            # Identifica swing high e low
            window = df.iloc[-50:]
            swing_high = window["high"].max()
            swing_low = window["low"].min()
            range_size = swing_high - swing_low
            
            # Níveis Fibonacci
            fib_618 = swing_low + range_size * 0.618
            fib_50 = swing_low + range_size * 0.5
            fib_382 = swing_low + range_size * 0.382
            
            ultima = df.iloc[-1]
            price = ultima["close"]
            
            # Preço próximo ao nível 61.8% (confluência)
            if abs(price - fib_618) / price < 0.01:  # Dentro de 1%
                direction = "LONG" if price < fib_618 else "SHORT"
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "fibonacci_confluence",
                    "direcao": direction,
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": swing_low if direction == "LONG" else swing_high,
                    "suggested_tp": None,
                    "meta": {"fib_level": 0.618, "distance_percent": float(abs(price - fib_618) / price * 100)}
                })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Fibonacci: {e}")
        return padroes
    
    def _detectar_liquidity_sweep(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #26: Liquidity sweep (long wick into stops)."""
        padroes = []
        try:
            if len(df) < 10:
                return padroes
            
            ultima = df.iloc[-1]
            window = df.iloc[-10:]
            
            # Long wick superior (liquidity sweep para cima)
            upper_wick = ultima["high"] - max(ultima["open"], ultima["close"])
            body = abs(ultima["close"] - ultima["open"])
            range_candle = ultima["high"] - ultima["low"]
            
            if upper_wick > body * 2 and upper_wick > range_candle * 0.6:
                # Sweep para cima seguido de reversão
                if ultima["close"] < ultima["open"]:
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "liquidity_sweep",
                        "direcao": "SHORT",
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": ultima["high"],
                        "suggested_tp": ultima["close"] - (ultima["high"] - ultima["close"]) * 2.3,
                        "meta": {"pattern_type": "liquidity_sweep_up"}
                    })
            
            # Long wick inferior (liquidity sweep para baixo)
            lower_wick = min(ultima["open"], ultima["close"]) - ultima["low"]
            if lower_wick > body * 2 and lower_wick > range_candle * 0.6:
                # Sweep para baixo seguido de reversão
                if ultima["close"] > ultima["open"]:
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "liquidity_sweep",
                        "direcao": "LONG",
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": ultima["low"],
                        "suggested_tp": ultima["close"] + (ultima["close"] - ultima["low"]) * 2.3,
                        "meta": {"pattern_type": "liquidity_sweep_down"}
                    })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Liquidity Sweep: {e}")
        return padroes
    
    def _detectar_picos_vales_robusto(self, df: pd.DataFrame, min_periods: int = 3) -> tuple:
        """
        Detecta picos e vales usando algoritmo robusto com filtragem de ruído.
        
        Args:
            df: DataFrame com dados OHLCV
            min_periods: Número mínimo de períodos para considerar pico/vale significativo
        
        Returns:
            tuple: (peaks, troughs) onde cada é lista de (index, price)
        """
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        
        # Calcula ATR para filtrar picos/vales muito pequenos
        atr = self._calcular_atr(df, periodo=14) if len(df) >= 14 else df["high"].std()
        threshold = atr * 0.5  # Pico/vale deve ser pelo menos 50% do ATR
        
        peaks = []
        troughs = []
        
        # Algoritmo melhorado: verifica múltiplos períodos e magnitude
        for i in range(min_periods, len(highs) - min_periods):
            # Pico: verifica se é máximo local em janela maior
            is_peak = True
            peak_value = highs[i]
            
            # Verifica se é maior que todos os vizinhos em janela
            for j in range(max(0, i - min_periods), min(len(highs), i + min_periods + 1)):
                if j != i and highs[j] >= peak_value:
                    is_peak = False
                    break
            
            # Verifica magnitude (deve ser significativo)
            if is_peak and peak_value > closes[i] + threshold:
                peaks.append((i, peak_value))
            
            # Vale: verifica se é mínimo local em janela maior
            is_trough = True
            trough_value = lows[i]
            
            for j in range(max(0, i - min_periods), min(len(lows), i + min_periods + 1)):
                if j != i and lows[j] <= trough_value:
                    is_trough = False
                    break
            
            # Verifica magnitude
            if is_trough and trough_value < closes[i] - threshold:
                troughs.append((i, trough_value))
        
        # Remove picos/vales muito próximos (mantém apenas o mais significativo)
        peaks = self._filtrar_proximos(peaks, min_distance=5)
        troughs = self._filtrar_proximos(troughs, min_distance=5)
        
        return sorted(peaks, key=lambda x: x[0]), sorted(troughs, key=lambda x: x[0])
    
    def _filtrar_proximos(self, pontos: List[tuple], min_distance: int) -> List[tuple]:
        """Remove pontos muito próximos, mantendo apenas o mais significativo."""
        if len(pontos) <= 1:
            return pontos
        
        filtrados = [pontos[0]]
        for i in range(1, len(pontos)):
            idx_atual, price_atual = pontos[i]
            idx_anterior, price_anterior = filtrados[-1]
            
            if abs(idx_atual - idx_anterior) >= min_distance:
                filtrados.append(pontos[i])
            else:
                # Mantém o ponto com maior magnitude
                if abs(price_atual) > abs(price_anterior):
                    filtrados[-1] = pontos[i]
        
        return filtrados
    
    def _calcular_atr(self, df: pd.DataFrame, periodo: int = 14) -> float:
        """Calcula Average True Range (ATR)."""
        if len(df) < periodo + 1:
            return df["high"].std()
        
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        
        tr_list = []
        for i in range(1, len(df)):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            )
            tr_list.append(tr)
        
        return np.mean(tr_list[-periodo:]) if tr_list else df["high"].std()
    
    def _validar_proporcao_fibonacci(self, valor: float, alvo: float, tolerancia: float = 0.05) -> bool:
        """
        Valida se uma proporção está próxima de um nível Fibonacci.
        
        Args:
            valor: Valor a validar
            alvo: Nível Fibonacci alvo (ex: 0.618, 0.786, 1.272)
            tolerancia: Tolerância percentual (padrão 5%)
        
        Returns:
            bool: True se está dentro da tolerância
        """
        return abs(valor - alvo) <= (alvo * tolerancia)
    
    def _detectar_harmonic_patterns(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #27: Harmonic patterns (AB=CD, Gartley, Butterfly, Bat, Crab) — completo."""
        padroes = []
        try:
            if len(df) < 50:
                return padroes
            
            # Log TRACE: Cálculos internos
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] TRACE — Iniciando detecção de padrões harmônicos para {symbol} {timeframe}"
                )
            
            window = df.iloc[-80:]  # Janela maior para padrões harmônicos
            
            # Detecta picos e vales usando algoritmo robusto
            peaks, troughs = self._detectar_picos_vales_robusto(window, min_periods=3)
            
            if len(peaks) < 2 or len(troughs) < 2:
                return padroes
            
            # Detecta padrão AB=CD (Bullish)
            # Estrutura: A (trough) -> B (peak) -> C (trough) -> D (peak)
            # AB ≈ CD em tamanho
            if len(troughs) >= 2 and len(peaks) >= 2:
                for i in range(len(troughs) - 1):
                    for j in range(len(peaks) - 1):
                        if troughs[i][0] < peaks[j][0] < troughs[i+1][0] < peaks[j+1][0]:
                            A_idx, A_price = troughs[i]
                            B_idx, B_price = peaks[j]
                            C_idx, C_price = troughs[i+1]
                            D_idx, D_price = peaks[j+1]
                            
                            # Calcula retrações Fibonacci
                            AB = abs(B_price - A_price)
                            BC = abs(C_price - B_price)
                            CD = abs(D_price - C_price)
                            
                            # Verifica se AB ≈ CD (tolerância de 5%)
                            if AB > 0 and CD > 0:
                                ratio_ab_cd = min(AB, CD) / max(AB, CD)
                                
                                # Verifica retrações Fibonacci típicas
                                bc_retrace = BC / AB if AB > 0 else 0
                                
                                # Padrão AB=CD válido: ratio próximo de 1.0 e retração BC entre 0.382-0.886
                                # Validação mais rigorosa usando função de validação Fibonacci
                                if ratio_ab_cd >= 0.95 and 0.382 <= bc_retrace <= 0.886:
                                    # Verifica completion: D deve estar próximo da última vela
                                    ultima = df.iloc[-1]
                                    completion = abs(D_idx - len(window) + 1) <= 3  # D dentro de 3 velas do final
                                    
                                    if completion:
                                        padroes.append({
                                            "symbol": symbol,
                                            "timeframe": timeframe,
                                            "open_time": ultima["datetime"],
                                            "tipo_padrao": "harmonic_ab_cd_bullish",
                                            "direcao": "LONG",
                                            "score": 0.80 if ratio_ab_cd >= 0.98 else 0.75,  # Score maior se ratio perfeito
                                            "confidence": 1.0,
                                            "regime": regime.value,
                                            "suggested_sl": C_price * 0.995,  # SL abaixo de C
                                            "suggested_tp": D_price + (D_price - C_price) * 1.618,  # TP em 161.8% de CD
                                            "meta": {
                                                "pattern_type": "AB=CD_Bullish",
                                                "A": float(A_price),
                                                "B": float(B_price),
                                                "C": float(C_price),
                                                "D": float(D_price),
                                                "ratio_ab_cd": float(ratio_ab_cd),
                                                "bc_retrace": float(bc_retrace),
                                                "completion": True
                                            }
                                        })
                                        
                                        # Log TRACE: Cálculo interno
                                        if self.logger:
                                            self.logger.debug(
                                                f"[{self.PLUGIN_NAME}] TRACE — AB=CD Bullish detectado (completo): "
                                                f"A={A_price:.4f} B={B_price:.4f} C={C_price:.4f} D={D_price:.4f} "
                                                f"ratio={ratio_ab_cd:.3f}, completion=True"
                                            )
            
            # Detecta padrão Gartley (Bullish)
            # Estrutura: X (trough) -> A (peak) -> B (trough) -> C (peak) -> D (trough)
            # Retrações: AB = 61.8% de XA, BC = 38.2-88.6% de AB, CD = 78.6% de XA
            if len(troughs) >= 3 and len(peaks) >= 2:
                for i in range(len(troughs) - 2):
                    for j in range(len(peaks) - 1):
                        if troughs[i][0] < peaks[j][0] < troughs[i+1][0] < peaks[j+1][0] < troughs[i+2][0]:
                            X_idx, X_price = troughs[i]
                            A_idx, A_price = peaks[j]
                            B_idx, B_price = troughs[i+1]
                            C_idx, C_price = peaks[j+1]
                            D_idx, D_price = troughs[i+2]
                            
                            XA = abs(A_price - X_price)
                            AB = abs(B_price - A_price)
                            BC = abs(C_price - B_price)
                            CD = abs(D_price - C_price)
                            
                            if XA > 0 and AB > 0:
                                ab_retrace = AB / XA
                                bc_retrace = BC / AB if AB > 0 else 0
                                cd_retrace = CD / XA if XA > 0 else 0
                                
                                # Gartley válido: AB ≈ 61.8%, BC ≈ 38.2-88.6%, CD ≈ 78.6%
                                # Validação mais rigorosa usando função de validação Fibonacci
                                ab_valid = self._validar_proporcao_fibonacci(ab_retrace, 0.618, tolerancia=0.05)
                                cd_valid = self._validar_proporcao_fibonacci(cd_retrace, 0.786, tolerancia=0.05)
                                
                                if ab_valid and 0.30 <= bc_retrace <= 0.95 and cd_valid:
                                    # Verifica completion: D deve estar próximo da última vela
                                    ultima = df.iloc[-1]
                                    completion = abs(D_idx - len(window) + 1) <= 3
                                    
                                    if completion:
                                        padroes.append({
                                            "symbol": symbol,
                                            "timeframe": timeframe,
                                            "open_time": ultima["datetime"],
                                            "tipo_padrao": "harmonic_gartley_bullish",
                                            "direcao": "LONG",
                                            "score": 0.85,  # Score maior para Gartley
                                            "confidence": 1.0,
                                            "regime": regime.value,
                                            "suggested_sl": D_price * 0.995,
                                            "suggested_tp": D_price + (D_price - X_price) * 0.618,
                                            "meta": {
                                                "pattern_type": "Gartley_Bullish",
                                                "X": float(X_price),
                                                "A": float(A_price),
                                                "B": float(B_price),
                                                "C": float(C_price),
                                                "D": float(D_price),
                                                "ab_retrace": float(ab_retrace),
                                                "bc_retrace": float(bc_retrace),
                                                "cd_retrace": float(cd_retrace),
                                                "completion": True
                                            }
                                        })
                                        
                                        # Log TRACE: Cálculo interno
                                        if self.logger:
                                            self.logger.debug(
                                                f"[{self.PLUGIN_NAME}] TRACE — Gartley Bullish detectado (completo): "
                                                f"X={X_price:.4f} A={A_price:.4f} B={B_price:.4f} "
                                                f"C={C_price:.4f} D={D_price:.4f}, completion=True"
                                            )
            
            # Detecta padrão Butterfly (Bullish)
            # Estrutura: X (trough) -> A (peak) -> B (trough) -> C (peak) -> D (trough)
            # Retrações: AB = 78.6% de XA, BC = 38.2-88.6% de AB, CD = 127.2% ou 161.8% de XA
            if len(troughs) >= 3 and len(peaks) >= 2:
                for i in range(len(troughs) - 2):
                    for j in range(len(peaks) - 1):
                        if troughs[i][0] < peaks[j][0] < troughs[i+1][0] < peaks[j+1][0] < troughs[i+2][0]:
                            X_idx, X_price = troughs[i]
                            A_idx, A_price = peaks[j]
                            B_idx, B_price = troughs[i+1]
                            C_idx, C_price = peaks[j+1]
                            D_idx, D_price = troughs[i+2]
                            
                            XA = abs(A_price - X_price)
                            AB = abs(B_price - A_price)
                            BC = abs(C_price - B_price)
                            CD = abs(D_price - C_price)
                            
                            if XA > 0 and AB > 0:
                                ab_retrace = AB / XA
                                bc_retrace = BC / AB if AB > 0 else 0
                                cd_retrace = CD / XA if XA > 0 else 0
                                
                                # Butterfly válido: AB ≈ 78.6%, CD ≈ 127.2% ou 161.8%
                                ab_valid = self._validar_proporcao_fibonacci(ab_retrace, 0.786, tolerancia=0.05)
                                cd_valid_127 = self._validar_proporcao_fibonacci(cd_retrace, 1.272, tolerancia=0.10)
                                cd_valid_161 = self._validar_proporcao_fibonacci(cd_retrace, 1.618, tolerancia=0.10)
                                
                                if ab_valid and 0.30 <= bc_retrace <= 0.95 and (cd_valid_127 or cd_valid_161):
                                    ultima = df.iloc[-1]
                                    completion = abs(D_idx - len(window) + 1) <= 3
                                    
                                    if completion:
                                        padroes.append({
                                            "symbol": symbol,
                                            "timeframe": timeframe,
                                            "open_time": ultima["datetime"],
                                            "tipo_padrao": "harmonic_butterfly_bullish",
                                            "direcao": "LONG",
                                            "score": 0.85,
                                            "confidence": 1.0,
                                            "regime": regime.value,
                                            "suggested_sl": D_price * 0.995,
                                            "suggested_tp": D_price + (D_price - X_price) * 0.618,
                                            "meta": {
                                                "pattern_type": "Butterfly_Bullish",
                                                "X": float(X_price),
                                                "A": float(A_price),
                                                "B": float(B_price),
                                                "C": float(C_price),
                                                "D": float(D_price),
                                                "ab_retrace": float(ab_retrace),
                                                "bc_retrace": float(bc_retrace),
                                                "cd_retrace": float(cd_retrace),
                                                "completion": True
                                            }
                                        })
                                        
                                        if self.logger:
                                            self.logger.debug(
                                                f"[{self.PLUGIN_NAME}] TRACE — Butterfly Bullish detectado (completo): "
                                                f"X={X_price:.4f} A={A_price:.4f} B={B_price:.4f} "
                                                f"C={C_price:.4f} D={D_price:.4f}, completion=True"
                                            )
            
            # Detecta padrão Bat (Bullish)
            # Estrutura: X (trough) -> A (peak) -> B (trough) -> C (peak) -> D (trough)
            # Retrações: AB = 38.2% ou 50% de XA, BC = 38.2-88.6% de AB, CD = 88.6% de XA
            if len(troughs) >= 3 and len(peaks) >= 2:
                for i in range(len(troughs) - 2):
                    for j in range(len(peaks) - 1):
                        if troughs[i][0] < peaks[j][0] < troughs[i+1][0] < peaks[j+1][0] < troughs[i+2][0]:
                            X_idx, X_price = troughs[i]
                            A_idx, A_price = peaks[j]
                            B_idx, B_price = troughs[i+1]
                            C_idx, C_price = peaks[j+1]
                            D_idx, D_price = troughs[i+2]
                            
                            XA = abs(A_price - X_price)
                            AB = abs(B_price - A_price)
                            BC = abs(C_price - B_price)
                            CD = abs(D_price - C_price)
                            
                            if XA > 0 and AB > 0:
                                ab_retrace = AB / XA
                                bc_retrace = BC / AB if AB > 0 else 0
                                cd_retrace = CD / XA if XA > 0 else 0
                                
                                # Bat válido: AB ≈ 38.2% ou 50%, CD ≈ 88.6%
                                ab_valid_382 = self._validar_proporcao_fibonacci(ab_retrace, 0.382, tolerancia=0.05)
                                ab_valid_50 = self._validar_proporcao_fibonacci(ab_retrace, 0.50, tolerancia=0.05)
                                cd_valid = self._validar_proporcao_fibonacci(cd_retrace, 0.886, tolerancia=0.05)
                                
                                if (ab_valid_382 or ab_valid_50) and 0.30 <= bc_retrace <= 0.95 and cd_valid:
                                    ultima = df.iloc[-1]
                                    completion = abs(D_idx - len(window) + 1) <= 3
                                    
                                    if completion:
                                        padroes.append({
                                            "symbol": symbol,
                                            "timeframe": timeframe,
                                            "open_time": ultima["datetime"],
                                            "tipo_padrao": "harmonic_bat_bullish",
                                            "direcao": "LONG",
                                            "score": 0.85,
                                            "confidence": 1.0,
                                            "regime": regime.value,
                                            "suggested_sl": D_price * 0.995,
                                            "suggested_tp": D_price + (D_price - X_price) * 0.618,
                                            "meta": {
                                                "pattern_type": "Bat_Bullish",
                                                "X": float(X_price),
                                                "A": float(A_price),
                                                "B": float(B_price),
                                                "C": float(C_price),
                                                "D": float(D_price),
                                                "ab_retrace": float(ab_retrace),
                                                "bc_retrace": float(bc_retrace),
                                                "cd_retrace": float(cd_retrace),
                                                "completion": True
                                            }
                                        })
                                        
                                        if self.logger:
                                            self.logger.debug(
                                                f"[{self.PLUGIN_NAME}] TRACE — Bat Bullish detectado (completo): "
                                                f"X={X_price:.4f} A={A_price:.4f} B={B_price:.4f} "
                                                f"C={C_price:.4f} D={D_price:.4f}, completion=True"
                                            )
            
            # Detecta padrão Crab (Bullish)
            # Estrutura: X (trough) -> A (peak) -> B (trough) -> C (peak) -> D (trough)
            # Retrações: AB = 38.2% ou 50% ou 61.8% de XA, BC = 38.2-88.6% de AB, CD = 161.8% de XA
            if len(troughs) >= 3 and len(peaks) >= 2:
                for i in range(len(troughs) - 2):
                    for j in range(len(peaks) - 1):
                        if troughs[i][0] < peaks[j][0] < troughs[i+1][0] < peaks[j+1][0] < troughs[i+2][0]:
                            X_idx, X_price = troughs[i]
                            A_idx, A_price = peaks[j]
                            B_idx, B_price = troughs[i+1]
                            C_idx, C_price = peaks[j+1]
                            D_idx, D_price = troughs[i+2]
                            
                            XA = abs(A_price - X_price)
                            AB = abs(B_price - A_price)
                            BC = abs(C_price - B_price)
                            CD = abs(D_price - C_price)
                            
                            if XA > 0 and AB > 0:
                                ab_retrace = AB / XA
                                bc_retrace = BC / AB if AB > 0 else 0
                                cd_retrace = CD / XA if XA > 0 else 0
                                
                                # Crab válido: AB ≈ 38.2%, 50% ou 61.8%, CD ≈ 161.8%
                                ab_valid_382 = self._validar_proporcao_fibonacci(ab_retrace, 0.382, tolerancia=0.05)
                                ab_valid_50 = self._validar_proporcao_fibonacci(ab_retrace, 0.50, tolerancia=0.05)
                                ab_valid_618 = self._validar_proporcao_fibonacci(ab_retrace, 0.618, tolerancia=0.05)
                                cd_valid = self._validar_proporcao_fibonacci(cd_retrace, 1.618, tolerancia=0.10)
                                
                                if (ab_valid_382 or ab_valid_50 or ab_valid_618) and 0.30 <= bc_retrace <= 0.95 and cd_valid:
                                    ultima = df.iloc[-1]
                                    completion = abs(D_idx - len(window) + 1) <= 3
                                    
                                    if completion:
                                        padroes.append({
                                            "symbol": symbol,
                                            "timeframe": timeframe,
                                            "open_time": ultima["datetime"],
                                            "tipo_padrao": "harmonic_crab_bullish",
                                            "direcao": "LONG",
                                            "score": 0.85,
                                            "confidence": 1.0,
                                            "regime": regime.value,
                                            "suggested_sl": D_price * 0.995,
                                            "suggested_tp": D_price + (D_price - X_price) * 0.618,
                                            "meta": {
                                                "pattern_type": "Crab_Bullish",
                                                "X": float(X_price),
                                                "A": float(A_price),
                                                "B": float(B_price),
                                                "C": float(C_price),
                                                "D": float(D_price),
                                                "ab_retrace": float(ab_retrace),
                                                "bc_retrace": float(bc_retrace),
                                                "cd_retrace": float(cd_retrace),
                                                "completion": True
                                            }
                                        })
                                        
                                        if self.logger:
                                            self.logger.debug(
                                                f"[{self.PLUGIN_NAME}] TRACE — Crab Bullish detectado (completo): "
                                                f"X={X_price:.4f} A={A_price:.4f} B={B_price:.4f} "
                                                f"C={C_price:.4f} D={D_price:.4f}, completion=True"
                                            )
            
            # Detecta versões Bearish dos padrões (mesma lógica, invertida)
            # Para Bearish: X (peak) -> A (trough) -> B (peak) -> C (trough) -> D (peak)
            if len(peaks) >= 3 and len(troughs) >= 2:
                # Gartley Bearish
                for i in range(len(peaks) - 2):
                    for j in range(len(troughs) - 1):
                        if peaks[i][0] < troughs[j][0] < peaks[i+1][0] < troughs[j+1][0] < peaks[i+2][0]:
                            X_idx, X_price = peaks[i]
                            A_idx, A_price = troughs[j]
                            B_idx, B_price = peaks[i+1]
                            C_idx, C_price = troughs[j+1]
                            D_idx, D_price = peaks[i+2]
                            
                            XA = abs(A_price - X_price)
                            AB = abs(B_price - A_price)
                            BC = abs(C_price - B_price)
                            CD = abs(D_price - C_price)
                            
                            if XA > 0 and AB > 0:
                                ab_retrace = AB / XA
                                bc_retrace = BC / AB if AB > 0 else 0
                                cd_retrace = CD / XA if XA > 0 else 0
                                
                                ab_valid = self._validar_proporcao_fibonacci(ab_retrace, 0.618, tolerancia=0.05)
                                cd_valid = self._validar_proporcao_fibonacci(cd_retrace, 0.786, tolerancia=0.05)
                                
                                if ab_valid and 0.30 <= bc_retrace <= 0.95 and cd_valid:
                                    ultima = df.iloc[-1]
                                    completion = abs(D_idx - len(window) + 1) <= 3
                                    
                                    if completion:
                                        padroes.append({
                                            "symbol": symbol,
                                            "timeframe": timeframe,
                                            "open_time": ultima["datetime"],
                                            "tipo_padrao": "harmonic_gartley_bearish",
                                            "direcao": "SHORT",
                                            "score": 0.85,
                                            "confidence": 1.0,
                                            "regime": regime.value,
                                            "suggested_sl": D_price * 1.005,
                                            "suggested_tp": D_price - (X_price - D_price) * 0.618,
                                            "meta": {
                                                "pattern_type": "Gartley_Bearish",
                                                "X": float(X_price),
                                                "A": float(A_price),
                                                "B": float(B_price),
                                                "C": float(C_price),
                                                "D": float(D_price),
                                                "ab_retrace": float(ab_retrace),
                                                "bc_retrace": float(bc_retrace),
                                                "cd_retrace": float(cd_retrace),
                                                "completion": True
                                            }
                                        })
            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Harmonic: {e}")
        return padroes
    
    def _detectar_volume_price_divergence(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #28: Volume–price divergence (decoupling em tendência)."""
        padroes = []
        try:
            if len(df) < 20:
                return padroes
            
            window = df.iloc[-20:]
            
            # Volume médio
            volume_medio = window["volume"].mean()
            volume_trend = np.polyfit(range(len(window)), window["volume"].values, 1)[0]
            price_trend = np.polyfit(range(len(window)), window["close"].values, 1)[0]
            
            ultima = df.iloc[-1]
            
            # Divergência bearish: preço sobe, volume cai
            if price_trend > 0 and volume_trend < 0 and ultima["volume"] < volume_medio * 0.8:
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "volume_price_divergence",
                    "direcao": "SHORT",
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["high"],
                    "suggested_tp": ultima["close"] - (ultima["high"] - ultima["close"]) * 2.3,
                    "meta": {"pattern_type": "bearish_volume_divergence"}
                })
            
            # Divergência bullish: preço cai, volume cai (exaustão)
            if price_trend < 0 and volume_trend < 0 and ultima["volume"] < volume_medio * 0.8:
                padroes.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": ultima["datetime"],
                    "tipo_padrao": "volume_price_divergence",
                    "direcao": "LONG",
                    "score": 0.7,
                    "confidence": 1.0,
                    "regime": regime.value,
                    "suggested_sl": ultima["low"],
                    "suggested_tp": ultima["close"] + (ultima["close"] - ultima["low"]) * 2.3,
                    "meta": {"pattern_type": "bullish_volume_divergence"}
                })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Volume-Price Divergence: {e}")
        return padroes
    
    def _detectar_multi_timeframe(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado,
        dados_multi_tf: Optional[Dict[str, pd.DataFrame]] = None
    ) -> List[Dict[str, Any]]:
        """
        Padrão #29: Multi-timeframe confirmation (15m + 1h) — completo.
        
        Requer dados de múltiplos timeframes para confirmação real.
        Se dados_multi_tf não estiver disponível, usa aproximação com EMAs maiores.
        """
        padroes = []
        try:
            if len(df) < 20:
                return padroes
            
            ultima = df.iloc[-1]
            close_atual = ultima["close"]
            
            # Se temos dados de múltiplos timeframes, usa confirmação real
            if dados_multi_tf and len(dados_multi_tf) > 1:
                # Mapeamento de timeframes para confirmação
                # 15m confirma com 1h e 4h
                # 1h confirma com 4h
                timeframe_hierarquia = {
                    "15m": ["1h", "4h"],
                    "1h": ["4h"],
                    "4h": []  # Timeframe maior não precisa confirmação
                }
                
                timeframes_confirmacao = timeframe_hierarquia.get(timeframe, [])
                
                if timeframes_confirmacao:
                    # Detecta padrão no timeframe atual
                    window_atual = df.iloc[-10:]
                    high_recent = window_atual["high"].max()
                    low_recent = window_atual["low"].min()
                    
                    # Verifica tendência em timeframes maiores
                    confirmacoes = []
                    pesos = {"1h": 0.6, "4h": 0.4}  # Timeframe maior tem mais peso
                    
                    for tf_conf in timeframes_confirmacao:
                        if tf_conf in dados_multi_tf:
                            df_conf = dados_multi_tf[tf_conf]
                            
                            if len(df_conf) >= 20:
                                # Calcula tendência no timeframe de confirmação
                                ema_fast = df_conf["close"].ewm(span=9, adjust=False).mean()
                                ema_slow = df_conf["close"].ewm(span=21, adjust=False).mean()
                                
                                ema_fast_atual = ema_fast.iloc[-1]
                                ema_slow_atual = ema_slow.iloc[-1]
                                
                                # Tendência bullish se EMA rápida > EMA lenta
                                tendencia = "BULLISH" if ema_fast_atual > ema_slow_atual else "BEARISH"
                                
                                # Força da tendência (distância entre EMAs normalizada pelo preço)
                                distancia_ema = abs(ema_fast_atual - ema_slow_atual) / close_atual
                                forca_tendencia = min(distancia_ema * 100, 1.0)  # Normaliza para 0-1
                                
                                confirmacoes.append({
                                    "timeframe": tf_conf,
                                    "tendencia": tendencia,
                                    "forca": forca_tendencia,
                                    "peso": pesos.get(tf_conf, 0.5),
                                    "ema_fast": float(ema_fast_atual),
                                    "ema_slow": float(ema_slow_atual)
                                })
                    
                    # Calcula confirmação consolidada
                    if confirmacoes:
                        # Soma ponderada das tendências
                        score_bullish = sum(
                            c["peso"] * c["forca"] 
                            for c in confirmacoes 
                            if c["tendencia"] == "BULLISH"
                        )
                        score_bearish = sum(
                            c["peso"] * c["forca"] 
                            for c in confirmacoes 
                            if c["tendencia"] == "BEARISH"
                        )
                        
                        # Calcula EMA rápida do timeframe atual para validação
                        ema_fast_atual_tf = df["close"].ewm(span=9, adjust=False).mean().iloc[-1] if len(df) >= 9 else close_atual
                        
                        # Confirmação bullish: padrão no 15m + tendência bullish em timeframes maiores
                        if score_bullish > 0.4 and close_atual > ema_fast_atual_tf:
                            # Verifica se há padrão de breakout ou reversão no timeframe atual
                            if close_atual > high_recent * 0.98:  # Próximo do high recente
                                padroes.append({
                                    "symbol": symbol,
                                    "timeframe": timeframe,
                                    "open_time": ultima["datetime"],
                                    "tipo_padrao": "multi_timeframe_confirmation_bullish",
                                    "direcao": "LONG",
                                    "score": min(0.75 + score_bullish * 0.2, 0.95),  # Score maior com confirmação forte
                                    "confidence": 1.0,
                                    "regime": regime.value,
                                    "suggested_sl": low_recent * 0.995,
                                    "suggested_tp": close_atual + (close_atual - low_recent) * 2.3,
                                    "meta": {
                                        "pattern_type": "MTF_Confirmation_Bullish",
                                        "timeframe_base": timeframe,
                                        "timeframes_confirmacao": [c["timeframe"] for c in confirmacoes],
                                        "score_bullish": float(score_bullish),
                                        "score_bearish": float(score_bearish),
                                        "confirmacoes": confirmacoes
                                    }
                                })
                        
                        # Confirmação bearish
                        elif score_bearish > 0.4 and close_atual < ema_fast_atual_tf:
                            if close_atual < low_recent * 1.02:  # Próximo do low recente
                                padroes.append({
                                    "symbol": symbol,
                                    "timeframe": timeframe,
                                    "open_time": ultima["datetime"],
                                    "tipo_padrao": "multi_timeframe_confirmation_bearish",
                                    "direcao": "SHORT",
                                    "score": min(0.75 + score_bearish * 0.2, 0.95),
                                    "confidence": 1.0,
                                    "regime": regime.value,
                                    "suggested_sl": high_recent * 1.005,
                                    "suggested_tp": close_atual - (high_recent - close_atual) * 2.3,
                                    "meta": {
                                        "pattern_type": "MTF_Confirmation_Bearish",
                                        "timeframe_base": timeframe,
                                        "timeframes_confirmacao": [c["timeframe"] for c in confirmacoes],
                                        "score_bullish": float(score_bullish),
                                        "score_bearish": float(score_bearish),
                                        "confirmacoes": confirmacoes
                                    }
                                })
                        
                        # Log TRACE: Cálculo interno
                        if self.logger and padroes:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] TRACE — Multi-timeframe confirmation detectado: "
                                f"{timeframe} close={close_atual:.4f}, "
                                f"confirmacoes={len(confirmacoes)}, "
                                f"score_bullish={score_bullish:.2f}, score_bearish={score_bearish:.2f}"
                            )
            
            else:
                # Fallback: usa aproximação com EMAs maiores (comportamento anterior)
                if timeframe == "15m":
                    ema_20 = df["close"].ewm(span=20, adjust=False).mean()
                    ema_50 = df["close"].ewm(span=50, adjust=False).mean() if len(df) >= 50 else ema_20
                    
                    ema_20_atual = ema_20.iloc[-1]
                    ema_50_atual = ema_50.iloc[-1] if len(df) >= 50 else ema_20_atual
                    
                    tendencia_1h = "BULLISH" if ema_20_atual > ema_50_atual else "BEARISH"
                    
                    window_15m = df.iloc[-10:]
                    high_recent = window_15m["high"].max()
                    low_recent = window_15m["low"].min()
                    
                    if tendencia_1h == "BULLISH" and close_atual > ema_20_atual:
                        if close_atual > high_recent * 0.98:
                            padroes.append({
                                "symbol": symbol,
                                "timeframe": timeframe,
                                "open_time": ultima["datetime"],
                                "tipo_padrao": "multi_timeframe_confirmation_bullish",
                                "direcao": "LONG",
                                "score": 0.70,  # Score menor para aproximação
                                "confidence": 0.8,  # Confidence menor para aproximação
                                "regime": regime.value,
                                "suggested_sl": low_recent * 0.995,
                                "suggested_tp": close_atual + (close_atual - low_recent) * 2.3,
                                "meta": {
                                    "pattern_type": "MTF_Confirmation_Bullish_Proxy",
                                    "timeframe_base": "15m",
                                    "timeframe_confirmation": "1h_proxy",
                                    "tendencia_1h": tendencia_1h,
                                    "ema_20": float(ema_20_atual),
                                    "ema_50": float(ema_50_atual),
                                    "aproximacao": True
                                }
                            })
                    
                    elif tendencia_1h == "BEARISH" and close_atual < ema_20_atual:
                        if close_atual < low_recent * 1.02:
                            padroes.append({
                                "symbol": symbol,
                                "timeframe": timeframe,
                                "open_time": ultima["datetime"],
                                "tipo_padrao": "multi_timeframe_confirmation_bearish",
                                "direcao": "SHORT",
                                "score": 0.70,
                                "confidence": 0.8,
                                "regime": regime.value,
                                "suggested_sl": high_recent * 1.005,
                                "suggested_tp": close_atual - (high_recent - close_atual) * 2.3,
                                "meta": {
                                    "pattern_type": "MTF_Confirmation_Bearish_Proxy",
                                    "timeframe_base": "15m",
                                    "timeframe_confirmation": "1h_proxy",
                                    "tendencia_1h": tendencia_1h,
                                    "ema_20": float(ema_20_atual),
                                    "ema_50": float(ema_50_atual),
                                    "aproximacao": True
                                }
                            })
            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Multi-timeframe: {e}")
        return padroes
    
    def _detectar_order_flow_proxy(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str, 
        regime: RegimeMercado
    ) -> List[Dict[str, Any]]:
        """Padrão #30: Order-flow proxy (wick + volume = stop hunt)."""
        padroes = []
        try:
            if len(df) < 5:
                return padroes
            
            ultima = df.iloc[-1]
            window = df.iloc[-5:]
            volume_medio = window["volume"].mean()
            
            # Long wick + volume alto = possível stop hunt
            upper_wick = ultima["high"] - max(ultima["open"], ultima["close"])
            lower_wick = min(ultima["open"], ultima["close"]) - ultima["low"]
            range_candle = ultima["high"] - ultima["low"]
            
            # Stop hunt para cima (wick superior longo + volume)
            if upper_wick > range_candle * 0.4 and ultima["volume"] > volume_medio * 1.5:
                if ultima["close"] < ultima["open"]:  # Reversão após hunt
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "order_flow_proxy",
                        "direcao": "SHORT",
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": ultima["high"],
                        "suggested_tp": ultima["close"] - (ultima["high"] - ultima["close"]) * 2.3,
                        "meta": {"pattern_type": "stop_hunt_up"}
                    })
            
            # Stop hunt para baixo (wick inferior longo + volume)
            if lower_wick > range_candle * 0.4 and ultima["volume"] > volume_medio * 1.5:
                if ultima["close"] > ultima["open"]:  # Reversão após hunt
                    padroes.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "open_time": ultima["datetime"],
                        "tipo_padrao": "order_flow_proxy",
                        "direcao": "LONG",
                        "score": 0.7,
                        "confidence": 1.0,
                        "regime": regime.value,
                        "suggested_sl": ultima["low"],
                        "suggested_tp": ultima["close"] + (ultima["close"] - ultima["low"]) * 2.3,
                        "meta": {"pattern_type": "stop_hunt_down"}
                    })
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao detectar Order Flow Proxy: {e}")
        return padroes
    
    def _aplicar_confidence_decay(
        self, 
        padroes: List[Dict[str, Any]], 
        symbol: str, 
        timeframe: str
    ) -> List[Dict[str, Any]]:
        """
        Aplica confidence decay aos padrões detectados.
        
        Conforme proxima_atualizacao.md:
        confidence_score = base_score * exp(-0.01 * days_since_last_win)
        
        Args:
            padroes: Lista de padrões detectados
            symbol: Símbolo do par
            timeframe: Timeframe
        
        Returns:
            list: Padrões com confidence ajustado
        """
        padroes_ajustados = []
        
        for padrao in padroes:
            tipo_padrao = padrao.get("tipo_padrao")
            base_score = padrao.get("score", 0.8)
            
            # Busca último win deste padrão
            days_since_last_win = self._obter_days_since_last_win(tipo_padrao, symbol, timeframe)
            
            # Aplica decay
            confidence_score = base_score * math.exp(-self.confidence_decay_lambda * days_since_last_win)
            
            # Atualiza confidence
            padrao["confidence"] = confidence_score
            padrao["meta"]["days_since_last_win"] = days_since_last_win
            padrao["meta"]["base_score"] = base_score
            
            # Marca quarentena se confidence < 0.5
            if confidence_score < 0.5:
                padrao["meta"]["em_quarentena"] = True
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Padrão {tipo_padrao} em quarentena "
                        f"(confidence: {confidence_score:.2f})"
                    )
            
            padroes_ajustados.append(padrao)
        
        return padroes_ajustados
    
    def _obter_days_since_last_win(
        self, 
        tipo_padrao: str, 
        symbol: str, 
        timeframe: str
    ) -> int:
        """
        Obtém dias desde último win deste padrão.
        
        Args:
            tipo_padrao: Tipo do padrão
            symbol: Símbolo do par
            timeframe: Timeframe
        
        Returns:
            int: Dias desde último win (0 se nunca houve win)
        """
        # Por enquanto retorna 0 (não há histórico ainda)
        # Futuramente buscará do banco de dados
        return 0
    
    def _calcular_score_final(
        self, 
        padroes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Calcula score final dos padrões.
        
        Conforme proxima_atualizacao.md:
        final_score = (technical_score * 0.6) + (confidence_score * 0.4)
        
        Args:
            padroes: Lista de padrões com confidence ajustado
        
        Returns:
            list: Padrões com final_score calculado
        """
        padroes_finais = []
        
        for padrao in padroes:
            technical_score = padrao.get("score", 0.8)
            confidence_score = padrao.get("confidence", 1.0)
            
            final_score = (technical_score * 0.6) + (confidence_score * 0.4)
            
            padrao["final_score"] = final_score
            padroes_finais.append(padrao)
        
        return padroes_finais
    
    def rankear_por_performance(
        self,
        metricas_backtest: Dict[str, Dict[str, Any]],
        oos_percentual_min: float = 0.30,
        expectancy_oos_ratio_min: float = 0.70
    ) -> List[Dict[str, Any]]:
        """
        Rankeia padrões por performance real baseado em métricas de backtest.
        
        Conforme proxima_atualizacao.md:
        - OOS ≥ 30% dos dados
        - Expectancy OOS > 70% in-sample
        
        Args:
            metricas_backtest: Dicionário com métricas por tipo de padrão
                Formato: {tipo_padrao: {expectancy_in_sample, expectancy_oos, oos_percentual, ...}}
            oos_percentual_min: Percentual mínimo de OOS (padrão: 0.30 = 30%)
            expectancy_oos_ratio_min: Ratio mínimo de Expectancy OOS vs In-Sample (padrão: 0.70 = 70%)
        
        Returns:
            list: Lista de padrões rankeados ordenados por performance
        """
        ranking = []
        
        for tipo_padrao, metricas in metricas_backtest.items():
            expectancy_in_sample = metricas.get("expectancy_in_sample", 0.0)
            expectancy_oos = metricas.get("expectancy_oos", 0.0)
            oos_percentual = metricas.get("oos_percentual", 0.0)
            
            # Verifica critérios de elegibilidade
            if oos_percentual < oos_percentual_min:
                continue  # Não tem OOS suficiente
            
            if expectancy_in_sample <= 0:
                continue  # Expectancy in-sample deve ser positiva
            
            # Calcula ratio de Expectancy OOS vs In-Sample
            expectancy_ratio = expectancy_oos / expectancy_in_sample if expectancy_in_sample > 0 else 0.0
            
            if expectancy_ratio < expectancy_oos_ratio_min:
                continue  # Expectancy OOS não atinge threshold
            
            # Score de ranking (combina múltiplas métricas)
            winrate = metricas.get("winrate", 0.0)
            sharpe = metricas.get("sharpe_condicional", 0.0) or 0.0
            avg_rr = metricas.get("avg_rr", 0.0) or 0.0
            
            # Score composto: expectancy (40%), winrate (20%), sharpe (20%), avg_rr (20%)
            score_ranking = (
                expectancy_oos * 0.4 +
                winrate * 0.2 +
                sharpe * 0.2 +
                (avg_rr / 10.0) * 0.2  # Normaliza avg_rr (assumindo range 0-10)
            )
            
            ranking.append({
                "tipo_padrao": tipo_padrao,
                "score_ranking": score_ranking,
                "expectancy_in_sample": expectancy_in_sample,
                "expectancy_oos": expectancy_oos,
                "expectancy_ratio": expectancy_ratio,
                "oos_percentual": oos_percentual,
                "winrate": winrate,
                "sharpe": sharpe,
                "avg_rr": avg_rr,
                "metricas_completas": metricas
            })
        
        # Ordena por score_ranking (maior primeiro)
        ranking.sort(key=lambda x: x["score_ranking"], reverse=True)
        
        return ranking
    
    def calcular_ensemble_score(
        self,
        padroes: List[Dict[str, Any]],
        janela_temporal_minutos: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Calcula score de ensemble quando múltiplos padrões convergem.
        
        Conforme proxima_atualizacao.md:
        - Combina detecções quando 2-3 padrões convergem (mesmo símbolo/timeframe/direção)
        - Peso maior quando confidence > 0.8
        - Score combinado aumenta quando múltiplos padrões apontam mesma direção
        
        Args:
            padroes: Lista de padrões detectados
            janela_temporal_minutos: Janela temporal para considerar convergência (padrão: 15 min)
        
        Returns:
            list: Padrões com ensemble_score calculado
        """
        if not padroes:
            return padroes
        
        # Agrupa padrões por símbolo/timeframe/direção
        grupos = {}
        for padrao in padroes:
            key = (
                padrao.get("symbol"),
                padrao.get("timeframe"),
                padrao.get("direcao")
            )
            
            if key not in grupos:
                grupos[key] = []
            grupos[key].append(padrao)
        
        # Calcula ensemble_score para cada grupo
        padroes_com_ensemble = []
        
        for key, padroes_grupo in grupos.items():
            if len(padroes_grupo) == 1:
                # Apenas um padrão: ensemble_score = final_score
                padrao = padroes_grupo[0]
                padrao["ensemble_score"] = padrao.get("final_score", 0.0)
                padroes_com_ensemble.append(padrao)
            else:
                # Múltiplos padrões convergindo: calcula ensemble
                # Filtra padrões na mesma janela temporal
                padroes_convergentes = []
                if len(padroes_grupo) > 1:
                    # Ordena por tempo
                    padroes_grupo_sorted = sorted(
                        padroes_grupo,
                        key=lambda p: p.get("open_time", datetime.min)
                    )
                    
                    # Agrupa por janela temporal
                    for i, padrao in enumerate(padroes_grupo_sorted):
                        if i == 0:
                            padroes_convergentes.append([padrao])
                        else:
                            # Verifica se está na mesma janela temporal
                            tempo_anterior = padroes_convergentes[-1][0].get("open_time")
                            tempo_atual = padrao.get("open_time")
                            
                            if isinstance(tempo_anterior, datetime) and isinstance(tempo_atual, datetime):
                                diff_minutos = (tempo_atual - tempo_anterior).total_seconds() / 60
                                if diff_minutos <= janela_temporal_minutos:
                                    padroes_convergentes[-1].append(padrao)
                                else:
                                    padroes_convergentes.append([padrao])
                            else:
                                padroes_convergentes.append([padrao])
                
                # Calcula ensemble_score para cada grupo convergente
                for grupo_convergente in padroes_convergentes:
                    if len(grupo_convergente) == 1:
                        padrao = grupo_convergente[0]
                        padrao["ensemble_score"] = padrao.get("final_score", 0.0)
                        padroes_com_ensemble.append(padrao)
                    else:
                        # Ensemble: combina scores com pesos baseados em confidence
                        scores_ponderados = []
                        total_peso = 0.0
                        
                        for padrao in grupo_convergente:
                            final_score = padrao.get("final_score", 0.0)
                            confidence = padrao.get("confidence", 1.0)
                            
                            # Peso maior se confidence > 0.8
                            peso = confidence * 1.5 if confidence > 0.8 else confidence
                            
                            scores_ponderados.append(final_score * peso)
                            total_peso += peso
                        
                        # Score de ensemble: média ponderada + bônus por convergência
                        if total_peso > 0:
                            ensemble_base = sum(scores_ponderados) / total_peso
                            # Bônus: +0.1 por cada padrão adicional (máximo +0.2 para 3+ padrões)
                            bonus_convergencia = min(0.2, (len(grupo_convergente) - 1) * 0.1)
                            ensemble_score = min(1.0, ensemble_base + bonus_convergencia)
                        else:
                            ensemble_score = grupo_convergente[0].get("final_score", 0.0)
                        
                        # Aplica ensemble_score a todos os padrões do grupo
                        for padrao in grupo_convergente:
                            padrao["ensemble_score"] = ensemble_score
                            padrao["ensemble_count"] = len(grupo_convergente)
                            padroes_com_ensemble.append(padrao)
        
        return padroes_com_ensemble
    
    def _persistir_padroes(self, padroes: List[Dict[str, Any]]):
        """
        Persiste padrões detectados no banco de dados.
        
        PASSO 4: Verifica duplicatas antes de inserir para evitar loops.
        Usa constraint UNIQUE ou verificação manual por (symbol, timeframe, open_time, tipo_padrao).
        
        Args:
            padroes: Lista de padrões detectados
        """
        try:
            if not padroes:
                return
            
            # PASSO 4: Verifica duplicatas antes de inserir
            # Remove duplicatas na mesma execução (evita múltiplas inserções do mesmo padrão)
            padroes_ja_vistos = set()
            
            # Prepara dados para inserção (apenas padrões únicos)
            dados_inserir = []
            for padrao in padroes:
                open_time = padrao.get("open_time")
                # Converte datetime para formato compatível com PostgreSQL
                if isinstance(open_time, pd.Timestamp):
                    open_time = open_time.to_pydatetime()
                elif isinstance(open_time, datetime):
                    open_time = open_time
                else:
                    # Tenta converter string ou timestamp
                    if isinstance(open_time, str):
                        open_time = pd.to_datetime(open_time).to_pydatetime()
                    elif isinstance(open_time, (int, float)):
                        open_time = datetime.utcfromtimestamp(open_time / 1000 if open_time > 1e10 else open_time)
                
                # PASSO 4: Verifica se padrão já foi processado nesta execução (evita duplicatas na memória)
                chave_padrao = (
                    str(padrao.get("symbol", "")),
                    str(padrao.get("timeframe", "")),
                    str(open_time),
                    str(padrao.get("tipo_padrao", ""))
                )
                
                if chave_padrao in padroes_ja_vistos:
                    # Padrão duplicado na mesma execução, pula
                    continue
                
                # Adiciona à lista de vistos
                padroes_ja_vistos.add(chave_padrao)
                
                # Prepara meta como JSON (PostgreSQL JSONB)
                meta = padrao.get("meta", {})
                # Converte valores numpy/pandas para tipos nativos Python
                meta_serializado = {}
                for k, v in meta.items():
                    if isinstance(v, (np.integer, np.floating)):
                        meta_serializado[k] = float(v)
                    elif isinstance(v, (np.ndarray, pd.Series)):
                        meta_serializado[k] = v.tolist()
                    elif isinstance(v, pd.Timestamp):
                        meta_serializado[k] = v.isoformat()
                    else:
                        meta_serializado[k] = v
                
                dados_inserir.append({
                    "symbol": padrao.get("symbol"),
                    "timeframe": padrao.get("timeframe"),
                    "open_time": open_time,
                    "tipo_padrao": padrao.get("tipo_padrao"),
                    "direcao": padrao.get("direcao"),
                    "score": float(padrao.get("score", 0.0)),
                    "confidence": float(padrao.get("confidence", 0.0)),
                    "regime": padrao.get("regime"),
                    "suggested_sl": float(padrao.get("suggested_sl")) if padrao.get("suggested_sl") else None,
                    "suggested_tp": float(padrao.get("suggested_tp")) if padrao.get("suggested_tp") else None,
                    "final_score": float(padrao.get("final_score", 0.0)),
                    "meta": meta_serializado,
                })
            
            # PASSO 4: Persiste via gerenciador_banco (apenas padrões únicos)
            if self.gerenciador_banco and dados_inserir:
                try:
                    # Usa transação para garantir atomicidade
                    self.persistir_dados("padroes_detectados", dados_inserir)
                    
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] {len(dados_inserir)} padrão(ões) único(s) persistido(s) "
                            f"(de {len(padroes)} detectado(s))"
                        )
                except Exception as persist_error:
                    # Log erro mas não interrompe execução
                    if self.logger:
                        self.logger.error(
                            f"[{self.PLUGIN_NAME}] Erro ao persistir padrões: {persist_error}",
                            exc_info=True
                        )
            
            # Loga cada padrão detectado
            if self.gerenciador_log:
                for padrao in padroes:
                    try:
                        self.gerenciador_log.log_padrao_detectado(
                            nome_padrao=padrao.get("tipo_padrao", "Unknown"),
                            moeda=padrao.get("symbol", "Unknown"),
                            timeframe=padrao.get("timeframe", "Unknown"),
                            direcao=padrao.get("direcao", "Unknown"),
                            score=float(padrao.get("score", 0.0)) if padrao.get("score") else None,
                            confidence=float(padrao.get("confidence", 0.0)) if padrao.get("confidence") else None,
                            porcentagem_sucesso=None,  # Será calculado futuramente
                            detalhes={
                                "regime": padrao.get("regime"),
                                "final_score": float(padrao.get("final_score", 0.0)) if padrao.get("final_score") else None,
                            }
                        )
                    except Exception as log_error:
                        # Não interrompe o processo se houver erro no log
                        if self.logger:
                            self.logger.warning(
                                f"[{self.PLUGIN_NAME}] Erro ao logar padrão: {log_error}"
                            )
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao persistir padrões: {e}",
                    exc_info=True,
                )
    
    def _resumir_por_tipo(
        self, 
        padroes: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Resume padrões detectados por tipo.
        
        Args:
            padroes: Lista de padrões detectados
        
        Returns:
            dict: Contagem por tipo de padrão
        """
        resumo = {}
        for padrao in padroes:
            tipo = padrao.get("tipo_padrao", "unknown")
            resumo[tipo] = resumo.get(tipo, 0) + 1
        return resumo
    
    def validar_temporal(
        self,
        dados_velas: Dict[str, Any],
        tipo_validacao: str = "walk_forward"
    ) -> Dict[str, Any]:
        """
        Executa validação temporal dos padrões detectados.
        
        Conforme proxima_atualizacao.md:
        - Walk-Forward: 60% treino → 40% teste
        - Rolling Window: 180 dias → recalcula a cada 30 dias
        - Out-of-Sample (OOS): ≥ 30% dos dados nunca vistos
        
        Args:
            dados_velas: Dados de velas organizados por par/timeframe
            tipo_validacao: Tipo de validação ("walk_forward", "rolling_window", "oos")
        
        Returns:
            dict: Resultado da validação com métricas
        """
        try:
            if tipo_validacao == "walk_forward":
                return self._validar_walk_forward(dados_velas)
            elif tipo_validacao == "rolling_window":
                return self._validar_rolling_window(dados_velas)
            elif tipo_validacao == "oos":
                return self._validar_oos(dados_velas)
            else:
                return {
                    "status": "erro",
                    "mensagem": f"Tipo de validação inválido: {tipo_validacao}",
                }
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro na validação temporal: {e}",
                    exc_info=True,
                )
            return {
                "status": "erro",
                "mensagem": str(e),
            }
    
    def _validar_walk_forward(
        self,
        dados_velas: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executa validação Walk-Forward (60% treino → 40% teste).
        
        Args:
            dados_velas: Dados de velas organizados por par/timeframe
        
        Returns:
            dict: Métricas de validação
        """
        resultados = {}
        
        for symbol, dados_par in dados_velas.items():
            if not isinstance(dados_par, dict):
                continue
            
            for timeframe, dados_tf in dados_par.items():
                if not isinstance(dados_tf, dict) or "velas" not in dados_tf:
                    continue
                
                velas = dados_tf.get("velas", [])
                if len(velas) < 100:  # Mínimo de velas para validação
                    continue
                
                # Divide em treino (60%) e teste (40%)
                split_index = int(len(velas) * self.walk_forward_treino)
                velas_treino = velas[:split_index]
                velas_teste = velas[split_index:]
                
                # Detecta padrões no treino
                df_treino = self._velas_para_dataframe(velas_treino)
                padroes_treino = self._detectar_padroes_top30(
                    df_treino, symbol, timeframe, RegimeMercado.INDEFINIDO
                )
                
                # Detecta padrões no teste
                df_teste = self._velas_para_dataframe(velas_teste)
                padroes_teste = self._detectar_padroes_top30(
                    df_teste, symbol, timeframe, RegimeMercado.INDEFINIDO
                )
                
                # Calcula métricas
                metricas_treino = self._calcular_metricas(padroes_treino, velas_treino, symbol, timeframe, "in_sample")
                metricas_teste = self._calcular_metricas(padroes_teste, velas_teste, symbol, timeframe, "out_of_sample")
                
                resultados[f"{symbol}_{timeframe}"] = {
                    "treino": metricas_treino,
                    "teste": metricas_teste,
                    "periodo_treino": {
                        "inicio": velas_treino[0].get("datetime") if velas_treino else None,
                        "fim": velas_treino[-1].get("datetime") if velas_treino else None,
                    },
                    "periodo_teste": {
                        "inicio": velas_teste[0].get("datetime") if velas_teste else None,
                        "fim": velas_teste[-1].get("datetime") if velas_teste else None,
                    },
                }
                
                # Persiste métricas no banco
                if metricas_treino:
                    self._persistir_metricas(metricas_treino)
                if metricas_teste:
                    self._persistir_metricas(metricas_teste)
        
        return {
            "status": "ok",
            "tipo_validacao": "walk_forward",
            "resultados": resultados,
        }
    
    def _validar_rolling_window(
        self,
        dados_velas: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executa validação Rolling Window completa (180 dias → recalcula a cada 30 dias).
        
        Conforme proxima_atualizacao.md:
        - Janela deslizante de 180 dias
        - Recalcula métricas a cada 30 dias
        - Tracking de performance ao longo do tempo
        - Detecção de degradação de performance
        - Ajuste automático de confidence baseado em performance recente
        
        Args:
            dados_velas: Dados de velas organizados por par/timeframe
        
        Returns:
            dict: Métricas de validação com histórico de performance
        """
        resultados = {}
        historico_performance = {}
        
        try:
            # Log INFO: Início da validação
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Iniciando validação Rolling Window — janela: {self.rolling_window_dias} dias, recalculo: {self.rolling_recalculo_dias} dias"
                )
            
            for symbol, dados_par in dados_velas.items():
                if not isinstance(dados_par, dict):
                    continue
                
                for timeframe, dados_tf in dados_par.items():
                    if not isinstance(dados_tf, dict) or "velas" not in dados_tf:
                        continue
                    
                    velas = dados_tf.get("velas", [])
                    if len(velas) < self.rolling_window_dias:  # Precisa de pelo menos 180 dias
                        if self.logger:
                            self.logger.warning(
                                f"[{self.PLUGIN_NAME}] WARNING — Dados insuficientes para Rolling Window: {symbol} {timeframe} — {len(velas)} velas (mínimo: {self.rolling_window_dias})"
                            )
                        continue
                    
                    # Converte para DataFrame e ordena por data
                    df = self._velas_para_dataframe(velas)
                    if "datetime" in df.columns:
                        df = df.sort_values("datetime")
                    
                    # Calcula número de janelas
                    total_dias = len(df)
                    num_janelas = max(1, (total_dias - self.rolling_window_dias) // self.rolling_recalculo_dias + 1)
                    
                    metricas_janelas = []
                    performance_historica = []
                    
                    # Log DEBUG: Detalhamento
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] DEBUG — Rolling Window para {symbol} {timeframe}: {num_janelas} janela(s) de {self.rolling_window_dias} dias"
                        )
                    
                    # Processa cada janela deslizante
                    for i in range(num_janelas):
                        inicio_janela = i * self.rolling_recalculo_dias
                        fim_janela = min(inicio_janela + self.rolling_window_dias, total_dias)
                        
                        if fim_janela - inicio_janela < self.rolling_window_dias:
                            # Última janela pode ser menor
                            break
                        
                        # Extrai dados da janela
                        df_janela = df.iloc[inicio_janela:fim_janela].copy()
                        
                        # Detecta regime
                        regime = self._detectar_regime(df_janela)
                        
                        # Detecta padrões na janela
                        padroes_janela = self._detectar_padroes_top30(df_janela, symbol, timeframe, regime)
                        
                        # Calcula métricas para esta janela
                        metricas_janela = self._calcular_metricas(
                            padroes_janela, 
                            df_janela.to_dict('records'), 
                            symbol, 
                            timeframe, 
                            "rolling"
                        )
                        
                        # Adiciona informações da janela
                        if metricas_janela:
                            for metrica in metricas_janela:
                                metrica["janela_inicio"] = inicio_janela
                                metrica["janela_fim"] = fim_janela
                                metrica["janela_numero"] = i + 1
                                metrica["data_inicio"] = df_janela.iloc[0].get("datetime") if len(df_janela) > 0 else None
                                metrica["data_fim"] = df_janela.iloc[-1].get("datetime") if len(df_janela) > 0 else None
                        
                        metricas_janelas.extend(metricas_janela if metricas_janela else [])
                        
                        # Log TRACE: Cálculos internos
                        if self.logger and padroes_janela:
                            tipos_detectados = [p.get("tipo_padrao", "unknown") for p in padroes_janela]
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] TRACE — Janela {i+1}/{num_janelas}: {len(padroes_janela)} padrão(ões) — {', '.join(set(tipos_detectados))}"
                            )
                    
                    # Agrupa métricas por tipo de padrão para análise de degradação
                    metricas_por_tipo = {}
                    for metrica in metricas_janelas:
                        tipo_padrao = metrica.get("tipo_padrao", "unknown")
                        if tipo_padrao not in metricas_por_tipo:
                            metricas_por_tipo[tipo_padrao] = []
                        metricas_por_tipo[tipo_padrao].append(metrica)
                    
                    # Analisa degradação de performance e ajusta confidence
                    ajustes_confidence = {}
                    for tipo_padrao, metricas_tipo in metricas_por_tipo.items():
                        if len(metricas_tipo) < 2:
                            continue  # Precisa de pelo menos 2 janelas para detectar degradação
                        
                        # Ordena por número da janela (mais antiga primeiro)
                        metricas_tipo_sorted = sorted(metricas_tipo, key=lambda x: x.get("janela_numero", 0))
                        
                        # Compara performance da primeira metade vs segunda metade
                        meio = len(metricas_tipo_sorted) // 2
                        primeira_metade = metricas_tipo_sorted[:meio]
                        segunda_metade = metricas_tipo_sorted[meio:]
                        
                        # Calcula média de expectancy para cada metade
                        exp_primeira = np.mean([m.get("expectancy", 0) for m in primeira_metade if m.get("expectancy")])
                        exp_segunda = np.mean([m.get("expectancy", 0) for m in segunda_metade if m.get("expectancy")])
                        
                        # Detecta degradação (expectancy caiu mais de 30%)
                        if exp_primeira > 0 and exp_segunda < exp_primeira * 0.7:
                            degradacao = (exp_primeira - exp_segunda) / exp_primeira
                            ajustes_confidence[tipo_padrao] = {
                                "degradacao_detectada": True,
                                "degradacao_percentual": degradacao * 100,
                                "expectancy_primeira_metade": exp_primeira,
                                "expectancy_segunda_metade": exp_segunda,
                                "ajuste_confidence": -0.1  # Reduz confidence em 10%
                            }
                            
                            # Log WARNING: Degradação detectada
                            if self.logger:
                                self.logger.warning(
                                    f"[{self.PLUGIN_NAME}] WARNING — Degradação detectada: {tipo_padrao} em {symbol} {timeframe} — "
                                    f"Expectancy caiu {degradacao*100:.1f}% ({exp_primeira:.4f} → {exp_segunda:.4f})"
                                )
                        else:
                            ajustes_confidence[tipo_padrao] = {
                                "degradacao_detectada": False,
                                "ajuste_confidence": 0.0
                            }
                    
                    # Armazena histórico de performance
                    historico_performance[f"{symbol}_{timeframe}"] = {
                        "metricas_por_janela": metricas_janelas,
                        "metricas_por_tipo": metricas_por_tipo,
                        "ajustes_confidence": ajustes_confidence,
                        "total_janelas": num_janelas,
                    }
                    
                    # Persiste métricas no banco
                    for metrica in metricas_janelas:
                        self._persistir_metricas([metrica])
                    
                    resultados[f"{symbol}_{timeframe}"] = {
                        "total_janelas": num_janelas,
                        "metricas_por_tipo": {k: len(v) for k, v in metricas_por_tipo.items()},
                        "ajustes_confidence": ajustes_confidence,
                    }
            
            # Log INFO: Resumo final
            if self.logger:
                total_janelas = sum(r.get("total_janelas", 0) for r in resultados.values())
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Rolling Window concluído — {len(resultados)} par(es)/timeframe(s) processado(s), {total_janelas} janela(s) total"
                )
            
            return {
                "status": "ok",
                "tipo_validacao": "rolling_window",
                "resultados": resultados,
                "historico_performance": historico_performance,
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro na validação Rolling Window: {e}",
                    exc_info=True,
                )
            return {
                "status": "erro",
                "tipo_validacao": "rolling_window",
                "mensagem": str(e),
                "resultados": resultados,
            }
    
    def _validar_oos(
        self,
        dados_velas: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executa validação Out-of-Sample (≥ 30% dos dados nunca vistos).
        
        Args:
            dados_velas: Dados de velas organizados por par/timeframe
        
        Returns:
            dict: Métricas de validação
        """
        resultados = {}
        
        for symbol, dados_par in dados_velas.items():
            if not isinstance(dados_par, dict):
                continue
            
            for timeframe, dados_tf in dados_par.items():
                if not isinstance(dados_tf, dict) or "velas" not in dados_tf:
                    continue
                
                velas = dados_tf.get("velas", [])
                if len(velas) < 100:
                    continue
                
                # Separa OOS (últimos 30% ou mais)
                oos_percentual = max(self.oos_percentual, 0.30)
                split_index = int(len(velas) * (1 - oos_percentual))
                velas_in_sample = velas[:split_index]
                velas_oos = velas[split_index:]
                
                # Detecta padrões no in-sample
                df_in_sample = self._velas_para_dataframe(velas_in_sample)
                padroes_in_sample = self._detectar_padroes_top30(
                    df_in_sample, symbol, timeframe, RegimeMercado.INDEFINIDO
                )
                
                # Detecta padrões no OOS
                df_oos = self._velas_para_dataframe(velas_oos)
                padroes_oos = self._detectar_padroes_top30(
                    df_oos, symbol, timeframe, RegimeMercado.INDEFINIDO
                )
                
                # Calcula métricas
                metricas_in_sample = self._calcular_metricas(
                    padroes_in_sample, velas_in_sample, symbol, timeframe, "in_sample"
                )
                metricas_oos = self._calcular_metricas(
                    padroes_oos, velas_oos, symbol, timeframe, "out_of_sample"
                )
                
                resultados[f"{symbol}_{timeframe}"] = {
                    "in_sample": metricas_in_sample,
                    "oos": metricas_oos,
                    "percentual_oos": oos_percentual,
                }
                
                # Persiste métricas
                if metricas_in_sample:
                    self._persistir_metricas(metricas_in_sample)
                if metricas_oos:
                    self._persistir_metricas(metricas_oos)
        
        return {
            "status": "ok",
            "tipo_validacao": "oos",
            "resultados": resultados,
        }
    
    def _calcular_metricas(
        self,
        padroes: List[Dict[str, Any]],
        velas: List[Dict[str, Any]],
        symbol: str,
        timeframe: str,
        tipo_validacao: str
    ) -> List[Dict[str, Any]]:
        """
        Calcula métricas de performance por padrão.
        
        Conforme proxima_atualizacao.md:
        - Frequency: Ocorrências por 1.000 velas
        - Precision: % de setups que atingiram target
        - Expectancy: EV por trade
        - Sharpe Condicional: Retorno médio / desvio por padrão
        - Drawdown condicional: Max perda por padrão
        - Winrate: % de trades vencedores
        - Avg R:R: Risk:Reward médio
        
        Args:
            padroes: Lista de padrões detectados
            velas: Lista de velas usadas
            symbol: Símbolo do par
            timeframe: Timeframe
            tipo_validacao: Tipo de validação
        
        Returns:
            list: Lista de métricas por padrão
        """
        metricas = []
        
        if not padroes or not velas:
            return metricas
        
        # Agrupa padrões por tipo
        padroes_por_tipo = {}
        for padrao in padroes:
            tipo = padrao.get("tipo_padrao", "unknown")
            if tipo not in padroes_por_tipo:
                padroes_por_tipo[tipo] = []
            padroes_por_tipo[tipo].append(padrao)
        
        # Calcula métricas por tipo de padrão
        for tipo_padrao, padroes_tipo in padroes_por_tipo.items():
            # Frequency: ocorrências por 1000 velas
            frequency = (len(padroes_tipo) / len(velas)) * 1000
            
            # Por enquanto, métricas básicas
            # Futuramente: simular trades e calcular métricas reais
            metrica = {
                "tipo_padrao": tipo_padrao,
                "symbol": symbol,
                "timeframe": timeframe,
                "periodo_inicio": velas[0].get("datetime") if velas else None,
                "periodo_fim": velas[-1].get("datetime") if velas else None,
                "frequency": float(frequency),
                "precision": None,  # Será calculado com backtest
                "recall": None,
                "expectancy": None,
                "sharpe_condicional": None,
                "drawdown_condicional": None,
                "winrate": None,
                "avg_rr": None,
                "total_trades": len(padroes_tipo),
                "trades_win": 0,  # Será calculado com backtest
                "trades_loss": 0,
                "tipo_validacao": tipo_validacao,
            }
            
            metricas.append(metrica)
        
        return metricas
    
    def _persistir_metricas(self, metricas: List[Dict[str, Any]]):
        """
        Persiste métricas no banco de dados.
        
        Args:
            metricas: Lista de métricas por padrão
        """
        try:
            if not metricas:
                return
            
            # Prepara dados para inserção
            dados_inserir = []
            for metrica in metricas:
                periodo_inicio = metrica.get("periodo_inicio")
                periodo_fim = metrica.get("periodo_fim")
                
                # Converte datetime se necessário
                if isinstance(periodo_inicio, pd.Timestamp):
                    periodo_inicio = periodo_inicio.to_pydatetime()
                elif isinstance(periodo_inicio, datetime):
                    periodo_inicio = periodo_inicio
                elif isinstance(periodo_inicio, str):
                    periodo_inicio = pd.to_datetime(periodo_inicio).to_pydatetime()
                
                if isinstance(periodo_fim, pd.Timestamp):
                    periodo_fim = periodo_fim.to_pydatetime()
                elif isinstance(periodo_fim, datetime):
                    periodo_fim = periodo_fim
                elif isinstance(periodo_fim, str):
                    periodo_fim = pd.to_datetime(periodo_fim).to_pydatetime()
                
                dados_inserir.append({
                    "tipo_padrao": metrica.get("tipo_padrao"),
                    "symbol": metrica.get("symbol"),
                    "timeframe": metrica.get("timeframe"),
                    "periodo_inicio": periodo_inicio,
                    "periodo_fim": periodo_fim,
                    "frequency": float(metrica.get("frequency", 0.0)),
                    "precision": float(metrica.get("precision")) if metrica.get("precision") else None,
                    "recall": float(metrica.get("recall")) if metrica.get("recall") else None,
                    "expectancy": float(metrica.get("expectancy")) if metrica.get("expectancy") else None,
                    "sharpe_condicional": float(metrica.get("sharpe_condicional")) if metrica.get("sharpe_condicional") else None,
                    "drawdown_condicional": float(metrica.get("drawdown_condicional")) if metrica.get("drawdown_condicional") else None,
                    "winrate": float(metrica.get("winrate")) if metrica.get("winrate") else None,
                    "avg_rr": float(metrica.get("avg_rr")) if metrica.get("avg_rr") else None,
                    "total_trades": int(metrica.get("total_trades", 0)),
                    "trades_win": int(metrica.get("trades_win", 0)),
                    "trades_loss": int(metrica.get("trades_loss", 0)),
                    "tipo_validacao": metrica.get("tipo_validacao"),
                })
            
            # Persiste via gerenciador_banco
            if self.gerenciador_banco:
                self.persistir_dados("padroes_metricas", dados_inserir)
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao persistir métricas: {e}",
                    exc_info=True,
                )

