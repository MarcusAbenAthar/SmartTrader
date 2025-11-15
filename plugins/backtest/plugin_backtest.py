"""
Plugin de Backtest - Sistema Smart Trader.

Simula trades baseados em padrões detectados e calcula métricas reais de performance.

Conforme STATUS_PROJETO.md (linhas 152-156):
1. Criar módulo de simulação de trades
2. Implementar tracking de posições por padrão
3. Calcular métricas reais baseadas em execuções simuladas
4. Validar padrões retroativamente com dados históricos

__institucional__ = "Smart_Trader Plugin Backtest - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from enum import Enum

try:
    from dateutil.parser import parse as parse_date
except ImportError:
    # Fallback se dateutil não estiver disponível
    def parse_date(date_string):
        return datetime.fromisoformat(date_string.replace('Z', '+00:00'))

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class StatusPosicao(Enum):
    """Status de uma posição no backtest."""
    ABERTA = "aberta"
    FECHADA = "fechada"
    CANCELADA = "cancelada"


class TipoExecucao(Enum):
    """Tipo de execução de trade."""
    MARKET = "market"
    LIMIT = "limit"


class PluginBacktest(Plugin):
    """
    Plugin de simulação de trades (backtest).
    
    Responsabilidades:
    - Simular execução de trades baseados em padrões detectados
    - Rastrear posições abertas/fechadas por padrão
    - Calcular métricas reais: precision, recall, expectancy, winrate, avg R:R, sharpe, drawdown
    - Validar padrões retroativamente com dados históricos
    - Integrar com histórico de velas para validar se padrões atingiram target/stop
    
    Características:
    - Simulação realista: slippage, fees, latência
    - Gerenciamento de capital: position sizing, risk management
    - Métricas estatísticas robustas
    - Validação temporal completa
    """
    
    __institucional__ = "Smart_Trader Plugin Backtest - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginBacktest"
    plugin_versao = "v1.0.0"
    plugin_schema_versao = "v1.0.0"
    plugin_tipo = TipoPlugin.AUXILIAR
    
    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLogProtocol] = None,
        gerenciador_banco: Optional[GerenciadorBancoProtocol] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o PluginBacktest.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            gerenciador_banco: Instância do GerenciadorBanco
            config: Configuração do sistema
        """
        super().__init__(gerenciador_log, gerenciador_banco, config)
        
        # Configurações de backtest
        self.config_backtest = self.config.get("backtest", {})
        
        # Parâmetros de simulação
        self.slippage_pct = self.config_backtest.get("slippage_pct", 0.001)  # 0.1% slippage
        self.fee_pct = self.config_backtest.get("fee_pct", 0.0006)  # 0.06% fee (taker)
        self.latencia_ms = self.config_backtest.get("latencia_ms", 50)  # 50ms latência
        
        # Gerenciamento de capital
        self.capital_inicial = self.config_backtest.get("capital_inicial", 10000.0)  # $10k
        self.risco_por_trade = self.config_backtest.get("risco_por_trade", 0.02)  # 2% por trade
        self.max_posicoes = self.config_backtest.get("max_posicoes", 5)  # Máximo 5 posições simultâneas
        
        # Posições abertas (tracking)
        self._posicoes_abertas: Dict[int, Dict[str, Any]] = {}  # id_posicao -> dados da posição
        self._posicoes_fechadas: List[Dict[str, Any]] = []  # Histórico de posições fechadas
        self._proximo_id_posicao = 1
        
        # Capital atual
        self._capital_atual = self.capital_inicial
        self._equity_curve: List[Dict[str, Any]] = []  # Histórico de equity
        
        # Referência ao plugin de padrões (será injetada)
        self.plugin_padroes = None
        
        # Referência ao plugin de banco de dados (será injetada)
        self.plugin_banco_dados = None
    
    def _inicializar_interno(self) -> bool:
        """
        Inicializa recursos específicos do plugin.
        
        Returns:
            bool: True se inicializado com sucesso
        """
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Inicializado. "
                    f"Capital inicial: ${self.capital_inicial:,.2f}, "
                    f"Risco por trade: {self.risco_por_trade*100:.1f}%"
                )
            
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro na inicialização: {e}",
                    exc_info=True
                )
            return False
    
    def definir_plugin_padroes(self, plugin_padroes):
        """
        Define referência ao plugin de padrões.
        
        Args:
            plugin_padroes: Instância do PluginPadroes
        """
        self.plugin_padroes = plugin_padroes
    
    def definir_plugin_banco_dados(self, plugin_banco_dados):
        """
        Define referência ao plugin de banco de dados.
        
        Args:
            plugin_banco_dados: Instância do PluginBancoDados
        """
        self.plugin_banco_dados = plugin_banco_dados
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executa o backtest.
        
        Se dados_entrada contiver 'validar_retroativo': True, executa validação retroativa.
        Caso contrário, apenas retorna status atual.
        
        Args:
            dados_entrada: Dados de entrada (opcional)
                - validar_retroativo (bool): Se True, executa validação retroativa
                - filtros (dict): Filtros opcionais (symbol, timeframe, tipo_padrao, data_inicio, data_fim)
            
        Returns:
            dict: Resultado da execução
        """
        try:
            if self.cancelamento_solicitado():
                return {
                    "status": StatusExecucao.CANCELADO.value,
                    "mensagem": "Cancelamento solicitado"
                }
            
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Executando backtest..."
                )
            
            # Verifica se deve executar validação retroativa
            if dados_entrada and dados_entrada.get("validar_retroativo", False):
                return self.validar_retroativo(
                    filtros=dados_entrada.get("filtros", {})
                )
            
            # Retorna status atual
            return {
                "status": StatusExecucao.OK.value,
                "mensagem": "Backtest em modo passivo",
                "posicoes_abertas": len(self._posicoes_abertas),
                "posicoes_fechadas": len(self._posicoes_fechadas),
                "capital_atual": self._capital_atual,
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
    
    def validar_retroativo(
        self,
        filtros: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Valida padrões retroativamente com dados históricos.
        
        Processo:
        1. Busca padrões detectados do banco de dados
        2. Para cada padrão, busca velas históricas correspondentes
        3. Simula abertura de posição no momento do padrão
        4. Valida se padrão atingiu TP ou SL nas velas seguintes
        5. Calcula métricas finais por padrão
        
        Args:
            filtros: Filtros opcionais para buscar padrões
                - symbol: Filtrar por símbolo
                - timeframe: Filtrar por timeframe
                - tipo_padrao: Filtrar por tipo de padrão
                - data_inicio: Data inicial (datetime ou string)
                - data_fim: Data final (datetime ou string)
                - confidence_min: Confidence mínimo (padrão: 0.5)
                - final_score_min: Final score mínimo (padrão: 0.6)
        
        Returns:
            dict: Resultado da validação com métricas
        """
        try:
            if not self.plugin_banco_dados:
                return {
                    "status": StatusExecucao.ERRO.value,
                    "mensagem": "PluginBancoDados não configurado"
                }
            
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Iniciando validação retroativa..."
                )
            
            # Prepara filtros
            filtros = filtros or {}
            confidence_min = filtros.get("confidence_min", 0.5)
            final_score_min = filtros.get("final_score_min", 0.6)
            
            # 1. Busca padrões detectados do banco
            filtros_consulta = {
                "confidence": {"$gte": confidence_min},
                "final_score": {"$gte": final_score_min},
            }
            
            if filtros.get("symbol"):
                filtros_consulta["symbol"] = filtros["symbol"]
            if filtros.get("timeframe"):
                filtros_consulta["timeframe"] = filtros["timeframe"]
            if filtros.get("tipo_padrao"):
                filtros_consulta["tipo_padrao"] = filtros["tipo_padrao"]
            if filtros.get("data_inicio"):
                filtros_consulta["open_time"] = {"$gte": filtros["data_inicio"]}
            if filtros.get("data_fim"):
                if "open_time" in filtros_consulta:
                    filtros_consulta["open_time"]["$lte"] = filtros["data_fim"]
                else:
                    filtros_consulta["open_time"] = {"$lte": filtros["data_fim"]}
            
            # Prepara filtros para o método consultar
            filtros_banco = {}
            
            if filtros_consulta.get("symbol"):
                filtros_banco["symbol"] = filtros_consulta["symbol"]
            if filtros_consulta.get("timeframe"):
                filtros_banco["timeframe"] = filtros_consulta["timeframe"]
            if filtros_consulta.get("tipo_padrao"):
                filtros_banco["tipo_padrao"] = filtros_consulta["tipo_padrao"]
            if filtros_consulta.get("open_time"):
                if isinstance(filtros_consulta["open_time"], dict):
                    if "$gte" in filtros_consulta["open_time"]:
                        filtros_banco["open_time"] = filtros_consulta["open_time"]["$gte"]
            
            # Busca padrões usando método consultar
            resultado_padroes = self.plugin_banco_dados.consultar(
                tabela="padroes_detectados",
                filtros=filtros_banco,
                ordem="open_time ASC"
            )
            
            # Filtra por confidence e final_score manualmente (já que consultar não suporta >=)
            if resultado_padroes.get("sucesso") and resultado_padroes.get("dados"):
                padroes_brutos = resultado_padroes["dados"]
                padroes = [
                    p for p in padroes_brutos
                    if float(p.get("confidence", 0)) >= confidence_min
                    and float(p.get("final_score", 0)) >= final_score_min
                ]
                
                # Filtra por data_fim se especificado
                if filtros.get("data_fim"):
                    data_fim = filtros["data_fim"]
                    if isinstance(data_fim, str):
                        data_fim = parse_date(data_fim)
                    padroes = [p for p in padroes if p.get("open_time") <= data_fim]
                
                resultado_padroes["dados"] = padroes
            else:
                padroes = []
            
            if not resultado_padroes.get("sucesso"):
                return {
                    "status": StatusExecucao.ERRO.value,
                    "mensagem": "Erro ao buscar padrões do banco",
                    "erro": resultado_padroes.get("erro")
                }
            
            padroes = resultado_padroes.get("dados", [])
            
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] {len(padroes)} padrões encontrados para validação"
                )
            
            if not padroes:
                return {
                    "status": StatusExecucao.OK.value,
                    "mensagem": "Nenhum padrão encontrado para validação",
                    "total_padroes": 0,
                    "metricas": {}
                }
            
            # 2. Para cada padrão, busca velas e simula trade
            padroes_processados = 0
            padroes_com_erro = 0
            
            for padrao in padroes:
                if self.cancelamento_solicitado():
                    break
                
                try:
                    # Busca velas históricas para o padrão
                    velas = self._buscar_velas_historicas(
                        symbol=padrao["symbol"],
                        timeframe=padrao["timeframe"],
                        data_inicio=padrao["open_time"],
                        limite_velas=200  # Busca até 200 velas após o padrão
                    )
                    
                    if not velas or len(velas) < 2:
                        padroes_com_erro += 1
                        continue
                    
                    # Determina preço de entrada (close da vela do padrão)
                    vela_padrao = velas[0] if velas else None
                    if not vela_padrao:
                        padroes_com_erro += 1
                        continue
                    
                    preco_entrada = float(vela_padrao.get("close", 0))
                    preco_sl = float(padrao.get("suggested_sl", 0)) if padrao.get("suggested_sl") else None
                    preco_tp = float(padrao.get("suggested_tp", 0)) if padrao.get("suggested_tp") else None
                    
                    if not preco_entrada or not preco_sl or not preco_tp:
                        padroes_com_erro += 1
                        continue
                    
                    # Simula abertura de posição
                    posicao = self.simular_trade(
                        padrao=padrao,
                        velas=velas,
                        preco_entrada=preco_entrada,
                        preco_sl=preco_sl,
                        preco_tp=preco_tp,
                        direcao=padrao["direcao"]
                    )
                    
                    if not posicao:
                        padroes_com_erro += 1
                        continue
                    
                    # Valida posição contra velas seguintes
                    posicao_fechada = None
                    for i, vela in enumerate(velas[1:], start=1):
                        vela_dict = {
                            "high": float(vela.get("high", 0)),
                            "low": float(vela.get("low", 0)),
                            "close": float(vela.get("close", 0)),
                            "datetime": vela.get("open_time"),
                            "index": i
                        }
                        
                        posicoes_fechadas = self.validar_posicoes_abertas(vela_dict)
                        if posicoes_fechadas:
                            posicao_fechada = posicoes_fechadas[0]
                            break
                    
                    # Se não fechou nas velas seguintes, fecha manualmente na última vela
                    if not posicao_fechada and len(velas) > 1:
                        ultima_vela = velas[-1]
                        preco_final = float(ultima_vela.get("close", preco_entrada))
                        self.fechar_posicao(
                            posicao["id"],
                            preco_final,
                            "MANUAL",
                            {
                                "datetime": ultima_vela.get("open_time"),
                                "index": len(velas) - 1
                            }
                        )
                    
                    padroes_processados += 1
                    
                except Exception as e:
                    padroes_com_erro += 1
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Erro ao processar padrão {padrao.get('id')}: {e}"
                        )
            
            # 3. Calcula métricas finais
            metricas_por_tipo = {}
            todos_tipos = set(p.get("tipo_padrao") for p in padroes if p.get("tipo_padrao"))
            
            for tipo_padrao in todos_tipos:
                metricas = self.calcular_metricas(tipo_padrao=tipo_padrao)
                metricas_por_tipo[tipo_padrao] = metricas
            
            # Métricas gerais
            metricas_gerais = self.calcular_metricas()
            
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Validação retroativa concluída: "
                    f"{padroes_processados} padrões processados, "
                    f"{padroes_com_erro} erros, "
                    f"{len(self._posicoes_fechadas)} trades simulados"
                )
            
            return {
                "status": StatusExecucao.OK.value,
                "mensagem": "Validação retroativa concluída",
                "total_padroes": len(padroes),
                "padroes_processados": padroes_processados,
                "padroes_com_erro": padroes_com_erro,
                "total_trades": len(self._posicoes_fechadas),
                "metricas_gerais": metricas_gerais,
                "metricas_por_tipo": metricas_por_tipo,
                "capital_final": self._capital_atual,
                "retorno_total": ((self._capital_atual - self.capital_inicial) / self.capital_inicial) * 100,
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro na validação retroativa: {e}",
                    exc_info=True
                )
            return {
                "status": StatusExecucao.ERRO.value,
                "mensagem": f"Erro: {e}",
                "erro": str(e)
            }
    
    def _buscar_velas_historicas(
        self,
        symbol: str,
        timeframe: str,
        data_inicio: datetime,
        limite_velas: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Busca velas históricas do banco de dados.
        
        Args:
            symbol: Símbolo do par
            timeframe: Timeframe das velas
            data_inicio: Data inicial (busca velas a partir desta data)
            limite_velas: Número máximo de velas a buscar
        
        Returns:
            list: Lista de velas históricas
        """
        try:
            if not self.plugin_banco_dados:
                return []
            
            # Busca velas do banco usando método consultar
            resultado = self.plugin_banco_dados.consultar(
                tabela="velas",
                filtros={
                    "ativo": symbol,
                    "timeframe": timeframe,
                    "fechada": True
                },
                ordem="open_time ASC",
                limite=limite_velas
            )
            
            # Filtra por data_inicio manualmente
            if resultado.get("sucesso") and resultado.get("dados"):
                velas_brutas = resultado["dados"]
                velas = [
                    v for v in velas_brutas
                    if v.get("open_time") >= data_inicio
                ]
                resultado["dados"] = velas
            
            if resultado.get("sucesso") and resultado.get("dados"):
                return resultado["dados"]
            
            return []
            
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Erro ao buscar velas históricas: {e}"
                )
            return []
    
    def simular_trade(
        self,
        padrao: Dict[str, Any],
        velas: List[Dict[str, Any]],
        preco_entrada: float,
        preco_sl: float,
        preco_tp: float,
        direcao: str,  # "LONG" ou "SHORT"
    ) -> Optional[Dict[str, Any]]:
        """
        Simula a execução de um trade baseado em um padrão detectado.
        
        Args:
            padrao: Dados do padrão detectado
            velas: Lista de velas históricas (para validar execução)
            preco_entrada: Preço de entrada
            preco_sl: Preço de stop loss
            preco_tp: Preço de take profit
            direcao: Direção do trade ("LONG" ou "SHORT")
            
        Returns:
            dict: Dados da posição criada ou None se não foi possível abrir
        """
        try:
            # Verifica se há capital disponível
            if self._capital_atual <= 0:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Sem capital disponível para abrir posição"
                    )
                return None
            
            # Verifica limite de posições simultâneas
            if len(self._posicoes_abertas) >= self.max_posicoes:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Limite de posições simultâneas atingido ({self.max_posicoes})"
                    )
                return None
            
            # Calcula tamanho da posição baseado no risco
            risco_absoluto = self._capital_atual * self.risco_por_trade
            distancia_sl = abs(preco_entrada - preco_sl)
            
            if distancia_sl == 0:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Distância SL zero. Não é possível calcular tamanho da posição"
                    )
                return None
            
            # Tamanho da posição em unidades do ativo
            # Para LONG: se preço cai até SL, perdemos distancia_sl por unidade
            # Para SHORT: se preço sobe até SL, perdemos distancia_sl por unidade
            tamanho_posicao = risco_absoluto / distancia_sl
            
            # Aplica slippage no preço de entrada
            if direcao == "LONG":
                preco_entrada_real = preco_entrada * (1 + self.slippage_pct)
            else:  # SHORT
                preco_entrada_real = preco_entrada * (1 - self.slippage_pct)
            
            # Calcula custo total (incluindo fees)
            valor_posicao = tamanho_posicao * preco_entrada_real
            fee_entrada = valor_posicao * self.fee_pct
            
            # Verifica se há capital suficiente
            if valor_posicao + fee_entrada > self._capital_atual:
                # Ajusta tamanho da posição para usar todo o capital disponível
                capital_disponivel = self._capital_atual * 0.95  # Deixa 5% de margem
                valor_posicao = capital_disponivel / (1 + self.fee_pct)
                tamanho_posicao = valor_posicao / preco_entrada_real
                fee_entrada = valor_posicao * self.fee_pct
            
            # Cria posição
            id_posicao = self._proximo_id_posicao
            self._proximo_id_posicao += 1
            
            posicao = {
                "id": id_posicao,
                "padrao_id": padrao.get("id"),
                "tipo_padrao": padrao.get("tipo_padrao"),
                "symbol": padrao.get("symbol"),
                "timeframe": padrao.get("timeframe"),
                "direcao": direcao,
                "preco_entrada": preco_entrada_real,
                "preco_sl": preco_sl,
                "preco_tp": preco_tp,
                "tamanho": tamanho_posicao,
                "valor_entrada": valor_posicao,
                "fee_entrada": fee_entrada,
                "status": StatusPosicao.ABERTA.value,
                "aberta_em": padrao.get("open_time"),
                "vela_entrada": len(velas) - 1 if velas else 0,
            }
            
            # Deduz capital
            self._capital_atual -= (valor_posicao + fee_entrada)
            
            # Armazena posição
            self._posicoes_abertas[id_posicao] = posicao
            
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Posição {id_posicao} aberta: "
                    f"{direcao} {padrao.get('symbol')} @ {preco_entrada_real:.2f}, "
                    f"tamanho: {tamanho_posicao:.6f}, valor: ${valor_posicao:.2f}"
                )
            
            return posicao
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao simular trade: {e}",
                    exc_info=True
                )
            return None
    
    def fechar_posicao(
        self,
        id_posicao: int,
        preco_saida: float,
        motivo: str,  # "TP", "SL", "MANUAL"
        vela_atual: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fecha uma posição aberta.
        
        Args:
            id_posicao: ID da posição a fechar
            preco_saida: Preço de saída
            motivo: Motivo do fechamento ("TP", "SL", "MANUAL")
            vela_atual: Vela atual (opcional, para timestamp)
            
        Returns:
            dict: Dados da posição fechada ou None se não encontrada
        """
        try:
            if id_posicao not in self._posicoes_abertas:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Posição {id_posicao} não encontrada"
                    )
                return None
            
            posicao = self._posicoes_abertas.pop(id_posicao)
            
            # Aplica slippage no preço de saída
            if posicao["direcao"] == "LONG":
                preco_saida_real = preco_saida * (1 - self.slippage_pct)
            else:  # SHORT
                preco_saida_real = preco_saida * (1 + self.slippage_pct)
            
            # Calcula valor de saída
            valor_saida = posicao["tamanho"] * preco_saida_real
            fee_saida = valor_saida * self.fee_pct
            
            # Calcula P&L
            if posicao["direcao"] == "LONG":
                pnl_bruto = valor_saida - posicao["valor_entrada"]
            else:  # SHORT
                pnl_bruto = posicao["valor_entrada"] - valor_saida
            
            pnl_liquido = pnl_bruto - posicao["fee_entrada"] - fee_saida
            pnl_pct = (pnl_liquido / posicao["valor_entrada"]) * 100
            
            # Atualiza capital
            self._capital_atual += (valor_saida - fee_saida)
            
            # Completa dados da posição
            posicao["status"] = StatusPosicao.FECHADA.value
            posicao["preco_saida"] = preco_saida_real
            posicao["valor_saida"] = valor_saida
            posicao["fee_saida"] = fee_saida
            posicao["pnl_bruto"] = pnl_bruto
            posicao["pnl_liquido"] = pnl_liquido
            posicao["pnl_pct"] = pnl_pct
            posicao["motivo_fechamento"] = motivo
            posicao["fechada_em"] = vela_atual.get("datetime") if vela_atual else datetime.now()
            posicao["vela_saida"] = vela_atual.get("index") if vela_atual else None
            
            # Armazena no histórico
            self._posicoes_fechadas.append(posicao)
            
            # Atualiza equity curve
            self._equity_curve.append({
                "timestamp": posicao["fechada_em"],
                "capital": self._capital_atual,
                "pnl_liquido": pnl_liquido,
            })
            
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Posição {id_posicao} fechada: "
                    f"{motivo} @ {preco_saida_real:.2f}, "
                    f"P&L: ${pnl_liquido:.2f} ({pnl_pct:+.2f}%)"
                )
            
            return posicao
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao fechar posição: {e}",
                    exc_info=True
                )
            return None
    
    def validar_posicoes_abertas(self, vela_atual: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Valida posições abertas contra a vela atual.
        
        Verifica se alguma posição atingiu TP ou SL.
        
        Args:
            vela_atual: Vela atual com dados OHLCV
            
        Returns:
            list: Lista de posições fechadas nesta validação
        """
        posicoes_fechadas = []
        
        try:
            high = vela_atual.get("high")
            low = vela_atual.get("low")
            close = vela_atual.get("close")
            
            if not all([high, low, close]):
                return posicoes_fechadas
            
            # Cria cópia da lista de IDs para evitar modificação durante iteração
            ids_posicoes = list(self._posicoes_abertas.keys())
            
            for id_posicao in ids_posicoes:
                if id_posicao not in self._posicoes_abertas:
                    continue
                
                posicao = self._posicoes_abertas[id_posicao]
                preco_sl = posicao["preco_sl"]
                preco_tp = posicao["preco_tp"]
                
                # Verifica se atingiu TP ou SL
                if posicao["direcao"] == "LONG":
                    # LONG: TP acima, SL abaixo
                    if high >= preco_tp:
                        # Atingiu TP
                        pos_fechada = self.fechar_posicao(id_posicao, preco_tp, "TP", vela_atual)
                        if pos_fechada:
                            posicoes_fechadas.append(pos_fechada)
                    elif low <= preco_sl:
                        # Atingiu SL
                        pos_fechada = self.fechar_posicao(id_posicao, preco_sl, "SL", vela_atual)
                        if pos_fechada:
                            posicoes_fechadas.append(pos_fechada)
                else:  # SHORT
                    # SHORT: TP abaixo, SL acima
                    if low <= preco_tp:
                        # Atingiu TP
                        pos_fechada = self.fechar_posicao(id_posicao, preco_tp, "TP", vela_atual)
                        if pos_fechada:
                            posicoes_fechadas.append(pos_fechada)
                    elif high >= preco_sl:
                        # Atingiu SL
                        pos_fechada = self.fechar_posicao(id_posicao, preco_sl, "SL", vela_atual)
                        if pos_fechada:
                            posicoes_fechadas.append(pos_fechada)
            
            return posicoes_fechadas
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao validar posições: {e}",
                    exc_info=True
                )
            return posicoes_fechadas
    
    def calcular_metricas(self, tipo_padrao: Optional[str] = None) -> Dict[str, Any]:
        """
        Calcula métricas reais baseadas em execuções simuladas.
        
        Métricas calculadas:
        - precision: TP / (TP + FP)
        - recall: TP / (TP + FN)
        - expectancy: E[P&L] por trade
        - winrate: % de trades vencedores
        - avg_rr: Média de Risk:Reward
        - sharpe_condicional: Sharpe ratio condicional
        - drawdown_condicional: Drawdown máximo
        - total_trades: Total de trades executados
        - trades_win: Total de wins
        - trades_loss: Total de losses
        
        Args:
            tipo_padrao: Filtrar por tipo de padrão (opcional)
            
        Returns:
            dict: Métricas calculadas
        """
        try:
            # Filtra posições fechadas
            posicoes = self._posicoes_fechadas
            if tipo_padrao:
                posicoes = [p for p in posicoes if p.get("tipo_padrao") == tipo_padrao]
            
            if not posicoes:
                return {
                    "tipo_padrao": tipo_padrao or "all",
                    "total_trades": 0,
                    "precision": None,
                    "recall": None,
                    "expectancy": None,
                    "winrate": None,
                    "avg_rr": None,
                    "sharpe_condicional": None,
                    "drawdown_condicional": None,
                    "trades_win": 0,
                    "trades_loss": 0,
                }
            
            # Separa wins e losses
            wins = [p for p in posicoes if p.get("pnl_liquido", 0) > 0]
            losses = [p for p in posicoes if p.get("pnl_liquido", 0) <= 0]
            
            total_trades = len(posicoes)
            trades_win = len(wins)
            trades_loss = len(losses)
            
            # Winrate
            winrate = trades_win / total_trades if total_trades > 0 else 0.0
            
            # Expectancy (média de P&L por trade)
            pnl_list = [p.get("pnl_liquido", 0) for p in posicoes]
            expectancy = np.mean(pnl_list) if pnl_list else 0.0
            
            # Precision e Recall
            # TP: trades que atingiram TP
            # FP: trades que atingiram SL (falsos positivos)
            # FN: padrões detectados mas não executados (não temos isso ainda)
            tp = len([p for p in wins if p.get("motivo_fechamento") == "TP"])
            fp = len([p for p in losses if p.get("motivo_fechamento") == "SL"])
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = None  # Requer dados de padrões não executados
            
            # Risk:Reward médio
            rrs = []
            for pos in posicoes:
                if pos.get("motivo_fechamento") == "TP":
                    # R:R = (TP - entrada) / (entrada - SL)
                    entrada = pos.get("preco_entrada", 0)
                    sl = pos.get("preco_sl", 0)
                    tp_price = pos.get("preco_tp", 0)
                    
                    if entrada > 0 and sl > 0 and tp_price > 0:
                        if pos.get("direcao") == "LONG":
                            rr = (tp_price - entrada) / (entrada - sl)
                        else:  # SHORT
                            rr = (entrada - tp_price) / (sl - entrada)
                        rrs.append(rr)
            
            avg_rr = np.mean(rrs) if rrs else None
            
            # Sharpe condicional (usando retornos)
            if len(pnl_list) > 1:
                retornos = [pnl / self.capital_inicial for pnl in pnl_list]
                sharpe_condicional = np.mean(retornos) / np.std(retornos) if np.std(retornos) > 0 else 0.0
            else:
                sharpe_condicional = None
            
            # Drawdown condicional
            if self._equity_curve:
                equity_values = [e["capital"] for e in self._equity_curve]
                peak = equity_values[0]
                max_drawdown = 0.0
                
                for equity in equity_values:
                    if equity > peak:
                        peak = equity
                    drawdown = (peak - equity) / peak if peak > 0 else 0.0
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown
                
                drawdown_condicional = max_drawdown
            else:
                drawdown_condicional = None
            
            return {
                "tipo_padrao": tipo_padrao or "all",
                "total_trades": total_trades,
                "precision": float(precision) if precision else None,
                "recall": recall,
                "expectancy": float(expectancy),
                "winrate": float(winrate),
                "avg_rr": float(avg_rr) if avg_rr else None,
                "sharpe_condicional": float(sharpe_condicional) if sharpe_condicional else None,
                "drawdown_condicional": float(drawdown_condicional) if drawdown_condicional else None,
                "trades_win": trades_win,
                "trades_loss": trades_loss,
                "capital_final": self._capital_atual,
                "retorno_total": ((self._capital_atual - self.capital_inicial) / self.capital_inicial) * 100,
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao calcular métricas: {e}",
                    exc_info=True
                )
            return {
                "tipo_padrao": tipo_padrao or "all",
                "erro": str(e)
            }
    
    def _finalizar_interno(self) -> bool:
        """
        Finalização específica do plugin.
        
        Returns:
            bool: True se finalizado com sucesso
        """
        try:
            # Fecha todas as posições abertas (se houver)
            if self._posicoes_abertas:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Fechando {len(self._posicoes_abertas)} "
                        f"posições abertas na finalização"
                    )
                
                # Fecha todas com preço atual (simulado)
                for id_posicao in list(self._posicoes_abertas.keys()):
                    posicao = self._posicoes_abertas[id_posicao]
                    preco_atual = posicao.get("preco_entrada", 0)  # Usa preço de entrada como fallback
                    self.fechar_posicao(id_posicao, preco_atual, "MANUAL")
            
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro na finalização: {e}",
                    exc_info=True
                )
            return False

