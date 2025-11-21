"""
Gerenciador de Logs do sistema Smart Trader.

Sistema de logs conversacional, objetivo e humano que serve como diário técnico e analítico.
Cada evento gravado segue estrutura simples com: data/hora UTC, origem, tipo de evento, 
resumo em texto, detalhes úteis e nível (INFO, WARN, ERROR).

Organização:
- logs/spot/      : Logs do mercado à vista
- logs/futures/   : Posições e contratos alavancados  
- logs/ia/        : Interpretações e sugestões do Llama
- logs/system/    : Inicialização, conexões, erros gerais

Cada arquivo leva o nome: {tipo_log}_2025-11-02.log (ex: system_2025-11-02.log, error_2025-11-02.log)
Rotação: a cada 5MB ou diária (compactação após 30 dias, retenção de 7 dias ativos).
"""

import logging
import os
import inspect
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler
import gzip
import shutil
import pytz

# Importa funcionalidades avançadas de log (cores, TRACE)
from utils.log_helper import SmartFormatter, TRACE_LEVEL
from enum import Enum


class CategoriaLog(Enum):
    """
    Categorias de log baseadas em responsabilidade funcional.
    
    Separação por responsabilidade, não por nível, para rastreabilidade real.
    """
    CORE = "CORE"           # Núcleo do sistema (ciclos, inicialização, versão)
    CONEXAO = "CONEXAO"     # Ligação com exchange (latency, timeouts, rate-limit)
    BANCO = "BANCO"          # Operações de banco (inserts, selects, transações)
    PLUGIN = "PLUGIN"        # Execução de plugins (início, dados, resultados)
    ANALISE = "ANALISE"      # Processamento de dados (cálculos, validações)
    SINAL = "SINAL"          # Sinais de trading (LONG, SHORT, força, timeframe)
    FILTRO = "FILTRO"        # Filtro dinâmico (pares aprovados, rejeições)
    IA = "IA"                # Inteligência artificial (decisões, pesos, validações)
    UTIL = "UTIL"            # Utilitários e helpers (conversores, checagens)


class GerenciadorLog:
    """
    Gerenciador centralizado de logs do sistema Smart Trader.
    
    Filosofia: Log conversacional, objetivo e humano - diário técnico que fala com você.
    
    Estrutura de diretórios:
    - logs/spot/      : Mercado à vista
    - logs/futures/  : Contratos perpétuos/alavancados
    - logs/ia/       : Análises e insights do Llama
    - logs/system/   : Sistema, inicialização, erros gerais
    
    Atributos:
        base_path (Path): Caminho base do diretório de logs
        loggers (dict): Cache de loggers criados
        formato_padrao (str): Formato padrão dos logs (UTC com milissegundos)
        retencao_dias (int): Dias de retenção de logs ativos (padrão: 7)
        retencao_arquivo_dias (int): Dias completos antes de compactar (padrão: 30)
    """

    def __init__(
        self, 
        base_path: str = "logs",
        retencao_dias: int = 7,
        retencao_arquivo_dias: int = 30
    ):
        """
        Inicializa o GerenciadorLog.
        
        Args:
            base_path: Caminho base do diretório de logs
            retencao_dias: Dias de retenção de logs ativos (padrão: 7)
            retencao_arquivo_dias: Dias completos antes de compactar (padrão: 30)
        """
        self.base_path = Path(base_path)
        self.loggers: Dict[str, logging.Logger] = {}
        
        # Timezone de São Paulo
        self.timezone_sp = pytz.timezone('America/Sao_Paulo')
        
        # Formato com timezone de São Paulo, milissegundos e informações de rastreamento
        # Suporta categoria opcional: [CATEGORIA] será adicionado quando especificado
        self.formato_padrao = (
            "[%(asctime)s.%(msecs)03d BRT] [%(name)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s"
        )
        self.formato_com_categoria = (
            "[%(asctime)s.%(msecs)03d BRT] [%(name)s] [%(levelname)s] [%(filename)s:%(lineno)d] [%(categoria)s] %(message)s"
        )
        self.data_format = "%Y-%m-%d %H:%M:%S"
        
        # Retenção
        self.retencao_dias = retencao_dias
        self.retencao_arquivo_dias = retencao_arquivo_dias
        
        # Cria estrutura de diretórios
        self._criar_estrutura_diretorios()
        
        # Garante que todos os arquivos de log sejam criados na inicialização
        self._criar_arquivos_log_iniciais()
        
        # Limpa logs antigos na inicialização
        self._limpar_logs_antigos()

    def _criar_estrutura_diretorios(self):
        """Cria a estrutura de diretórios de log conforme padrão."""
        diretorios = [
            "spot",
            "futures", 
            "ia",
            "system",
            "banco",
            "sinais",
            "erros",
            "warnings",
            "critical",
            "padroes",
        ]
        
        for diretorio in diretorios:
            caminho = self.base_path / diretorio
            caminho.mkdir(parents=True, exist_ok=True)
    
    def _criar_arquivos_log_iniciais(self):
        """
        Cria todos os arquivos de log na inicialização para garantir que existam.
        """
        tipos_log = ["spot", "futures", "ia", "system", "banco", "sinais", "erros", "warnings", "critical", "padroes"]
        for tipo_log in tipos_log:
            try:
                arquivo_log = self._obter_caminho_arquivo(tipo_log)
                # Garante que o arquivo existe e tem pelo menos uma linha
                if arquivo_log.exists() and arquivo_log.stat().st_size == 0:
                    with open(arquivo_log, 'a', encoding='utf-8') as f:
                        data_hora = datetime.now(self.timezone_sp).strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"[{data_hora} BRT] [GerenciadorLog] [INFO] [gerenciador_log.py:108] Arquivo de log '{tipo_log}' inicializado\n")
                        f.flush()
            except Exception:
                pass  # Ignora erros na criação inicial

    def get_logger(
        self,
        nome: str,
        tipo_log: str = "system",
        nivel: int = logging.INFO,
    ) -> logging.Logger:
        """
        Obtém ou cria um logger para o nome especificado.
        
        Tipos de log suportados:
        - spot: Mercado à vista
        - futures: Contratos perpétuos/alavancados
        - ia: Análises do Llama
        - system: Sistema, inicialização, erros gerais
        
        Args:
            nome: Nome do logger (geralmente PLUGIN_NAME ou componente)
            tipo_log: Tipo de log (spot, futures, ia, system)
            nivel: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            
        Returns:
            logging.Logger: Logger configurado
        """
        # Valida tipo_log
        tipos_validos = ["spot", "futures", "ia", "system", "banco", "sinais", "erros", "warnings", "critical", "padroes"]
        if tipo_log not in tipos_validos:
            tipo_log = "system"
        
        # Cache key único por nome e tipo
        cache_key = f"{nome}_{tipo_log}"
        
        if cache_key in self.loggers:
            return self.loggers[cache_key]
        
        # Cria novo logger
        logger = logging.getLogger(cache_key)
        logger.setLevel(nivel)
        
        # Remove handlers existentes (evita duplicação)
        logger.handlers.clear()
        
        # Handler para arquivo específico por tipo (formato: {tipo_log}_2025-11-02.log)
        arquivo_log = self._obter_caminho_arquivo(tipo_log)
        
        # Garante que o diretório existe
        arquivo_log.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            str(arquivo_log),  # Converte Path para string
            maxBytes=5 * 1024 * 1024,  # 5MB (conforme especificação)
            backupCount=10,  # Mantém últimos 10 arquivos rotacionados
            encoding="utf-8",
            delay=False,  # Cria arquivo imediatamente
        )
        file_handler.setLevel(nivel)
        
        # Formatter customizado com timezone de São Paulo e milissegundos
        class SPFormatter(logging.Formatter):
            def __init__(self, fmt=None, datefmt=None, timezone_sp=None, suporta_categoria=False):
                super().__init__(fmt, datefmt)
                self.timezone_sp = timezone_sp
                self.suporta_categoria = suporta_categoria
            
            def formatTime(self, record, datefmt=None):
                # Converte para timezone de São Paulo
                dt_utc = datetime.fromtimestamp(record.created, tz=pytz.UTC)
                dt_sp = dt_utc.astimezone(self.timezone_sp)
                if datefmt:
                    s = dt_sp.strftime(datefmt)
                else:
                    s = dt_sp.strftime(self.default_time_format)
                return s
            
            def format(self, record):
                # Verifica se a mensagem começa com [CATEGORIA] (ex: [CORE], [FILTRO])
                # Se sim, substitui o nível de log pela categoria
                # Estratégia: lê mensagem original ANTES de formatar
                mensagem_original = None
                try:
                    # Obtém mensagem original do record ANTES de formatar
                    if hasattr(record, 'msg'):
                        if isinstance(record.msg, str):
                            mensagem_original = record.msg
                        elif record.args:
                            # Se há args, a mensagem será formatada - precisamos processar depois
                            mensagem_original = None
                        else:
                            mensagem_original = str(record.msg)
                except:
                    pass
                
                # Se não conseguiu, tenta getMessage() mas isso pode já ter processado
                if not mensagem_original:
                    try:
                        mensagem_original = record.getMessage()
                    except:
                        mensagem_original = None
                
                categoria_extraida = None
                
                # Primeiro, verifica se a categoria foi armazenada diretamente no record
                if hasattr(record, '_categoria_log') and record._categoria_log:
                    categoria_extraida = record._categoria_log
                    # Remove categoria da mensagem se estiver presente
                    if mensagem_original and isinstance(mensagem_original, str) and mensagem_original.startswith(f"[{categoria_extraida}]"):
                        mensagem_sem_categoria = mensagem_original[len(f"[{categoria_extraida}]"):].strip()
                        record.msg = mensagem_sem_categoria
                        record.args = ()
                # Se não encontrou, tenta extrair da mensagem
                elif mensagem_original and isinstance(mensagem_original, str) and mensagem_original.startswith("[") and "]" in mensagem_original:
                    fim_categoria = mensagem_original.find("]")
                    if fim_categoria > 0:
                        categoria_extraida = mensagem_original[1:fim_categoria]
                        # Remove categoria da mensagem para não aparecer duplicada
                        mensagem_sem_categoria = mensagem_original[fim_categoria + 1:].strip()
                        record.msg = mensagem_sem_categoria
                        record.args = ()
                
                # Formata normalmente
                msg_formatada = super().format(record)
                
                # Se encontrou categoria, substitui [LEVEL] por [CATEGORIA] na mensagem formatada
                if categoria_extraida:
                    level = record.levelname
                    # Substitui [LEVEL] por [CATEGORIA] no formato (apenas primeira ocorrência)
                    if f"[{level}]" in msg_formatada:
                        msg_formatada = msg_formatada.replace(f"[{level}]", f"[{categoria_extraida}]", 1)
                
                return msg_formatada
        
        file_formatter = SPFormatter(
            self.formato_padrao, datefmt=self.data_format, timezone_sp=self.timezone_sp, suporta_categoria=True
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Handler para console (INFO e acima, formato simplificado com cores)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        # Usa SmartFormatter com cores para console
        console_formatter = SmartFormatter(
            "[%(asctime)s BRT] [%(name)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            timezone_sp=self.timezone_sp,
            use_colors=True  # Habilita cores no console
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # Evita propagação para logger raiz
        logger.propagate = False
        
        # Adiciona ao cache
        self.loggers[cache_key] = logger
        
        # Testa escrita no arquivo para garantir que funciona (DEBUG para não poluir inicialização)
        try:
            logger.debug(f"[{nome}] Logger inicializado para tipo '{tipo_log}' -> {arquivo_log.name}")
            # Força flush imediato
            for handler in logger.handlers:
                if hasattr(handler, 'flush'):
                    handler.flush()
        except Exception as e:
            # Se houver erro, loga no console
            print(f"[GerenciadorLog] AVISO: Erro ao criar arquivo de log {arquivo_log}: {e}")
        
        return logger

    def _obter_caminho_arquivo(self, tipo_log: str) -> Path:
        """
        Obtém o caminho do arquivo de log para o tipo especificado.
        
        Formato: logs/{tipo_log}/{tipo_log}_2025-11-02.log
        
        Args:
            tipo_log: Tipo de log (spot, futures, ia, system, banco, sinais, erros, warnings, critical, padroes)
            
        Returns:
            Path: Caminho completo do arquivo de log
        """
        data_atual = datetime.now(self.timezone_sp).strftime("%Y-%m-%d")
        nome_arquivo = f"{tipo_log}_{data_atual}.log"
        diretorio = self.base_path / tipo_log
        
        # Garante que o diretório existe
        diretorio.mkdir(parents=True, exist_ok=True)
        
        arquivo_log = diretorio / nome_arquivo
        
        # Garante que o arquivo existe (cria se não existir) e escreve uma linha inicial
        if not arquivo_log.exists():
            arquivo_log.touch()
            # Escreve linha inicial para garantir que o arquivo seja criado
            try:
                with open(arquivo_log, 'a', encoding='utf-8') as f:
                    data_hora = datetime.now(self.timezone_sp).strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{data_hora} BRT] [GerenciadorLog] [INFO] [gerenciador_log.py:237] Arquivo de log '{tipo_log}' criado\n")
                    f.flush()
            except Exception:
                pass  # Ignora erro na criação inicial
        
        return arquivo_log

    def log_evento(
        self,
        tipo_log: str,
        nome_origem: str,
        tipo_evento: str,
        mensagem: str,
        detalhes: Optional[Dict[str, Any]] = None,
        nivel: int = logging.INFO,
        par: Optional[str] = None,
    ):
        """
        Registra um evento estruturado no log.
        
        Método principal para logging estruturado e conversacional.
        
        Args:
            tipo_log: Tipo de log (spot, futures, ia, system)
            nome_origem: Nome do módulo/plugin/componente
            tipo_evento: Tipo do evento (inicializacao, execucao, decisao, ordem, erro, etc.)
            mensagem: Mensagem conversacional explicando o que aconteceu e por quê
            detalhes: Dicionário com dados-chave (preço, quantidade, resultado, tempo, etc.)
            nivel: Nível de log (INFO, WARNING, ERROR)
            par: Par ou instrumento (opcional, ex: BTC/USDT)
        """
        logger = self.get_logger(nome_origem, tipo_log, nivel)
        
        # Monta mensagem estruturada
        partes = [mensagem]
        
        if par:
            partes.append(f"Par: {par}")
        
        if detalhes:
            detalhes_str = ", ".join([f"{k}: {v}" for k, v in detalhes.items()])
            partes.append(f"Detalhes: {detalhes_str}")
        
        mensagem_completa = " | ".join(partes)
        
        # Log conforme nível (garante que seja salvo no arquivo)
        if nivel == logging.ERROR:
            logger.error(f"[{tipo_evento}] {mensagem_completa}")
        elif nivel == logging.WARNING:
            # Warnings também vão para log de warnings
            logger_warning = self.get_logger(nome_origem, "warnings", nivel=logging.WARNING)
            logger_warning.warning(f"[{tipo_evento}] {mensagem_completa}")
            for handler in logger_warning.handlers:
                if hasattr(handler, 'flush'):
                    handler.flush()
            logger.warning(f"[{tipo_evento}] {mensagem_completa}")
        elif nivel == logging.CRITICAL:
            logger.critical(f"[{tipo_evento}] {mensagem_completa}")
        else:
            logger.info(f"[{tipo_evento}] {mensagem_completa}")
        
        # Força flush para garantir que o log seja escrito imediatamente
        for handler in logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()
    
    def log_categoria(
        self,
        categoria: CategoriaLog,
        nome_origem: str,
        mensagem: str,
        nivel: int = logging.INFO,
        tipo_log: str = "system",
        detalhes: Optional[Dict[str, Any]] = None,
        plugin_nome: Optional[str] = None,
    ):
        """
        Registra um log com categoria funcional.
        
        Método principal para logging por responsabilidade funcional.
        A categoria aparece como [CATEGORIA] no início da mensagem.
        
        Args:
            categoria: Categoria funcional (CORE, CONEXAO, BANCO, PLUGIN, etc.)
            nome_origem: Nome do módulo/plugin/componente
            mensagem: Mensagem do log
            nivel: Nível de log (INFO, DEBUG, WARNING, ERROR, CRITICAL)
            tipo_log: Tipo de log (system, banco, sinais, etc.) - mantém compatibilidade
            detalhes: Dicionário com dados adicionais (opcional)
            plugin_nome: Nome do plugin (para categoria PLUGIN, ex: "PluginSupertrend")
        """
        logger = self.get_logger(nome_origem, tipo_log, nivel)
        
        # Monta mensagem com categoria
        categoria_str = categoria.value
        if categoria == CategoriaLog.PLUGIN and plugin_nome:
            categoria_str = f"PLUGIN:{plugin_nome}"
        
        mensagem_com_categoria = f"[{categoria_str}] {mensagem}"
        
        # Adiciona detalhes se fornecidos
        if detalhes:
            detalhes_str = ", ".join([f"{k}: {v}" for k, v in detalhes.items()])
            mensagem_com_categoria += f" | Detalhes: {detalhes_str}"
        
        # Cria um LogRecord customizado com a categoria armazenada
        # Isso garante que o formatter possa detectar a categoria
        import logging
        frame = inspect.currentframe().f_back
        record = logging.LogRecord(
            name=logger.name,
            level=nivel,
            pathname=frame.f_code.co_filename if frame else "",
            lineno=frame.f_lineno if frame else 0,
            msg=mensagem_com_categoria,
            args=(),
            exc_info=None
        )
        # Armazena categoria no record para o formatter detectar
        record._categoria_log = categoria_str
        
        # Log conforme nível usando handle() para garantir que o formatter seja chamado
        logger.handle(record)
        
        # Força flush para garantir que o log seja escrito imediatamente
        for handler in logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()

    def log_erro_bot(
        self,
        origem: str,
        mensagem: str,
        detalhes: Optional[Dict[str, Any]] = None,
        exc_info: bool = False
    ):
        """
        Log específico para erros do bot - mais detalhado e claro.
        
        Args:
            origem: Módulo/plugin onde ocorreu o erro
            mensagem: Mensagem clara descrevendo o erro
            detalhes: Dicionário com informações adicionais (par, timeframe, valores, etc)
            exc_info: Se True, inclui stack trace completo
        """
        logger = self.get_logger(f"{origem}_ERROR", "erros", nivel=logging.ERROR)
        
        # Monta mensagem detalhada
        msg_completa = f"[{origem}] ERRO: {mensagem}"
        
        if detalhes:
            detalhes_str = ", ".join([f"{k}={v}" for k, v in detalhes.items()])
            msg_completa += f" | Detalhes: {detalhes_str}"
        
        if exc_info:
            logger.error(msg_completa, exc_info=True)
        else:
            logger.error(msg_completa)
        
        # Força flush para garantir que o erro seja escrito imediatamente
        for handler in logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()
    
    def log_erro_critico(
        self, 
        plugin_name: str, 
        mensagem: str, 
        exc_info: bool = True,
        detalhes: Optional[Dict[str, Any]] = None
    ):
        """
        Registra um erro crítico no log de sistema.
        
        Args:
            plugin_name: Nome do plugin/componente que gerou o erro
            mensagem: Mensagem de erro descritiva
            exc_info: Se True, inclui stack trace completo
            detalhes: Dicionário com detalhes adicionais (opcional)
        """
        logger = self.get_logger("ERROS_SISTEMA", "critical", logging.CRITICAL)
        
        mensagem_completa = mensagem
        if detalhes:
            detalhes_str = ", ".join([f"{k}: {v}" for k, v in detalhes.items()])
            mensagem_completa = f"{mensagem} | Detalhes: {detalhes_str}"
        
        logger.critical(
            f"[{plugin_name}] [ERRO_CRITICO] {mensagem_completa}",
            exc_info=exc_info
        )
        
        # Força flush para garantir que o log crítico seja escrito imediatamente
        for handler in logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()

    def log_inicializacao(self, componente: str, sucesso: bool, detalhes: Optional[Dict[str, Any]] = None):
        """
        Registra inicialização de componente.
        
        Args:
            componente: Nome do componente inicializado
            sucesso: Se inicialização foi bem-sucedida
            detalhes: Detalhes adicionais (opcional)
        """
        if sucesso:
            self.log_evento(
                tipo_log="system",
                nome_origem=componente,
                tipo_evento="inicializacao",
                mensagem=f"Iniciando {componente}",
                detalhes=detalhes,
                nivel=logging.INFO
            )
        else:
            self.log_evento(
                tipo_log="system",
                nome_origem=componente,
                tipo_evento="inicializacao",
                mensagem=f"Falha ao inicializar {componente}",
                detalhes=detalhes,
                nivel=logging.ERROR
            )

    def log_ordem(
        self,
        par: str,
        acao: str,
        tipo_ordem: str,
        quantidade: Optional[float] = None,
        preco: Optional[float] = None,
        resultado: Optional[str] = None,
        detalhes: Optional[Dict[str, Any]] = None,
    ):
        """
        Registra envio/execução de ordem.
        
        Args:
            par: Par ou instrumento (ex: BTCUSDT)
            acao: Ação (enviada, executada, cancelada, rejeitada)
            tipo_ordem: Tipo (LONG, SHORT, MARKET, LIMIT, etc.)
            quantidade: Quantidade negociada
            preco: Preço de execução
            resultado: Resultado (sucesso, falha, etc.)
            detalhes: Detalhes adicionais (alavancagem, SL, TP, etc.)
        """
        # Determina tipo_log baseado no tipo de ordem
        tipo_log = "futures" if "PERP" in par.upper() or "FUTURES" in tipo_ordem.upper() else "spot"
        
        mensagem = f"Ordem {tipo_ordem} {acao} para {par}"
        if quantidade and preco:
            mensagem += f": qty {quantidade}, preço {preco}"
        
        if resultado:
            mensagem += f". Resultado: {resultado}"
        
        if not detalhes:
            detalhes = {}
        if quantidade:
            detalhes["quantidade"] = quantidade
        if preco:
            detalhes["preco"] = preco
        
        self.log_evento(
            tipo_log=tipo_log,
            nome_origem="GerenciadorBot",
            tipo_evento="ordem",
            mensagem=mensagem,
            detalhes=detalhes,
            nivel=logging.INFO,
            par=par
        )

    def log_decisao(
        self,
        par: str,
        decisao: str,
        motivo: str,
        contagem_indicadores: Optional[int] = None,
        detalhes: Optional[Dict[str, Any]] = None,
    ):
        """
        Registra decisão de estratégia.
        
        Args:
            par: Par ou instrumento
            decisao: Decisão (abrir, fechar, ignorar)
            motivo: Motivo da decisão
            contagem_indicadores: Contagem de indicadores (ex: 6/8)
            detalhes: Detalhes adicionais (SL calculado, TP, etc.)
        """
        mensagem = f"Decisão: {decisao} para {par}. Motivo: {motivo}"
        if contagem_indicadores is not None:
            mensagem += f" (Confluência {contagem_indicadores}/8)"
        
        if not detalhes:
            detalhes = {}
        if contagem_indicadores is not None:
            detalhes["contagem_indicadores"] = f"{contagem_indicadores}/8"
        
        tipo_log = "futures"  # Assumindo futuros por padrão, pode ser ajustado
        
        self.log_evento(
            tipo_log=tipo_log,
            nome_origem="GerenciadorBot",
            tipo_evento="decisao",
            mensagem=mensagem,
            detalhes=detalhes,
            nivel=logging.INFO,
            par=par
        )

    def log_ia(
        self,
        par: Optional[str],
        tipo_analise: str,
        resumo: str,
        sugestao: Optional[str] = None,
        detalhes: Optional[Dict[str, Any]] = None,
    ):
        """
        Registra análise/sugestão da IA (Llama).
        
        Args:
            par: Par analisado (opcional)
            tipo_analise: Tipo (tendencia, divergencia, padrao, etc.)
            resumo: Resumo da análise
            sugestao: Sugestão da IA (opcional)
            detalhes: Detalhes adicionais
        """
        mensagem = f"IA ({tipo_analise}): {resumo}"
        if sugestao:
            mensagem += f" | Sugestão: {sugestao}"
        
        self.log_evento(
            tipo_log="ia",
                        nome_origem="PluginIA",
            tipo_evento="analise_ia",
            mensagem=mensagem,
            detalhes=detalhes,
            nivel=logging.INFO,
            par=par
        )
    
    def log_padrao_detectado(
        self,
        nome_padrao: str,
        moeda: str,
        timeframe: str,
        direcao: str,
        score: Optional[float] = None,
        confidence: Optional[float] = None,
        porcentagem_sucesso: Optional[float] = None,
        detalhes: Optional[Dict[str, Any]] = None,
    ):
        """
        Registra um padrão detectado no log.
        
        Args:
            nome_padrao: Nome do padrão detectado (ex: "Engulfing", "Head and Shoulders")
            moeda: Símbolo da moeda (ex: "BTCUSDT", "ETHUSDT")
            timeframe: Timeframe do padrão (ex: "15m", "1h", "4h")
            direcao: Direção do padrão ("LONG" ou "SHORT")
            score: Score do padrão (0.0 a 1.0, opcional)
            confidence: Confidence do padrão (0.0 a 1.0, opcional)
            porcentagem_sucesso: Porcentagem de sucesso do padrão (futuro, opcional)
            detalhes: Detalhes adicionais (opcional)
        """
        partes = [f"Padrão detectado: {nome_padrao}"]
        partes.append(f"Moeda: {moeda}")
        partes.append(f"Timeframe: {timeframe}")
        partes.append(f"Direção: {direcao}")
        
        if score is not None:
            partes.append(f"Score: {score:.4f}")
        if confidence is not None:
            partes.append(f"Confidence: {confidence:.4f}")
        if porcentagem_sucesso is not None:
            partes.append(f"Sucesso: {porcentagem_sucesso:.2f}%")
        
        mensagem = " | ".join(partes)
        
        if detalhes:
            detalhes_str = ", ".join([f"{k}: {v}" for k, v in detalhes.items()])
            mensagem += f" | Detalhes: {detalhes_str}"
        
        logger = self.get_logger("PluginPadroes", "padroes", nivel=logging.INFO)
        logger.info(mensagem)
        for handler in logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()
    
    def log_sinal(
        self,
        moeda: str,
        tipo_sinal: str,
        direcao: str,
        timeframe: Optional[str] = None,
        preco: Optional[float] = None,
        quantidade: Optional[float] = None,
        detalhes: Optional[Dict[str, Any]] = None,
    ):
        """
        Registra um sinal de trading no log.
        
        Args:
            moeda: Símbolo da moeda (ex: "BTCUSDT", "ETHUSDT")
            tipo_sinal: Tipo de sinal (ex: "ENTRADA", "SAIDA", "STOP_LOSS", "TAKE_PROFIT")
            direcao: Direção do sinal ("LONG" ou "SHORT")
            timeframe: Timeframe do sinal (opcional)
            preco: Preço do sinal (opcional)
            quantidade: Quantidade do sinal (opcional)
            detalhes: Detalhes adicionais (opcional)
        """
        partes = [f"Sinal: {tipo_sinal}"]
        partes.append(f"Moeda: {moeda}")
        partes.append(f"Direção: {direcao}")
        
        if timeframe:
            partes.append(f"Timeframe: {timeframe}")
        if preco is not None:
            partes.append(f"Preço: {preco:.8f}")
        if quantidade is not None:
            partes.append(f"Quantidade: {quantidade:.8f}")
        
        mensagem = " | ".join(partes)
        
        if detalhes:
            detalhes_str = ", ".join([f"{k}: {v}" for k, v in detalhes.items()])
            mensagem += f" | Detalhes: {detalhes_str}"
        
        logger = self.get_logger("GerenciadorBot", "sinais", nivel=logging.INFO)
        logger.info(mensagem)
        for handler in logger.handlers:
            if hasattr(handler, 'flush'):
                handler.flush()

    def _limpar_logs_antigos(self):
        """
        Limpa logs antigos conforme política de retenção.
        
        - Mantém últimos N dias ativos (retencao_dias)
        - Compacta logs mais antigos que retencao_arquivo_dias
        - Remove logs compactados muito antigos
        """
        agora = datetime.now(self.timezone_sp)
        
        for tipo_log in ["spot", "futures", "ia", "system", "banco", "sinais", "erros", "warnings", "critical", "padroes"]:
            diretorio = self.base_path / tipo_log
            if not diretorio.exists():
                continue
            
            for arquivo in diretorio.iterdir():
                if not arquivo.is_file():
                    continue
                
                # Ignora arquivos compactados e backups
                if arquivo.suffix in [".gz", ".zip"]:
                    continue
                if ".log." in arquivo.name:  # Backups do RotatingFileHandler
                    continue
                
                # Extrai data do nome do arquivo (formato: {tipo_log}_2025-11-02.log)
                try:
                    nome_base = arquivo.stem  # Remove .log
                    # Remove o prefixo do tipo de log (ex: "system_2025-11-02" -> "2025-11-02")
                    if "_" in nome_base:
                        # Formato novo: {tipo_log}_YYYY-MM-DD
                        partes = nome_base.split("_", 1)
                        if len(partes) == 2 and len(partes[1]) == 10:  # Verifica se tem formato de data
                            data_str = partes[1]
                        else:
                            # Formato antigo: YYYY-MM-DD (compatibilidade)
                            data_str = nome_base
                    else:
                        # Formato antigo: YYYY-MM-DD (compatibilidade)
                        data_str = nome_base
                    
                    data_naive = datetime.strptime(data_str, "%Y-%m-%d")
                    data_arquivo = self.timezone_sp.localize(data_naive)
                    dias_diferenca = (agora - data_arquivo).days
                    
                    # Se mais antigo que retencao_dias, compacta ou remove
                    if dias_diferenca > self.retencao_arquivo_dias:
                        # Compacta
                        with open(arquivo, 'rb') as f_in:
                            arquivo_gz = arquivo.with_suffix('.log.gz')
                            with gzip.open(arquivo_gz, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        arquivo.unlink()
                        self.loggers.get("SYSTEM_system", logging.getLogger("SYSTEM")).info(
                            f"Log compactado: {arquivo.name} → {arquivo_gz.name}"
                        )
                    elif dias_diferenca > self.retencao_dias:
                        # Remove logs muito antigos (mais de retencao_dias dias)
                        arquivo.unlink()
                        
                except (ValueError, AttributeError):
                    # Se não conseguir parsear a data, mantém o arquivo
                    pass
