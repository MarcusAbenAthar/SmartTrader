"""
Plugin de Inteligência Artificial usando Llama 3.

Transforma dados brutos do sistema 6/8 em conhecimento acionável através de:
- Aprendizado passivo (modo estudo)
- Insights estratégicos (modo ativo)
- Análise de padrões de mercado e comportamento do bot

__institucional__ = "Smart_Trader Plugin IA Llama - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import json
import os
import requests
from plugins.base_plugin import Plugin, execucao_segura
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginIaLlama(Plugin):
    """
    Plugin de IA que aprende com dados do sistema 6/8 usando Llama 3.
    
    Funciona em dois modos:
    - Passivo (on=False): Apenas observa e aprende, gera insights neutros
    - Ativo (on=True): Pode sugerir ajustes estratégicos
    
    Características:
    - Persistência via PostgreSQL (GerenciadorBanco)
    - Consulta LLM (Llama 3 via API)
    - Não interfere nas decisões até ser explicitamente ativado
    - Registra tudo para rastreabilidade completa
    """
    
    __institucional__ = "Smart_Trader Plugin IA Llama - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginIaLlama"
    plugin_versao = "v1.0.0"
    plugin_schema_versao = "v1.0.0"
    
    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLogProtocol] = None,
        gerenciador_banco: Optional[GerenciadorBancoProtocol] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o PluginIaLlama.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            gerenciador_banco: Instância do GerenciadorBanco
            config: Configuração do sistema (deve conter ia_on e api keys)
        """
        super().__init__(gerenciador_log, gerenciador_banco, config)
        
        # Configuração de modo (passivo por padrão)
        self.ia_on: bool = self.config.get("ia", {}).get("on", False)
        
        # Configurações da API Llama
        self.llama_api_key: Optional[str] = os.getenv("LLAMA_API_KEY")
        self.llama_api_url: str = self.config.get("ia", {}).get(
            "api_url", "https://api.llama.ai/v1/chat/completions"
        )
        self.llama_model: str = self.config.get("ia", {}).get("model", "llama-3")
        
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
        
    def _inicializar_interno(self) -> bool:
        """
        Inicializa recursos específicos do plugin IA.
        
        Returns:
            bool: True se inicializado com sucesso
        """
        try:
            # Valida configurações
            if self.ia_on and not self.llama_api_key:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Modo ativo ativado mas LLAMA_API_KEY não encontrada. "
                        "Usando modo passivo."
                    )
                self.ia_on = False
            
            # Valida GerenciadorBanco (necessário para persistência)
            if not self.gerenciador_banco:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] GerenciadorBanco não disponível. "
                        "Persistência desabilitada."
                    )
            
            if self.logger:
                modo = "ATIVO" if self.ia_on else "PASSIVO"
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] Inicializado em modo {modo}. "
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
        }
    
    @execucao_segura
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executa análise de IA sobre dados do sistema 6/8.
        
        Args:
            dados_entrada: Dicionário com:
                - ohlcv: Dados OHLCV da vela
                - indicadores: Valores dos 8 indicadores
                - contagem: Contagem final (6/8, 7/8, 8/8)
                - resultado_trade: Resultado do trade (win/loss, R:R, duração)
                - contexto: Horário, volume 24h, volatilidade (ATR), par
                
        Returns:
            dict: Resultado com insights gerados
        """
        if not dados_entrada:
            return {
                "status": "erro",
                "mensagem": "Dados de entrada não fornecidos",
                "plugin": self.PLUGIN_NAME,
            }
        
        try:
            # Extrai dados
            par = dados_entrada.get("par", "UNKNOWN")
            ohlcv = dados_entrada.get("ohlcv", {})
            indicadores = dados_entrada.get("indicadores", {})
            contagem = dados_entrada.get("contagem", 0)
            resultado_trade = dados_entrada.get("resultado_trade", {})
            contexto = dados_entrada.get("contexto", {})
            
            # Armazena dados brutos no banco
            self._armazenar_dados_brutos(
                par=par,
                ohlcv=ohlcv,
                indicadores=indicadores,
                contagem=contagem,
                resultado_trade=resultado_trade,
                contexto=contexto,
            )
            
            # Adiciona ao buffer para análise em lote
            self._buffer_dados.append({
                "par": par,
                "ohlcv": ohlcv,
                "indicadores": indicadores,
                "contagem": contagem,
                "resultado_trade": resultado_trade,
                "contexto": contexto,
                "timestamp": datetime.now().isoformat(),
            })
            
            # Processa buffer quando atinge tamanho máximo
            if len(self._buffer_dados) >= self._buffer_tamanho_max:
                insights = self._processar_buffer()
                buffer_processado = len(self._buffer_dados)
                self._buffer_dados.clear()
                
                return {
                    "status": "ok",
                    "insights_gerados": len(insights),
                    "insights": insights,
                    "modo": "ativo" if self.ia_on else "passivo",
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
        Processa buffer de dados e gera insights via Llama.
        
        Returns:
            list: Lista de insights gerados
        """
        if not self._buffer_dados:
            return []
        
        try:
            # Prepara prompt baseado no modo
            if self.ia_on:
                prompt = self._gerar_prompt_ativo(self._buffer_dados)
            else:
                prompt = self._gerar_prompt_passivo(self._buffer_dados)
            
            # Consulta Llama 3
            resposta = self._consultar_llama(prompt)
            
            # Processa resposta e gera insights
            insights = self._extrair_insights(resposta, self._buffer_dados)
            
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
        Gera prompt liberado para modo ativo com sugestões.
        
        Args:
            dados: Lista de dados do buffer
            
        Returns:
            str: Prompt formatado
        """
        dados_formatados = json.dumps(dados, indent=2)
        
        prompt = f"""Você é um consultor estratégico especializado em trading algorítmico. 
Analise os dados abaixo do sistema 6/8 e forneça insights e sugestões estratégicas.

Dados do sistema 6/8:
{dados_formatados}

Formato da resposta esperado:
Insight: [descrição do padrão]
Sugestão: [recomendação estratégica opcional]

Analise os dados e forneça insights estratégicos com sugestões de otimização."""
        
        return prompt
    
    def _consultar_llama(self, prompt: str) -> str:
        """
        Consulta API Llama 3 com retry automático.
        
        Args:
            prompt: Prompt formatado
            
        Returns:
            str: Resposta do LLM
            
        Raises:
            ValueError: Se API key não configurada
            requests.RequestException: Se falhar após todas as tentativas
        """
        if not self.llama_api_key:
            raise ValueError("LLAMA_API_KEY não configurada")
        
        headers = {
            "Authorization": f"Bearer {self.llama_api_key}",
            "Content-Type": "application/json",
        }
        
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
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        
        # Retry logic
        ultimo_erro = None
        for tentativa in range(1, self.api_retry_attempts + 1):
            try:
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Consultando Llama API "
                        f"(tentativa {tentativa}/{self.api_retry_attempts}, modelo: {self.llama_model})"
                    )
                
                response = requests.post(
                    self.llama_api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.api_timeout,
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
                
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Resposta recebida ({len(conteudo)} caracteres)"
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
                ultimo_erro = f"HTTP {e.response.status_code}: {e}"
                # Não retry em erros 4xx (erro do cliente)
                if 400 <= e.response.status_code < 500:
                    break
                if tentativa < self.api_retry_attempts:
                    import time
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Erro HTTP {e.response.status_code} na tentativa {tentativa}. "
                            f"Tentando novamente em {self.api_retry_delay}s..."
                        )
                    time.sleep(self.api_retry_delay)
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
    
    def _extrair_insights(
        self, resposta: str, dados: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extrai insights estruturados da resposta do LLM.
        
        Suporta múltiplos formatos de resposta:
        - "Insight: ..."
        - "Sugestão: ..."
        - Markdown com ##
        - Lista numerada
        
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
        
        # Parse melhorado da resposta
        linhas = resposta.split("\n")
        insight_atual = ""
        sugestao_atual = ""
        insights_multiplos = []
        
        for linha in linhas:
            linha_limpa = linha.strip()
            
            # Detecta diferentes formatos
            if linha_limpa.startswith("Insight:") or linha_limpa.startswith("Insight :"):
                texto = linha_limpa.split(":", 1)[1].strip() if ":" in linha_limpa else linha_limpa[8:].strip()
                if texto:
                    insights_multiplos.append({"tipo": "insight", "texto": texto})
                    
            elif linha_limpa.startswith("Sugestão:") or linha_limpa.startswith("Sugestão :"):
                texto = linha_limpa.split(":", 1)[1].strip() if ":" in linha_limpa else linha_limpa[10:].strip()
                if texto:
                    sugestao_atual = texto
                    
            elif linha_limpa.startswith("- Insight:") or linha_limpa.startswith("* Insight:"):
                texto = linha_limpa.split(":", 1)[1].strip() if ":" in linha_limpa else ""
                if texto:
                    insights_multiplos.append({"tipo": "insight", "texto": texto})
                    
            elif linha_limpa.startswith("## Insight") or linha_limpa.startswith("# Insight"):
                # Pega próxima linha como conteúdo
                continue
                
            elif linha_limpa and not linha_limpa.startswith("#") and not linha_limpa.startswith("*"):
                # Se não há insights encontrados ainda, assume que toda resposta é um insight
                if not insights_multiplos and not insight_atual and len(linha_limpa) > 20:
                    insight_atual = linha_limpa
                    break
        
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
        elif insight_atual or resposta:
            # Fallback: usa primeiro insight ou resposta completa (limitado)
            texto_insight = insight_atual or resposta[:500].strip()
            if len(texto_insight) > 10:  # Mínimo de 10 caracteres
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
                self.logger.info(
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
                self.logger.info(
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
                - ultima_analise: Timestamp da última análise
        """
        try:
            # TODO: Implementar queries via GerenciadorBanco quando plugin BancoDados estiver pronto
            # Por enquanto retorna estatísticas básicas do buffer
            return {
                "total_insights": 0,  # Será implementado via PostgreSQL
                "total_dados_armazenados": 0,  # Será implementado via PostgreSQL
                "buffer_atual": len(self._buffer_dados),
                "buffer_size_max": self._buffer_tamanho_max,
                "modo": "ativo" if self.ia_on else "passivo",
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

