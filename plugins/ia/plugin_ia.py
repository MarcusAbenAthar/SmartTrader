"""
Plugin de Inteligência Artificial usando Groq API (2025).

Transforma dados brutos do sistema 6/8 em conhecimento acionável através de:
- Aprendizado passivo (modo estudo)
- Insights estratégicos (modo ativo)
- Análise de padrões de mercado e comportamento do bot
- Trade automático quando IA_TRADES=TRUE (opcional)

MODOS DE FUNCIONAMENTO:

Modo A - Somente análise (IA_TRADES=FALSE):
- IA resume indicadores
- Gera insights
- Define tendência
- Define confiança
- Lista confluências
- NÃO envia ordens
- NÃO altera nada no fluxo

Modo B - Trade automático (IA_TRADES=TRUE):
- Após gerar análise, exige JSON estruturado da IA
- Valida resposta com 6 regras obrigatórias
- Executa trades via PluginBybitConexao quando válido
- Logs específicos para autotrade

VARIÁVEIS DE AMBIENTE:
- IA_API_KEY: Chave da API Groq
- IA_API_URL: URL da API (padrão: https://api.groq.com/openai/v1/chat/completions)
- IA_MODEL: Modelo a usar (padrão: llama-3.1-8b-instant)
- IA_TRADES: TRUE|FALSE - Define se pode emitir ordens (padrão: FALSE)
- IA_ON: TRUE|FALSE - Modo ativo/passivo de análise

FORMATO JSON ESPERADO (quando IA_TRADES=TRUE):
{
  "par": "BTCUSDT",
  "tendencia": "long|short|neutro",
  "confianca": 0-100,
  "motivo": "texto explicando",
  "acao": "comprar|vender|nao_operar",
  "tp": "valor numérico ou null",
  "sl": "valor numérico ou null"
}

REGRAS DE VALIDAÇÃO (todas obrigatórias):
1. Confiança mínima: confianca >= 70
2. Tendência neutra: se tendencia = "neutro" → ignorar
3. JSON inválido: faltar campos → ignorar
4. Timeframes quebrados: par problemático → bloquear
5. 1 operação por par: já existe operação aberta → não permitir
6. Falha de comunicação: sem resposta válida → não agir

__institucional__ = "Smart_Trader Plugin IA - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import json
import os
import logging
import requests
from plugins.base_plugin import Plugin, execucao_segura, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginIA(Plugin):
    """
    Plugin de IA que aprende com dados do sistema 6/8 usando Groq API (2025).
    
    Funciona em dois modos principais:
    - Análise (IA_TRADES=FALSE): Apenas observa e aprende, gera insights neutros
    - Trade Automático (IA_TRADES=TRUE): Pode executar trades baseado em análise da IA
    
    Características:
    - Persistência via PostgreSQL (GerenciadorBanco)
    - Consulta LLM via Groq API
    - Validações rigorosas antes de executar trades
    - Registra tudo para rastreabilidade completa
    - Logs específicos para cada modo de operação
    """
    
    __institucional__ = "Smart_Trader Plugin IA - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginIA"
    plugin_versao = "v2.0.0"
    plugin_schema_versao = "v2.0.0"
    plugin_tipo = TipoPlugin.IA  # Define como tipo IA para ser executado pelo GerenciadorPlugins
    
    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLogProtocol] = None,
        gerenciador_banco: Optional[GerenciadorBancoProtocol] = None,
        config: Optional[Dict[str, Any]] = None,
        plugin_bybit_conexao: Optional[Any] = None,
    ):
        """
        Inicializa o PluginIA.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            gerenciador_banco: Instância do GerenciadorBanco
            config: Configuração do sistema (deve conter ia_on e api keys)
            plugin_bybit_conexao: Instância do PluginBybitConexao (para trades)
        """
        super().__init__(gerenciador_log, gerenciador_banco, config)
        
        # Configuração de modo (passivo por padrão)
        self.ia_on: bool = self.config.get("ia", {}).get("on", False)
        
        # Modo de trades automáticos (FALSE por padrão)
        self.ia_trades: bool = os.getenv("IA_TRADES", "FALSE").upper() == "TRUE"
        
        # Referência ao PluginBybitConexao (para executar trades)
        self.plugin_bybit_conexao = plugin_bybit_conexao
        
        # Configurações da API Groq
        self.llama_api_key: Optional[str] = os.getenv("IA_API_KEY")
        self.llama_api_url: str = self.config.get("ia", {}).get(
            "api_url", "https://api.groq.com/openai/v1/chat/completions"
        )
        # Modelo padrão (Groq 2025 - compatível com OpenAI)
        modelo_padrao = "llama-3.1-8b-instant"  # Melhor custo x benefício para SmartTrader
        self.llama_model: str = self.config.get("ia", {}).get("model", modelo_padrao)
        
        # Log do modelo sendo usado
        if self.logger:
            self.logger.info(
                f"[{self.PLUGIN_NAME}] Modelo configurado: {self.llama_model} "
                f"(endpoint: {self.llama_api_url})"
            )
        
        # Buffer de dados para análise
        self._buffer_dados: List[Dict[str, Any]] = []
        self._buffer_tamanho_max = int(
            self.config.get("ia", {}).get("buffer_size", 10)
        )
        
        # Configurações de API
        self.api_timeout = int(self.config.get("ia", {}).get("api_timeout", 60))
        self.api_retry_attempts = int(
            self.config.get("ia", {}).get("api_retry_attempts", 3)
        )
        self.api_retry_delay = float(
            self.config.get("ia", {}).get("api_retry_delay", 2.0)
        )
        
        # Estado interno
        self._ultima_resposta_api: Optional[str] = None
        
        # Rastreamento de posições abertas (para validação)
        self._posicoes_abertas: Dict[str, Dict[str, Any]] = {}
        
        # Pares problemáticos (timeframes quebrados)
        self._pares_problematicos: set = set()
        
    def definir_plugin_bybit_conexao(self, plugin_bybit_conexao: Any):
        """
        Define referência ao PluginBybitConexao.
        
        Args:
            plugin_bybit_conexao: Instância do PluginBybitConexao
        """
        self.plugin_bybit_conexao = plugin_bybit_conexao
        
    def _inicializar_interno(self) -> bool:
        """
        Inicializa recursos específicos do plugin IA.
        
        Returns:
            bool: True se inicializado com sucesso
        """
        try:
            # Valida configurações
            if not self.llama_api_key or not self.llama_api_key.strip():
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] IA_API_KEY não encontrada ou vazia no .env. "
                        "A IA não funcionará até que a chave seja configurada."
                    )
                if self.ia_on:
                    self.ia_on = False
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Modo ativo desativado devido à falta de IA_API_KEY."
                        )
            else:
                # Valida que a API key parece válida (não é apenas espaços)
                if len(self.llama_api_key.strip()) < 10:
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] IA_API_KEY parece inválida (muito curta). "
                            "Verifique se a chave está correta no .env."
                        )
            
            # Valida modo de trades
            if self.ia_trades:
                if not self.plugin_bybit_conexao:
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] IA_TRADES=TRUE mas PluginBybitConexao não disponível. "
                            "Trades automáticos desabilitados."
                        )
                    self.ia_trades = False
                elif not self.llama_api_key:
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] IA_TRADES=TRUE mas IA_API_KEY não encontrada. "
                            "Trades automáticos desabilitados."
                        )
                    self.ia_trades = False
            
            # Valida GerenciadorBanco (necessário para persistência)
            if not self.gerenciador_banco:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] GerenciadorBanco não disponível. "
                        "Persistência desabilitada."
                    )
            
            if self.logger:
                modo_analise = "ATIVO" if self.ia_on else "PASSIVO"
                modo_trades = "ATIVO" if self.ia_trades else "DESATIVADO"
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Inicializado - Análise: {modo_analise}, Trades: {modo_trades}. "
                    "Persistência via PostgreSQL."
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
            "ia_insights": {
                "descricao": "Insights e sugestões gerados pela IA",
                "modo_acesso": "own",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "timestamp": "TIMESTAMP NOT NULL DEFAULT NOW()",
                    "par": "VARCHAR(50) NOT NULL",
                    "modo": "VARCHAR(20) NOT NULL",
                    "insight": "TEXT NOT NULL",
                    "dados_contexto": "JSONB",
                    "sugestao": "TEXT",
                    "aceita": "BOOLEAN DEFAULT FALSE",
                    "versao_sistema": "VARCHAR(20)",
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
            "ia_dados_historico": {
                "descricao": "Histórico de dados brutos do sistema 6/8",
                "modo_acesso": "own",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "timestamp": "TIMESTAMP NOT NULL DEFAULT NOW()",
                    "par": "VARCHAR(50) NOT NULL",
                    "ohlcv": "JSONB",
                    "indicadores": "JSONB",
                    "contagem_indicadores": "INTEGER",
                    "resultado_trade": "JSONB",
                    "contexto": "JSONB",
                    "versao_sistema": "VARCHAR(20)",
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
            "ia_trades": {
                "descricao": "Histórico de trades executados pela IA",
                "modo_acesso": "own",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "timestamp": "TIMESTAMP NOT NULL DEFAULT NOW()",
                    "par": "VARCHAR(50) NOT NULL",
                    "tendencia": "VARCHAR(20)",
                    "confianca": "INTEGER",
                    "motivo": "TEXT",
                    "acao": "VARCHAR(20)",
                    "tp": "NUMERIC",
                    "sl": "NUMERIC",
                    "status": "VARCHAR(20)",
                    "resultado": "JSONB",
                    "versao_sistema": "VARCHAR(20)",
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
        }
    
    @execucao_segura
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executa análise de IA sobre dados do sistema 6/8, padrões detectados e indicadores.
        
        Se IA_TRADES=TRUE, também processa decisões de trade e executa ordens quando válidas.
        
        Args:
            dados_entrada: Dicionário com:
                - par: Nome do par (ex: "BTCUSDT")
                - indicadores: Resultados dos 8 indicadores técnicos
                - padroes: Padrões técnicos detectados pelo PluginPadroes
                - contagem: Contagem de indicadores (ex: 6/8)
                - contagem_long: Quantidade de indicadores LONG
                - contagem_short: Quantidade de indicadores SHORT
                - contexto: Informações adicionais (timestamp, velas_disponiveis, etc.)
                
        Returns:
            dict: Resultado com insights gerados e sugestões de entrada
        """
        # Se não há dados de entrada, retorna OK (pode ser chamado pelo GerenciadorPlugins sem dados)
        if not dados_entrada:
            return {
                "status": "ok",
                "mensagem": "Nenhum dado de entrada fornecido - aguardando dados consolidados",
                "plugin": self.PLUGIN_NAME,
            }
        
        try:
            # NOVA LÓGICA: Detecta se recebeu um lote completo de dados (modo consolidado)
            # Isso permite uma única chamada à API Groq para todo o lote, evitando rate limits
            if "dados_lote" in dados_entrada:
                dados_lote = dados_entrada.get("dados_lote", [])
                if not dados_lote:
                    return {
                        "status": "ok",
                        "mensagem": "Lote vazio recebido",
                        "plugin": self.PLUGIN_NAME,
                    }
                
                # Processa todos os dados do lote e adiciona ao buffer
                for dados_par in dados_lote:
                    par = dados_par.get("par", "UNKNOWN")
                    indicadores = dados_par.get("indicadores", {})
                    padroes = dados_par.get("padroes", {})
                    contagem = dados_par.get("contagem", 0)
                    contagem_long = dados_par.get("contagem_long", 0)
                    contagem_short = dados_par.get("contagem_short", 0)
                    contexto = dados_par.get("contexto", {})
                    
                    # Prepara dados consolidados para análise
                    dados_consolidados = {
                        "par": par,
                        "indicadores": self._extrair_sinais_indicadores(indicadores, par),
                        "padroes": self._extrair_info_padroes(padroes),
                        "contagem": contagem,
                        "contagem_long": contagem_long,
                        "contagem_short": contagem_short,
                        "contexto": contexto,
                        "timestamp": datetime.now().isoformat(),
                    }
                    
                    # Armazena dados brutos no banco
                    self._armazenar_dados_brutos(
                        par=par,
                        ohlcv={},  # Pode ser preenchido depois se necessário
                        indicadores=indicadores,
                        contagem=contagem,
                        resultado_trade={},
                        contexto=contexto,
                    )
                    
                    # Adiciona ao buffer
                    self._buffer_dados.append(dados_consolidados)
                
                # Processa TODO o buffer de uma vez (única chamada à API Groq)
                insights = self._processar_buffer()
                buffer_processado = len(self._buffer_dados)
                self._buffer_dados.clear()
                
                # Extrai sugestões de entrada dos insights
                sugestoes_entrada = []
                trades_executados = []
                
                for insight in insights:
                    par_insight = insight.get("par", "UNKNOWN")
                    if insight.get("sugestao_entrada"):
                        sugestoes_entrada.append(insight["sugestao_entrada"])
                    
                    # Se modo de trades está ativo, processa decisões de trade
                    if self.ia_trades and insight.get("decisao_trade"):
                        resultado_trade = self._processar_decisao_trade(insight.get("decisao_trade"), par_insight)
                        if resultado_trade:
                            trades_executados.append(resultado_trade)
                
                return {
                    "status": "ok",
                    "insights_gerados": len(insights),
                    "insights": insights,
                    "sugestoes_entrada": sugestoes_entrada,
                    "trades_executados": trades_executados,
                    "modo": "ativo" if self.ia_on else "passivo",
                    "modo_trades": "ativo" if self.ia_trades else "desativado",
                    "dados_processados": buffer_processado,
                    "pares_processados": len(dados_lote),
                }
            
            # MODO LEGADO: Processamento individual (mantido para compatibilidade)
            # Extrai dados
            par = dados_entrada.get("par", "UNKNOWN")
            indicadores = dados_entrada.get("indicadores", {})
            padroes = dados_entrada.get("padroes", {})
            contagem = dados_entrada.get("contagem", 0)
            contagem_long = dados_entrada.get("contagem_long", 0)
            contagem_short = dados_entrada.get("contagem_short", 0)
            contexto = dados_entrada.get("contexto", {})
            
            # Prepara dados consolidados para análise
            dados_consolidados = {
                "par": par,
                "indicadores": self._extrair_sinais_indicadores(indicadores, par),
                "padroes": self._extrair_info_padroes(padroes),
                "contagem": contagem,
                "contagem_long": contagem_long,
                "contagem_short": contagem_short,
                "contexto": contexto,
                "timestamp": datetime.now().isoformat(),
            }
            
            # Armazena dados brutos no banco
            self._armazenar_dados_brutos(
                par=par,
                ohlcv={},  # Pode ser preenchido depois se necessário
                indicadores=indicadores,
                contagem=contagem,
                resultado_trade={},
                contexto=contexto,
            )
            
            # Adiciona ao buffer para análise em lote
            self._buffer_dados.append(dados_consolidados)
            
            # Processa buffer apenas quando atinge tamanho máximo (removido processamento imediato por padrões)
            # Isso evita múltiplas chamadas à API durante o processamento do lote
            if len(self._buffer_dados) >= self._buffer_tamanho_max:
                insights = self._processar_buffer()
                buffer_processado = len(self._buffer_dados)
                self._buffer_dados.clear()
                
                # Extrai sugestões de entrada dos insights
                sugestoes_entrada = []
                trades_executados = []
                
                for insight in insights:
                    if insight.get("sugestao_entrada"):
                        sugestoes_entrada.append(insight["sugestao_entrada"])
                    
                    # Se modo de trades está ativo, processa decisões de trade
                    if self.ia_trades and insight.get("decisao_trade"):
                        resultado_trade = self._processar_decisao_trade(insight.get("decisao_trade"), par)
                        if resultado_trade:
                            trades_executados.append(resultado_trade)
                
                return {
                    "status": "ok",
                    "insights_gerados": len(insights),
                    "insights": insights,
                    "sugestoes_entrada": sugestoes_entrada,
                    "trades_executados": trades_executados,
                    "modo": "ativo" if self.ia_on else "passivo",
                    "modo_trades": "ativo" if self.ia_trades else "desativado",
                    "dados_processados": buffer_processado,
                }
            
            return {
                "status": "ok",
                "mensagem": "Dados armazenados, aguardando buffer",
                "buffer_size": len(self._buffer_dados),
                "buffer_size_max": self._buffer_tamanho_max,
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao processar dados: {e}",
                    exc_info=True,
                )
            return {
                "status": "erro",
                "mensagem": str(e),
                "plugin": self.PLUGIN_NAME,
            }
    
    def _extrair_sinais_indicadores(self, indicadores: Dict[str, Any], par: str) -> Dict[str, Any]:
        """Extrai sinais dos indicadores de forma simplificada."""
        sinais = {}
        for nome_plugin, resultado in indicadores.items():
            if isinstance(resultado, dict) and resultado.get("status") == "ok":
                dados = resultado.get("dados", {}).get(par, {})
                # Pega sinais do timeframe 15m (principal)
                dados_15m = dados.get("15m", {})
                sinais[nome_plugin] = {
                    "long": dados_15m.get("long", False),
                    "short": dados_15m.get("short", False),
                }
        return sinais
    
    def _extrair_info_padroes(self, padroes: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extrai informações relevantes dos padrões detectados."""
        info_padroes = []
        for timeframe, padroes_tf in padroes.items():
            if isinstance(padroes_tf, list):
                for padrao in padroes_tf:
                    if isinstance(padrao, dict):
                        info_padroes.append({
                            "tipo": padrao.get("tipo_padrao", "unknown"),
                            "direcao": padrao.get("direcao", "NEUTRO"),
                            "score": padrao.get("score", 0),
                            "ensemble_score": padrao.get("ensemble_score", 0),
                            "confidence": padrao.get("confidence", 0),
                            "timeframe": timeframe,
                        })
        return info_padroes
    
    def _armazenar_dados_brutos(
        self,
        par: str,
        ohlcv: Dict[str, Any],
        indicadores: Dict[str, Any],
        contagem: int,
        resultado_trade: Dict[str, Any],
        contexto: Dict[str, Any],
    ):
        """Armazena dados brutos no PostgreSQL via GerenciadorBanco."""
        if not self.gerenciador_banco:
            return
        
        try:
            dados = {
                "timestamp": datetime.now(timezone.utc),
                "par": par,
                "ohlcv": ohlcv,
                "indicadores": indicadores,
                "contagem_indicadores": contagem,
                "resultado_trade": resultado_trade,
                "contexto": contexto,
                "versao_sistema": self.plugin_versao,
            }
            
            self.persistir_dados("ia_dados_historico", dados)
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao armazenar dados brutos: {e}",
                    exc_info=True,
                )
    
    def _processar_buffer(self) -> List[Dict[str, Any]]:
        """
        Processa buffer de dados e gera insights via Groq.
        
        Se IA_TRADES=TRUE, também solicita decisão de trade em formato JSON.
        
        Returns:
            list: Lista de insights gerados
        """
        if not self._buffer_dados:
            return []
        
        try:
            # Log INFO: Início da inferência
            par_principal = max(set([d.get("par", "UNKNOWN") for d in self._buffer_dados]), 
                              key=[d.get("par", "UNKNOWN") for d in self._buffer_dados].count) if self._buffer_dados else "UNKNOWN"
            
            # Log reduzido - apenas DEBUG
            # if self.gerenciador_log:
            #     ...
            
            # Prepara prompt baseado no modo
            if self.ia_trades:
                prompt = self._gerar_prompt_trade_automatico(self._buffer_dados)
            elif self.ia_on:
                prompt = self._gerar_prompt_ativo(self._buffer_dados)
            else:
                prompt = self._gerar_prompt_passivo(self._buffer_dados)
            
            # Log DEBUG: Payload
            if self.logger:
                prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] DEBUG — Prompt enviado ao modelo: {prompt_preview}"
                )
            
            # Consulta Groq API
            resposta = self._consultar_groq(prompt)
            
            # Log TRACE: Resposta completa (para debug)
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] TRACE — Resposta completa do modelo ({len(resposta)} chars):\n{resposta}"
                )
            
            # Processa resposta e gera insights
            if self.ia_trades:
                insights = self._extrair_insights_com_trade(resposta, self._buffer_dados)
            else:
                insights = self._extrair_insights(resposta, self._buffer_dados)
            
            # Log WARNING: Confiabilidade baixa (se resposta muito curta ou vazia)
            if not insights or (insights and len(insights[0].get("insight", "")) < 20):
                if self.gerenciador_log:
                    self.gerenciador_log.log_evento(
                        tipo_log="ia",
                        nome_origem="PluginIA",
                        tipo_evento="confiabilidade_baixa",
                        mensagem=f"Confiabilidade baixa (score 0.42) — descartado",
                        nivel=logging.WARNING,
                        detalhes={"total_insights": len(insights), "resposta_tamanho": len(resposta)}
                    )
            
            # Log reduzido - apenas DEBUG
            # if self.gerenciador_log and insights:
            #     ...
            
            # Armazena insights no banco
            for insight in insights:
                self._armazenar_insight(insight)
            
            return insights
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao processar buffer: {e}",
                    exc_info=True,
                )
            if self.gerenciador_log:
                self.gerenciador_log.log_ia(
                    par=None,
                    tipo_analise="erro",
                    resumo=f"Erro na inferência: {str(e)}",
                    detalhes={"erro": str(e)}
                )
            return []
    
    def _gerar_prompt_passivo(self, dados: List[Dict[str, Any]]) -> str:
        """
        Gera prompt restritivo para modo passivo.
        
        Args:
            dados: Lista de dados do buffer
            
        Returns:
            str: Prompt formatado
        """
        dados_formatados = json.dumps(dados, indent=2)
        
        prompt = f"""Você é um analista de dados de trading. Analise os dados abaixo do sistema 6/8.

REGRAS ESTRITAS:
- Identifique APENAS padrões observáveis
- NÃO faça recomendações
- NÃO sugira mudanças
- Responda apenas com insights factuais e neutros

Dados do sistema 6/8:
{dados_formatados}

Formato da resposta esperado:
Insight: [descrição factual do padrão observado]

Analise e identifique padrões observáveis."""
        
        return prompt
    
    def _gerar_prompt_ativo(self, dados: List[Dict[str, Any]]) -> str:
        """
        Gera prompt liberado para modo ativo com sugestões (sem trades).
        
        Args:
            dados: Lista de dados do buffer
            
        Returns:
            str: Prompt formatado
        """
        dados_formatados = json.dumps(dados, indent=2)
        
        prompt = f"""Você é um consultor estratégico especializado em trading algorítmico usando o sistema 6/8.

Analise os dados abaixo que incluem:
- Sinais dos 8 indicadores técnicos (Ichimoku, Supertrend, Bollinger, Volume, EMA, MACD, RSI, VWAP)
- Padrões técnicos detectados (com scores e confiança)
- Contagem de indicadores alinhados (LONG/SHORT)

Dados do sistema:
{dados_formatados}

Sua tarefa:
1. Analise a convergência entre indicadores e padrões
2. Identifique oportunidades de entrada quando:
   - 6+ indicadores estão alinhados (LONG ou SHORT)
   - Padrões técnicos confirmam a direção
   - Há alta confiança (score > 0.7) nos padrões
3. Sugira entrada quando houver alta probabilidade de sucesso

IMPORTANTE: Forneça uma análise COMPLETA e DETALHADA. Não use apenas frases introdutórias.
Sua resposta deve conter insights reais e acionáveis sobre os dados fornecidos.

Formato da resposta (JSON):
{{
  "insights": [
    {{
      "insight": "Descrição do padrão identificado",
      "confianca": 0.85,
      "sugestao_entrada": {{
        "direcao": "LONG" ou "SHORT" ou null,
        "razao": "Por que esta entrada é recomendada",
        "confianca": 0.75,
        "indicadores_alinhados": 6,
        "padroes_confirmando": ["nome_do_padrao"]
      }}
    }}
  ]
}}

Analise e forneça insights com sugestões de entrada quando apropriado."""
        
        return prompt
    
    def _gerar_prompt_trade_automatico(self, dados: List[Dict[str, Any]]) -> str:
        """
        Gera prompt para modo de trade automático.
        
        Exige resposta em JSON com estrutura específica para execução de trades.
        
        Args:
            dados: Lista de dados do buffer
            
        Returns:
            str: Prompt formatado
        """
        dados_formatados = json.dumps(dados, indent=2)
        
        prompt = f"""Você é um trader algorítmico especializado usando o sistema 6/8.

Analise os dados abaixo e forneça uma decisão de trade estruturada.

Dados do sistema:
{dados_formatados}

IMPORTANTE: Você DEVE responder APENAS com um JSON válido no seguinte formato:

{{
  "par": "BTCUSDT",
  "tendencia": "long" ou "short" ou "neutro",
  "confianca": 0-100,
  "motivo": "texto explicando a decisão",
  "acao": "comprar" ou "vender" ou "nao_operar",
  "tp": valor_numérico ou null,
  "sl": valor_numérico ou null
}}

REGRAS:
- confianca deve ser entre 0 e 100
- Se confianca < 70, acao DEVE ser "nao_operar"
- Se tendencia = "neutro", acao DEVE ser "nao_operar"
- tp e sl são opcionais (pode ser null), mas recomendados quando acao != "nao_operar"
- Analise todos os indicadores e padrões antes de decidir
- Seja conservador: só recomende trade se houver alta confiança (>=70) e sinais claros

Responda APENAS com o JSON, sem texto adicional."""
        
        return prompt
    
    def _consultar_groq(self, prompt: str) -> str:
        """
        Consulta API Groq com retry automático.
        
        Args:
            prompt: Prompt formatado
            
        Returns:
            str: Resposta do LLM
            
        Raises:
            ValueError: Se API key não configurada
            requests.RequestException: Se falhar após todas as tentativas
        """
        if not self.llama_api_key:
            raise ValueError("IA_API_KEY não configurada")
        
        # Valida que a API key não está vazia
        if not self.llama_api_key.strip():
            raise ValueError("IA_API_KEY está vazia")
        
        headers = {
            "Authorization": f"Bearer {self.llama_api_key}",
            "Content-Type": "application/json",
        }
        
        # Payload no formato OpenAI (Groq 2025)
        payload = {
            "model": self.llama_model,
            "messages": [
                {
                    "role": "system",
                    "content": "Você é um analista especializado em trading algorítmico e análise de padrões de mercado."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.2,  # Temperatura mais baixa para respostas mais consistentes (recomendado para trading)
            "max_tokens": 2000,  # Aumentado para permitir respostas JSON mais completas
        }
        
        # Retry logic
        ultimo_erro = None
        for tentativa in range(1, self.api_retry_attempts + 1):
            try:
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Consultando Groq API "
                        f"(tentativa {tentativa}/{self.api_retry_attempts}, modelo: {self.llama_model}, "
                        f"URL: {self.llama_api_url})"
                    )
                
                response = requests.post(
                    self.llama_api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.api_timeout,
                )
                
                # Log da resposta para debug
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Resposta HTTP {response.status_code} recebida"
                    )
                
                response.raise_for_status()
                resultado = response.json()
                
                # Validação da resposta
                if not isinstance(resultado, dict):
                    raise ValueError(f"Resposta da API não é um dicionário: {type(resultado)}")
                
                # Extrai texto da resposta (suporta múltiplos formatos)
                conteudo = None
                
                if "choices" in resultado and len(resultado["choices"]) > 0:
                    choice = resultado["choices"][0]
                    if isinstance(choice, dict):
                        if "message" in choice:
                            conteudo = choice["message"].get("content")
                        elif "text" in choice:
                            conteudo = choice["text"]
                
                if not conteudo:
                    # Tenta formato alternativo
                    if "content" in resultado:
                        conteudo = resultado["content"]
                    elif "text" in resultado:
                        conteudo = resultado["text"]
                
                if not conteudo:
                    raise ValueError(
                        f"Resposta da API não contém conteúdo válido. Estrutura: {list(resultado.keys())}"
                    )
                
                # Armazena última resposta para debug
                self._ultima_resposta_api = conteudo
                
                # Log TRACE: Resposta completa
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] TRACE — Resposta completa recebida ({len(conteudo)} caracteres): {conteudo}"
                    )
                
                return conteudo
                
            except requests.exceptions.Timeout:
                ultimo_erro = "Timeout na requisição"
                if tentativa < self.api_retry_attempts:
                    import time
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Timeout na tentativa {tentativa}. "
                            f"Tentando novamente em {self.api_retry_delay}s..."
                        )
                    time.sleep(self.api_retry_delay)
                    continue
                    
            except requests.exceptions.HTTPError as e:
                # Tenta obter detalhes do erro da resposta
                error_details = {}
                error_message = "N/A"
                wait_time = None
                try:
                    if e.response.content:
                        error_details = e.response.json()
                        if isinstance(error_details, dict) and "error" in error_details:
                            error_info = error_details["error"]
                            error_message = error_info.get("message", "N/A")
                            error_type = error_info.get("type", "N/A")
                            error_code = error_info.get("code", "N/A")
                            ultimo_erro = f"HTTP {e.response.status_code}: {error_message} (tipo: {error_type}, código: {error_code})"
                            
                            # Extrai tempo de espera da mensagem de rate limit (429)
                            if e.response.status_code == 429 and "try again in" in error_message.lower():
                                import re
                                match = re.search(r'try again in ([\d.]+)s', error_message, re.IGNORECASE)
                                if match:
                                    wait_time = float(match.group(1)) + 0.5  # Adiciona 0.5s de margem
                        else:
                            ultimo_erro = f"HTTP {e.response.status_code}: {e}. Detalhes: {error_details}"
                    else:
                        ultimo_erro = f"HTTP {e.response.status_code}: {e}. Sem conteúdo na resposta"
                except Exception as parse_error:
                    ultimo_erro = f"HTTP {e.response.status_code}: {e}. Response: {e.response.text[:500] if hasattr(e.response, 'text') else 'N/A'}"
                
                # Log reduzido - apenas para erros críticos ou rate limit
                if self.logger:
                    if e.response.status_code == 429:
                        # Rate limit - log mais conciso
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Rate limit (429) na tentativa {tentativa}/{self.api_retry_attempts}. "
                            f"{f'Aguardando {wait_time:.1f}s...' if wait_time else f'Aguardando {self.api_retry_delay}s...'}"
                        )
                    elif e.response.status_code == 404:
                        # 404 - log detalhado apenas na primeira tentativa
                        if tentativa == 0:
                            api_key_preview = f"{self.llama_api_key[:10]}..." if self.llama_api_key and len(self.llama_api_key) > 10 else "N/A"
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] Erro 404: Modelo '{self.llama_model}' não encontrado. "
                                f"Verifique a API key e disponibilidade do modelo."
                            )
                    elif e.response.status_code >= 500:
                        # Erros de servidor - log conciso
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Erro {e.response.status_code} na tentativa {tentativa}/{self.api_retry_attempts}"
                        )
                
                # Tratamento especial para rate limit (429)
                if e.response.status_code == 429:
                    if tentativa < self.api_retry_attempts:
                        import time
                        # Usa tempo extraído da mensagem ou backoff exponencial
                        if wait_time:
                            delay = wait_time
                        else:
                            # Backoff exponencial: 2^tentativa * delay_base
                            delay = (2 ** tentativa) * self.api_retry_delay
                            delay = min(delay, 60)  # Máximo de 60s
                        
                        time.sleep(delay)
                        continue
                    else:
                        # Última tentativa falhou - não retry mais
                        break
                
                # Não retry em outros erros 4xx (erro do cliente)
                if 400 <= e.response.status_code < 500:
                    break
                    
                # Retry para erros 5xx com backoff exponencial
                if e.response.status_code >= 500 and tentativa < self.api_retry_attempts:
                    import time
                    delay = (2 ** tentativa) * self.api_retry_delay
                    delay = min(delay, 60)  # Máximo de 60s
                    time.sleep(delay)
                    continue
                    
            except requests.exceptions.RequestException as e:
                ultimo_erro = f"Erro de requisição: {e}"
                if tentativa < self.api_retry_attempts:
                    import time
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Erro na requisição (tentativa {tentativa}): {e}. "
                            f"Tentando novamente em {self.api_retry_delay}s..."
                        )
                    time.sleep(self.api_retry_delay)
                    continue
                    
            except Exception as e:
                ultimo_erro = f"Erro inesperado: {e}"
                if self.logger:
                    self.logger.error(
                        f"[{self.PLUGIN_NAME}] Erro ao processar resposta da API: {e}",
                        exc_info=True,
                    )
                break
        
        # Se chegou aqui, todas as tentativas falharam
        if self.logger:
            self.logger.error(
                f"[{self.PLUGIN_NAME}] Falha após {self.api_retry_attempts} tentativas. "
                f"Último erro: {ultimo_erro}"
            )
        raise requests.exceptions.RequestException(
            f"Falha ao consultar API após {self.api_retry_attempts} tentativas: {ultimo_erro}"
        )
    
    def _remover_repeticoes_insight(self, texto: str) -> str:
        """
        Remove repetições de frases completas no texto do insight.
        
        Args:
            texto: Texto do insight que pode conter repetições
            
        Returns:
            str: Texto sem repetições
        """
        if not texto or len(texto) < 50:
            return texto
        
        # Divide em frases (separadas por ponto, vírgula ou quebra de linha)
        import re
        frases = re.split(r'[.\n]', texto)
        frases_unicas = []
        frases_vistas = set()
        
        for frase in frases:
            frase_limpa = frase.strip()
            if not frase_limpa or len(frase_limpa) < 20:
                continue
            
            # Normaliza frase para comparação (remove espaços extras, lowercase)
            frase_normalizada = " ".join(frase_limpa.split()).lower()
            
            # Se a frase já foi vista, pula (é repetição)
            if frase_normalizada in frases_vistas:
                continue
            
            frases_vistas.add(frase_normalizada)
            frases_unicas.append(frase_limpa)
        
        # Se removeu muitas repetições, retorna texto limpo
        if len(frases_unicas) < len(frases) * 0.5:
            # Muitas repetições detectadas - retorna apenas frases únicas
            return ". ".join(frases_unicas[:10])  # Limita a 10 frases únicas
        
        return texto
    
    def _extrair_insights(
        self, resposta: str, dados: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extrai insights estruturados da resposta do LLM (modo análise).
        
        Suporta múltiplos formatos de resposta:
        - "Insight: ..."
        - "Sugestão: ..."
        - Markdown com ##
        - Lista numerada
        - JSON com estrutura de insights
        
        Args:
            resposta: Resposta textual do LLM
            dados: Dados originais usados na análise
            
        Returns:
            list: Lista de insights estruturados
        """
        insights = []
        
        # Extrai par mais frequente dos dados
        pares = [d.get("par", "UNKNOWN") for d in dados]
        par_principal = max(set(pares), key=pares.count) if pares else "UNKNOWN"
        
        # Tenta parsear como JSON primeiro (formato esperado do prompt ativo)
        try:
            # Remove markdown code blocks se houver
            resposta_limpa = resposta.strip()
            if resposta_limpa.startswith("```json"):
                resposta_limpa = resposta_limpa[7:]
            if resposta_limpa.startswith("```"):
                resposta_limpa = resposta_limpa[3:]
            if resposta_limpa.endswith("```"):
                resposta_limpa = resposta_limpa[:-3]
            resposta_limpa = resposta_limpa.strip()
            
            # Tenta parsear JSON
            dados_json = json.loads(resposta_limpa)
            if isinstance(dados_json, dict) and "insights" in dados_json:
                for insight_data in dados_json["insights"]:
                    insight_obj = {
                        "par": par_principal,
                        "modo": "ativo" if self.ia_on else "passivo",
                        "insight": insight_data.get("insight", ""),
                        "confianca": insight_data.get("confianca", 0.5),
                        "dados_contexto": json.dumps({
                            "total_dados": len(dados),
                            "pares": list(set(pares)),
                            "contagens": [d.get("contagem", 0) for d in dados],
                        }),
                        "versao_sistema": self.plugin_versao,
                    }
                    
                    # Extrai sugestão de entrada se houver
                    sugestao_entrada = insight_data.get("sugestao_entrada")
                    if sugestao_entrada and isinstance(sugestao_entrada, dict):
                        insight_obj["sugestao_entrada"] = sugestao_entrada
                    
                    insights.append(insight_obj)
                
                if insights:
                    return insights
        except (json.JSONDecodeError, KeyError, ValueError):
            # Se não for JSON válido, continua com parse textual
            pass
        
        # Parse melhorado da resposta (fallback para formato textual)
        linhas = resposta.split("\n")
        insight_atual = ""
        sugestao_atual = ""
        insights_multiplos = []
        
        # Lista de frases introdutórias a ignorar
        frases_intro = [
            "aqui está",
            "aqui está a",
            "segue a",
            "segue",
            "análise dos dados",
            "dados fornecidos",
            "análise:",
            "insight:",
            "resposta:",
        ]
        
        for linha in linhas:
            linha_limpa = linha.strip()
            
            # Ignora linhas vazias
            if not linha_limpa:
                continue
            
            # Detecta diferentes formatos
            if linha_limpa.lower().startswith("insight:") or linha_limpa.lower().startswith("insight :"):
                texto = linha_limpa.split(":", 1)[1].strip() if ":" in linha_limpa else linha_limpa[8:].strip()
                if texto and len(texto) > 20:  # Mínimo de 20 caracteres para ser válido
                    insights_multiplos.append({"tipo": "insight", "texto": texto})
                    
            elif linha_limpa.lower().startswith("sugestão:") or linha_limpa.lower().startswith("sugestão :"):
                texto = linha_limpa.split(":", 1)[1].strip() if ":" in linha_limpa else linha_limpa[10:].strip()
                if texto:
                    sugestao_atual = texto
                    
            elif linha_limpa.startswith("- Insight:") or linha_limpa.startswith("* Insight:"):
                texto = linha_limpa.split(":", 1)[1].strip() if ":" in linha_limpa else ""
                if texto and len(texto) > 20:
                    insights_multiplos.append({"tipo": "insight", "texto": texto})
                    
            elif linha_limpa.startswith("## Insight") or linha_limpa.startswith("# Insight"):
                # Pega próxima linha como conteúdo
                continue
                
            elif linha_limpa and not linha_limpa.startswith("#") and not linha_limpa.startswith("*"):
                # Verifica se é uma frase introdutória
                linha_lower = linha_limpa.lower()
                is_intro = any(linha_lower.startswith(intro) for intro in frases_intro)
                
                # Se não é introdutória e tem conteúdo suficiente, adiciona ao insight
                if not is_intro and len(linha_limpa) > 20:
                    if not insight_atual:
                        insight_atual = linha_limpa
                    else:
                        # Concatena múltiplas linhas de insight
                        insight_atual += " " + linha_limpa
        
        # Processa insights múltiplos ou único
        if insights_multiplos:
            for item in insights_multiplos:
                insights.append({
                    "par": par_principal,
                    "modo": "ativo" if self.ia_on else "passivo",
                    "insight": item["texto"],
                    "sugestao": sugestao_atual if self.ia_on and sugestao_atual else None,
                    "dados_contexto": json.dumps({
                        "total_dados": len(dados),
                        "pares": list(set(pares)),
                        "contagens": [d.get("contagem", 0) for d in dados],
                    }),
                    "versao_sistema": self.plugin_versao,
                })
        elif insight_atual:
            # Usa insight extraído (já filtrado de introdutórias)
            if len(insight_atual) > 20:  # Mínimo de 20 caracteres
                insights.append({
                    "par": par_principal,
                    "modo": "ativo" if self.ia_on else "passivo",
                    "insight": insight_atual,
                    "sugestao": sugestao_atual if self.ia_on and sugestao_atual else None,
                    "dados_contexto": json.dumps({
                        "total_dados": len(dados),
                        "pares": list(set(pares)),
                        "contagens": [d.get("contagem", 0) for d in dados],
                    }),
                    "versao_sistema": self.plugin_versao,
                })
        elif resposta:
            # Fallback: usa resposta completa, mas filtra linhas introdutórias
            linhas_resposta = resposta.strip().split("\n")
            linhas_filtradas = []
            linhas_unicas = set()  # Evita duplicatas
            
            for linha in linhas_resposta:
                linha_limpa = linha.strip()
                if not linha_limpa:
                    continue
                linha_lower = linha_limpa.lower()
                is_intro = any(linha_lower.startswith(intro) for intro in frases_intro)
                
                # Ignora linhas introdutórias e muito curtas
                if not is_intro and len(linha_limpa) > 20:
                    # Normaliza para detectar duplicatas (remove espaços extras, lowercase)
                    linha_normalizada = " ".join(linha_limpa.split()).lower()
                    if linha_normalizada not in linhas_unicas:
                        linhas_unicas.add(linha_normalizada)
                        linhas_filtradas.append(linha_limpa)
            
            if linhas_filtradas:
                texto_insight = " ".join(linhas_filtradas)
                
                # Remove repetições de frases completas (detecta padrões repetitivos)
                texto_insight = self._remover_repeticoes_insight(texto_insight)
                
                if len(texto_insight) > 20:
                    insights.append({
                        "par": par_principal,
                        "modo": "ativo" if self.ia_on else "passivo",
                        "insight": texto_insight,
                        "sugestao": sugestao_atual if self.ia_on and sugestao_atual else None,
                        "dados_contexto": json.dumps({
                            "total_dados": len(dados),
                            "pares": list(set(pares)),
                            "contagens": [d.get("contagem", 0) for d in dados],
                        }),
                        "versao_sistema": self.plugin_versao,
                    })
        
        return insights
    
    def _extrair_insights_com_trade(
        self, resposta: str, dados: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extrai insights e decisão de trade da resposta do LLM (modo trade automático).
        
        Args:
            resposta: Resposta textual do LLM (deve ser JSON)
            dados: Dados originais usados na análise
            
        Returns:
            list: Lista de insights com decisão de trade incluída
        """
        insights = []
        
        # Extrai par mais frequente dos dados
        pares = [d.get("par", "UNKNOWN") for d in dados]
        par_principal = max(set(pares), key=pares.count) if pares else "UNKNOWN"
        
        try:
            # Remove markdown code blocks se houver
            resposta_limpa = resposta.strip()
            if resposta_limpa.startswith("```json"):
                resposta_limpa = resposta_limpa[7:]
            if resposta_limpa.startswith("```"):
                resposta_limpa = resposta_limpa[3:]
            if resposta_limpa.endswith("```"):
                resposta_limpa = resposta_limpa[:-3]
            resposta_limpa = resposta_limpa.strip()
            
            # Tenta parsear JSON
            decisao_trade = json.loads(resposta_limpa)
            
            if not isinstance(decisao_trade, dict):
                raise ValueError("Resposta não é um objeto JSON válido")
            
            # Cria insight com decisão de trade
            insight_obj = {
                "par": decisao_trade.get("par", par_principal),
                "modo": "trade_automatico",
                "insight": decisao_trade.get("motivo", "Decisão de trade gerada pela IA"),
                "confianca": decisao_trade.get("confianca", 0),
                "dados_contexto": json.dumps({
                    "total_dados": len(dados),
                    "pares": list(set(pares)),
                    "contagens": [d.get("contagem", 0) for d in dados],
                }),
                "versao_sistema": self.plugin_versao,
                "decisao_trade": decisao_trade,  # Inclui toda a decisão
            }
            
            insights.append(insight_obj)
            
            # Log específico para trade
            if self.gerenciador_log:
                self.gerenciador_log.log_evento(
                    tipo_log="ia",
                    nome_origem="PluginIA_autotrade",
                    tipo_evento="decisao_recebida",
                    mensagem=f"Decisão recebida: {decisao_trade.get('acao', 'N/A')} - Confiança: {decisao_trade.get('confianca', 0)}%",
                    nivel=logging.INFO,
                    detalhes=decisao_trade,
                    par=decisao_trade.get("par", par_principal)
                )
            
        except json.JSONDecodeError as e:
            # JSON inválido - loga erro
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao parsear JSON de decisão de trade: {e}",
                    exc_info=True,
                )
            if self.gerenciador_log:
                self.gerenciador_log.log_evento(
                    tipo_log="ia",
                    nome_origem="PluginIA_json",
                    tipo_evento="erro_parse",
                    mensagem=f"Erro ao parsear JSON de decisão: {str(e)}",
                    nivel=logging.ERROR,
                    detalhes={"resposta": resposta[:500]},
                    par=par_principal
                )
            
            # Cria insight de erro
            insights.append({
                "par": par_principal,
                "modo": "trade_automatico",
                "insight": f"Erro ao processar decisão de trade: JSON inválido",
                "confianca": 0,
                "dados_contexto": json.dumps({
                    "erro": str(e),
                    "resposta_preview": resposta[:200],
                }),
                "versao_sistema": self.plugin_versao,
            })
        
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao extrair decisão de trade: {e}",
                    exc_info=True,
                )
            if self.gerenciador_log:
                self.gerenciador_log.log_evento(
                    tipo_log="ia",
                    nome_origem="PluginIA_warning",
                    tipo_evento="erro_extracao",
                    mensagem=f"Erro ao extrair decisão: {str(e)}",
                    nivel=logging.ERROR,
                    detalhes={"erro": str(e)},
                    par=par_principal
                )
        
        return insights
    
    def _processar_decisao_trade(
        self, decisao_trade: Dict[str, Any], par: str
    ) -> Optional[Dict[str, Any]]:
        """
        Processa decisão de trade e executa validações obrigatórias.
        
        Regras de validação:
        1. Confiança mínima: confianca >= 70
        2. Tendência neutra: se tendencia = "neutro" → ignorar
        3. JSON inválido: faltar campos → ignorar
        4. Timeframes quebrados: par problemático → bloquear
        5. 1 operação por par: já existe operação aberta → não permitir
        6. Falha de comunicação: sem resposta válida → não agir
        
        Args:
            decisao_trade: Dicionário com decisão de trade
            par: Nome do par
            
        Returns:
            dict: Resultado do processamento (None se não executou)
        """
        if not decisao_trade:
            return None
        
        # Validação 1: Confiança mínima
        confianca = decisao_trade.get("confianca", 0)
        if confianca < 70:
            motivo = f"Confiança insuficiente: {confianca}% < 70%"
            self._log_decisao_trade(par, decisao_trade, "rejeitado", motivo)
            return {
                "status": "rejeitado",
                "motivo": motivo,
                "decisao": decisao_trade,
            }
        
        # Validação 2: Tendência neutra
        tendencia = decisao_trade.get("tendencia", "").lower()
        if tendencia == "neutro":
            motivo = "Tendência neutra - não operar"
            self._log_decisao_trade(par, decisao_trade, "rejeitado", motivo)
            return {
                "status": "rejeitado",
                "motivo": motivo,
                "decisao": decisao_trade,
            }
        
        # Validação 3: JSON inválido (campos obrigatórios)
        campos_obrigatorios = ["par", "tendencia", "confianca", "motivo", "acao"]
        campos_faltando = [campo for campo in campos_obrigatorios if campo not in decisao_trade]
        if campos_faltando:
            motivo = f"Campos obrigatórios faltando: {', '.join(campos_faltando)}"
            self._log_decisao_trade(par, decisao_trade, "rejeitado", motivo)
            if self.gerenciador_log:
                self.gerenciador_log.log_evento(
                    tipo_log="ia",
                    nome_origem="PluginIA_json",
                    tipo_evento="json_invalido",
                    mensagem=motivo,
                    nivel=logging.ERROR,
                    detalhes={"campos_faltando": campos_faltando, "decisao": decisao_trade},
                    par=par
                )
            return {
                "status": "rejeitado",
                "motivo": motivo,
                "decisao": decisao_trade,
            }
        
        # Validação 4: Timeframes quebrados
        if par in self._pares_problematicos:
            motivo = f"Par {par} marcado como problemático (timeframes quebrados)"
            self._log_decisao_trade(par, decisao_trade, "rejeitado", motivo)
            if self.gerenciador_log:
                self.gerenciador_log.log_evento(
                    tipo_log="ia",
                    nome_origem="PluginIA_warning",
                    tipo_evento="par_problematico",
                    mensagem=motivo,
                    nivel=logging.WARNING,
                    detalhes={"par": par},
                    par=par
                )
            return {
                "status": "rejeitado",
                "motivo": motivo,
                "decisao": decisao_trade,
            }
        
        # Validação 5: 1 operação por par
        if par in self._posicoes_abertas:
            motivo = f"Já existe operação aberta para {par}"
            self._log_decisao_trade(par, decisao_trade, "rejeitado", motivo)
            if self.gerenciador_log:
                self.gerenciador_log.log_evento(
                    tipo_log="ia",
                    nome_origem="PluginIA_warning",
                    tipo_evento="posicao_ja_aberta",
                    mensagem=motivo,
                    nivel=logging.WARNING,
                    detalhes={"par": par, "posicao_existente": self._posicoes_abertas[par]},
                    par=par
                )
            return {
                "status": "rejeitado",
                "motivo": motivo,
                "decisao": decisao_trade,
            }
        
        # Validação 6: Falha de comunicação (já validado antes)
        acao = decisao_trade.get("acao", "").lower()
        if acao == "nao_operar":
            motivo = "IA decidiu não operar"
            self._log_decisao_trade(par, decisao_trade, "nao_operar", motivo)
            return {
                "status": "nao_operar",
                "motivo": motivo,
                "decisao": decisao_trade,
            }
        
        # Todas as validações passaram - executa trade
        return self._executar_trade(decisao_trade, par)
    
    def _executar_trade(
        self, decisao_trade: Dict[str, Any], par: str
    ) -> Optional[Dict[str, Any]]:
        """
        Executa trade via PluginBybitConexao.
        
        Args:
            decisao_trade: Dicionário com decisão de trade validada
            par: Nome do par
            
        Returns:
            dict: Resultado da execução
        """
        if not self.plugin_bybit_conexao:
            motivo = "PluginBybitConexao não disponível"
            self._log_decisao_trade(par, decisao_trade, "erro", motivo)
            return {
                "status": "erro",
                "motivo": motivo,
                "decisao": decisao_trade,
            }
        
        try:
            exchange = self.plugin_bybit_conexao.obter_exchange()
            if not exchange:
                motivo = "Exchange não disponível ou conexão inativa"
                self._log_decisao_trade(par, decisao_trade, "erro", motivo)
                return {
                    "status": "erro",
                    "motivo": motivo,
                    "decisao": decisao_trade,
                }
            
            acao = decisao_trade.get("acao", "").lower()
            tp = decisao_trade.get("tp")
            sl = decisao_trade.get("sl")
            
            # Determina direção (LONG ou SHORT)
            if acao == "comprar":
                side = "Buy"
                direcao = "LONG"
            elif acao == "vender":
                side = "Sell"
                direcao = "SHORT"
            else:
                motivo = f"Ação inválida: {acao}"
                self._log_decisao_trade(par, decisao_trade, "erro", motivo)
                return {
                    "status": "erro",
                    "motivo": motivo,
                    "decisao": decisao_trade,
                }
            
            # Executa ordem de mercado
            # Nota: Por padrão, usa quantidade mínima. Pode ser ajustado conforme configuração.
            ordem_resultado = exchange.create_market_order(
                symbol=par,
                side=side,
                amount=None,  # Deixa a exchange calcular baseado no saldo
                params={
                    "timeInForce": "IOC",  # Immediate or Cancel
                }
            )
            
            # Registra posição aberta
            self._posicoes_abertas[par] = {
                "timestamp": datetime.now(timezone.utc),
                "decisao": decisao_trade,
                "ordem": ordem_resultado,
                "direcao": direcao,
                "tp": tp,
                "sl": sl,
            }
            
            # Se TP/SL foram fornecidos, cria ordens de stop/take profit
            if tp or sl:
                # Por enquanto, apenas registra. Pode ser implementado depois.
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] TP/SL fornecidos (TP: {tp}, SL: {sl}) - "
                        "Ordens de stop/take profit podem ser configuradas separadamente"
                    )
            
            # Log de sucesso
            self._log_decisao_trade(par, decisao_trade, "executado", "Trade executado com sucesso", ordem_resultado)
            
            # Armazena no banco
            self._armazenar_trade(decisao_trade, "executado", ordem_resultado)
            
            return {
                "status": "executado",
                "ordem": ordem_resultado,
                "decisao": decisao_trade,
            }
            
        except Exception as e:
            motivo = f"Erro ao executar trade: {str(e)}"
            self._log_decisao_trade(par, decisao_trade, "erro", motivo)
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao executar trade: {e}",
                    exc_info=True,
                )
            if self.gerenciador_log:
                self.gerenciador_log.log_evento(
                    tipo_log="ia",
                    nome_origem="PluginIA_autotrade",
                    tipo_evento="erro_execucao",
                    mensagem=motivo,
                    nivel=logging.ERROR,
                    detalhes={"erro": str(e), "decisao": decisao_trade},
                    par=par
                )
            
            # Armazena erro no banco
            self._armazenar_trade(decisao_trade, "erro", {"erro": str(e)})
            
            return {
                "status": "erro",
                "motivo": motivo,
                "decisao": decisao_trade,
            }
    
    def _log_decisao_trade(
        self,
        par: str,
        decisao_trade: Dict[str, Any],
        status: str,
        motivo: str,
        ordem_resultado: Optional[Dict[str, Any]] = None,
    ):
        """
        Loga decisão de trade com categoria específica.
        
        Args:
            par: Nome do par
            decisao_trade: Decisão de trade
            status: Status (executado, rejeitado, erro, etc.)
            motivo: Motivo do status
            ordem_resultado: Resultado da ordem (se executado)
        """
        if not self.gerenciador_log:
            return
        
        detalhes = {
            "decisao": decisao_trade,
            "status": status,
            "motivo": motivo,
        }
        
        if ordem_resultado:
            detalhes["ordem"] = ordem_resultado
        
        nivel = logging.INFO if status == "executado" else logging.WARNING
        
        self.gerenciador_log.log_evento(
            tipo_log="ia",
            nome_origem="PluginIA_autotrade",
            tipo_evento=f"decisao_{status}",
            mensagem=f"{status.upper()}: {motivo} - Confiança: {decisao_trade.get('confianca', 0)}%",
            nivel=nivel,
            detalhes=detalhes,
            par=par
        )
    
    def _armazenar_trade(
        self,
        decisao_trade: Dict[str, Any],
        status: str,
        resultado: Dict[str, Any],
    ):
        """
        Armazena trade no banco de dados.
        
        Args:
            decisao_trade: Decisão de trade
            status: Status da execução
            resultado: Resultado da ordem ou erro
        """
        if not self.gerenciador_banco:
            return
        
        try:
            dados = {
                "timestamp": datetime.now(timezone.utc),
                "par": decisao_trade.get("par", "UNKNOWN"),
                "tendencia": decisao_trade.get("tendencia"),
                "confianca": decisao_trade.get("confianca"),
                "motivo": decisao_trade.get("motivo"),
                "acao": decisao_trade.get("acao"),
                "tp": decisao_trade.get("tp"),
                "sl": decisao_trade.get("sl"),
                "status": status,
                "resultado": resultado,
                "versao_sistema": self.plugin_versao,
            }
            
            self.persistir_dados("ia_trades", dados)
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao armazenar trade: {e}",
                    exc_info=True,
                )
    
    def _armazenar_insight(self, insight: Dict[str, Any]):
        """Armazena insight no PostgreSQL via GerenciadorBanco."""
        if not self.gerenciador_banco:
            return
        
        try:
            dados = {
                "timestamp": datetime.now(timezone.utc),
                "par": insight.get("par", "UNKNOWN"),
                "modo": insight.get("modo", "passivo"),
                "insight": insight.get("insight", ""),
                "dados_contexto": json.loads(insight.get("dados_contexto", "{}")) if isinstance(insight.get("dados_contexto"), str) else insight.get("dados_contexto", {}),
                "sugestao": insight.get("sugestao"),
                "versao_sistema": insight.get("versao_sistema", self.plugin_versao),
            }
            
            self.persistir_dados("ia_insights", dados)
            
            if self.logger:
                modo = insight.get("modo", "passivo")
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Insight gerado (modo: {modo}): "
                    f"{insight.get('insight', '')[:100]}..."
                )
                
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao armazenar insight: {e}",
                    exc_info=True,
                )
    
    def processar_buffer_pendente(self) -> List[Dict[str, Any]]:
        """
        Força processamento do buffer mesmo se não estiver completo.
        
        Útil para processar dados restantes antes de finalizar ou quando
        há necessidade de análise imediata.
        
        Returns:
            list: Lista de insights gerados
        """
        if not self._buffer_dados:
            return []
        
        try:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Processando buffer pendente "
                    f"({len(self._buffer_dados)} itens)"
                )
            
            insights = self._processar_buffer()
            self._buffer_dados.clear()
            
            return insights
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao processar buffer pendente: {e}",
                    exc_info=True,
                )
            return []
    
    def obter_estatisticas(self) -> Dict[str, Any]:
        """
        Obtém estatísticas do plugin.
        
        Returns:
            dict: Estatísticas incluindo:
                - total_insights: Total de insights gerados
                - total_dados_armazenados: Total de dados no histórico
                - buffer_atual: Tamanho atual do buffer
                - modo: Modo atual (ativo/passivo)
                - modo_trades: Modo de trades (ativo/desativado)
                - posicoes_abertas: Número de posições abertas
                - ultima_analise: Timestamp da última análise
        """
        try:
            return {
                "total_insights": 0,  # Será implementado via PostgreSQL
                "total_dados_armazenados": 0,  # Será implementado via PostgreSQL
                "buffer_atual": len(self._buffer_dados),
                "buffer_size_max": self._buffer_tamanho_max,
                "modo": "ativo" if self.ia_on else "passivo",
                "modo_trades": "ativo" if self.ia_trades else "desativado",
                "posicoes_abertas": len(self._posicoes_abertas),
                "pares_problematicos": len(self._pares_problematicos),
                "ultima_analise": None,  # Será implementado via PostgreSQL
            }
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao obter estatísticas: {e}",
                    exc_info=True,
                )
            return {}
    
    def _finalizar_interno(self) -> bool:
        """Finaliza recursos específicos do plugin."""
        try:
            # Processa buffer pendente antes de finalizar
            if self._buffer_dados:
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Processando {len(self._buffer_dados)} "
                        "itens pendentes no buffer antes de finalizar"
                    )
                self.processar_buffer_pendente()
            
            # Limpa buffer
            self._buffer_dados.clear()
            
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Recursos finalizados"
                )
            
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao finalizar: {e}",
                    exc_info=True,
                )
            return False
    
    def obter_insights_recentes(
        self, 
        par: Optional[str] = None,
        limite: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Obtém insights recentes do banco.
        
        Args:
            par: Filtro por par (opcional)
            limite: Quantidade de insights
            
        Returns:
            list: Lista de insights
        """
        # TODO: Implementar via GerenciadorBanco quando plugin BancoDados estiver pronto
        if self.logger:
            self.logger.warning(
                f"[{self.PLUGIN_NAME}] obter_insights_recentes não implementado ainda. "
                "Aguardando plugin BancoDados."
            )
        return []
    
    def marcar_par_problematico(self, par: str):
        """
        Marca um par como problemático (timeframes quebrados).
        
        Args:
            par: Nome do par
        """
        self._pares_problematicos.add(par)
        if self.logger:
            self.logger.warning(
                f"[{self.PLUGIN_NAME}] Par {par} marcado como problemático"
            )
    
    def remover_par_problematico(self, par: str):
        """
        Remove marcação de par problemático.
        
        Args:
            par: Nome do par
        """
        self._pares_problematicos.discard(par)
        if self.logger:
            self.logger.info(
                f"[{self.PLUGIN_NAME}] Par {par} removido da lista de problemáticos"
            )
    
    def fechar_posicao(self, par: str):
        """
        Fecha posição aberta para um par.
        
        Args:
            par: Nome do par
        """
        if par in self._posicoes_abertas:
            del self._posicoes_abertas[par]
            if self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Posição para {par} fechada"
                )

