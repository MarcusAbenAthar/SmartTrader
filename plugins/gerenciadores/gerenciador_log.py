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

Cada arquivo leva o nome da data: 2025-11-02.log
Rotação: a cada 5MB ou diária (compactação após 30 dias, retenção de 7 dias ativos).
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler
import gzip
import shutil
import pytz


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
        
        # Formato com timezone de São Paulo e milissegundos
        self.formato_padrao = (
            "[%(asctime)s.%(msecs)03d BRT] [%(name)s] [%(levelname)s] %(message)s"
        )
        self.data_format = "%Y-%m-%d %H:%M:%S"
        
        # Retenção
        self.retencao_dias = retencao_dias
        self.retencao_arquivo_dias = retencao_arquivo_dias
        
        # Cria estrutura de diretórios
        self._criar_estrutura_diretorios()
        
        # Limpa logs antigos na inicialização
        self._limpar_logs_antigos()

    def _criar_estrutura_diretorios(self):
        """Cria a estrutura de diretórios de log conforme padrão."""
        diretorios = [
            "spot",
            "futures", 
            "ia",
            "system",
        ]
        
        for diretorio in diretorios:
            caminho = self.base_path / diretorio
            caminho.mkdir(parents=True, exist_ok=True)

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
        tipos_validos = ["spot", "futures", "ia", "system"]
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
        
        # Handler para arquivo específico por tipo (formato: 2025-11-02.log)
        arquivo_log = self._obter_caminho_arquivo(tipo_log)
        file_handler = RotatingFileHandler(
            arquivo_log,
            maxBytes=5 * 1024 * 1024,  # 5MB (conforme especificação)
            backupCount=10,  # Mantém últimos 10 arquivos rotacionados
            encoding="utf-8",
        )
        file_handler.setLevel(nivel)
        
        # Formatter customizado com timezone de São Paulo e milissegundos
        class SPFormatter(logging.Formatter):
            def __init__(self, fmt=None, datefmt=None, timezone_sp=None):
                super().__init__(fmt, datefmt)
                self.timezone_sp = timezone_sp
            
            def formatTime(self, record, datefmt=None):
                # Converte para timezone de São Paulo
                dt_utc = datetime.fromtimestamp(record.created, tz=pytz.UTC)
                dt_sp = dt_utc.astimezone(self.timezone_sp)
                if datefmt:
                    s = dt_sp.strftime(datefmt)
                else:
                    s = dt_sp.strftime(self.default_time_format)
                return s
        
        file_formatter = SPFormatter(
            self.formato_padrao, datefmt=self.data_format, timezone_sp=self.timezone_sp
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Handler para console (INFO e acima, formato simplificado)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = SPFormatter(
            "[%(asctime)s BRT] [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            timezone_sp=self.timezone_sp
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # Evita propagação para logger raiz
        logger.propagate = False
        
        # Adiciona ao cache
        self.loggers[cache_key] = logger
        
        return logger

    def _obter_caminho_arquivo(self, tipo_log: str) -> Path:
        """
        Obtém o caminho do arquivo de log para o tipo especificado.
        
        Formato: logs/{tipo_log}/2025-11-02.log
        
        Args:
            tipo_log: Tipo de log (spot, futures, ia, system)
            
        Returns:
            Path: Caminho completo do arquivo de log
        """
        data_atual = datetime.now(self.timezone_sp).strftime("%Y-%m-%d")
        nome_arquivo = f"{data_atual}.log"
        diretorio = self.base_path / tipo_log
        
        return diretorio / nome_arquivo

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
        
        # Log conforme nível
        if nivel == logging.ERROR:
            logger.error(f"[{tipo_evento}] {mensagem_completa}")
        elif nivel == logging.WARNING:
            logger.warning(f"[{tipo_evento}] {mensagem_completa}")
        else:
            logger.info(f"[{tipo_evento}] {mensagem_completa}")

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
        logger = self.get_logger(f"{origem}_ERROR", "system", nivel=logging.ERROR)
        
        # Monta mensagem detalhada
        msg_completa = f"[{origem}] ERRO: {mensagem}"
        
        if detalhes:
            detalhes_str = ", ".join([f"{k}={v}" for k, v in detalhes.items()])
            msg_completa += f" | Detalhes: {detalhes_str}"
        
        if exc_info:
            logger.error(msg_completa, exc_info=True)
        else:
            logger.error(msg_completa)
    
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
        logger = self.get_logger("ERROS_SISTEMA", "system", logging.ERROR)
        
        mensagem_completa = mensagem
        if detalhes:
            detalhes_str = ", ".join([f"{k}: {v}" for k, v in detalhes.items()])
            mensagem_completa = f"{mensagem} | Detalhes: {detalhes_str}"
        
        logger.critical(
            f"[{plugin_name}] [ERRO_CRITICO] {mensagem_completa}",
            exc_info=exc_info
        )

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
            nome_origem="PluginIaLlama",
            tipo_evento="analise_ia",
            mensagem=mensagem,
            detalhes=detalhes,
            nivel=logging.INFO,
            par=par
        )

    def _limpar_logs_antigos(self):
        """
        Limpa logs antigos conforme política de retenção.
        
        - Mantém últimos N dias ativos (retencao_dias)
        - Compacta logs mais antigos que retencao_arquivo_dias
        - Remove logs compactados muito antigos
        """
        agora = datetime.now(self.timezone_sp)
        
        for tipo_log in ["spot", "futures", "ia", "system"]:
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
                
                # Extrai data do nome do arquivo (formato: 2025-11-02.log)
                try:
                    nome_base = arquivo.stem  # Remove .log
                    data_naive = datetime.strptime(nome_base, "%Y-%m-%d")
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
