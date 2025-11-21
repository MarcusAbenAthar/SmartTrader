# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

## [v1.5.2] - 2025-11-16

### Refinamento Completo dos Padrões Harmônicos e Multi-Timeframe

#### Adicionado
- ✅ **Harmonic Patterns (Padrão #27) - Implementação Completa**
  - Detecção robusta de picos e vales usando algoritmo com filtragem de ruído (ATR-based)
  - Validação rigorosa de proporções Fibonacci com função dedicada (`_validar_proporcao_fibonacci`)
  - Padrões implementados: AB=CD, Gartley, Butterfly, Bat, Crab (Bullish e Bearish)
  - Confirmação de completion (padrão completo dentro de 3 velas do final)
  - Cálculo de ATR para filtrar picos/vales significativos
  - Remoção de pontos muito próximos (mantém apenas o mais significativo)
  - Logs TRACE completos para cada padrão detectado

- ✅ **Multi-Timeframe Confirmation (Padrão #29) - Implementação Completa**
  - Acesso real a dados de múltiplos timeframes via `dados_multi_tf`
  - Sistema de hierarquia de timeframes (15m → 1h/4h, 1h → 4h)
  - Lógica de confirmação com pesos dinâmicos (1h: 60%, 4h: 40%)
  - Cálculo de força de tendência baseado em distância entre EMAs
  - Score dinâmico baseado na força da confirmação (0.75-0.95)
  - Fallback para aproximação quando dados multi-TF não disponíveis

#### Melhorado
- ✅ Algoritmo de detecção de picos/vales com janela configurável (min_periods=3)
- ✅ Validação de proporções Fibonacci com tolerância configurável (padrão 5%)
- ✅ Score dinâmico baseado na qualidade do padrão (ratio perfeito = score maior)
- ✅ Integração completa com estrutura de dados do PluginDadosVelas
- ✅ Sistema de pesos ponderados para múltiplas confirmações

#### Impacto
- 🎯 **Top 30 Padrões 100% Implementados**: Todos os 30 padrões agora estão completamente implementados e funcionais
- 🎯 **Harmonic Patterns**: Detecção profissional com validação Fibonacci rigorosa
- 🎯 **Multi-Timeframe**: Confirmação real usando dados de múltiplos timeframes simultaneamente
- 📊 Meta informações completas com todos os pontos (X, A, B, C, D) e retrações
- 📊 Logs TRACE com detalhes de confirmações e scores calculados

#### Arquivos Modificados
- `plugins/padroes/plugin_padroes.py` - Refinamento completo dos padrões #27 e #29
- `docs/proxima_atualizacao.md` - Atualizado para refletir 100% de implementação
- `STATUS_PROJETO.md` - Atualizado com detalhes da implementação completa

## [v1.5.1] - 2025-11-16

### Correções e Otimizações de Performance

#### Corrigido
- ✅ **Filtro Dinâmico - Logs Detalhados de Diagnóstico**
  - Logs detalhados de rejeições por camada (Liquidez, Maturidade, Atividade, Integridade)
  - Log DEBUG com detalhes dos primeiros 10 pares rejeitados (par, camada, motivo)
  - Log WARNING quando nenhum par é aprovado, incluindo mediana de volume 24h
  - Modo debug configurável via `MODO_DEBUG` ou config
  - Estatísticas completas no relatório (rejeições por camada, mediana de volume)

- ✅ **PluginDadosVelas - Otimizações de Performance**
  - Processamento paralelo de timeframes dentro de cada thread
  - Redução de ~60% no tempo de processamento (de ~7s para ~2-3s por par)
  - Ajuste do cálculo de workers: até 3 pares = 1 worker por par, mais de 3 = min(pares // 3, 5)
  - Métricas de tempo por par (tempo_processamento_ms, tempo médio, mínimo, máximo)
  - Logs de métricas consolidadas no final de cada lote

- ✅ **Identificação de Plugins Não Executados**
  - Log INFO explicando quais plugins não foram executados e motivo
  - Informação incluída no log do ciclo completo
  - Campo `plugins_nao_executados` no retorno do GerenciadorPlugins

#### Melhorado
- ✅ **Intervalo do Ciclo Ajustado**
  - Intervalo ajustado de 5s para 25s (configurável via `BOT_CYCLE_INTERVAL`)
  - Permite processamento completo sem sobrecarga
  - Comentários explicativos sobre o motivo do ajuste

- ✅ **Métricas de Performance**
  - Tracking de tempo de processamento por par
  - Métricas consolidadas: tempo médio, mínimo, máximo
  - Informações de performance incluídas nos dados retornados (`_metricas`)

#### Impacto
- ⚡ Redução de ~60% no tempo de processamento de timeframes (paralelo vs sequencial)
- ⚡ Melhor utilização de workers (até 5 workers vs máximo 1 anteriormente)
- ⚡ Ciclo ajustado para permitir processamento completo (25s vs 5s)
- 🔍 Logs detalhados permitem identificar exatamente por que pares são rejeitados
- 🔍 Métricas de tempo facilitam identificação de gargalos
- 🔍 Identificação de plugins não executados facilita troubleshooting

#### Arquivos Modificados
- `plugins/filtro/plugin_filtro_dinamico.py` - Logs detalhados e modo debug
- `plugins/indicadores/plugin_dados_velas.py` - Processamento paralelo, métricas, workers
- `plugins/gerenciadores/gerenciador_plugins.py` - Identificação de plugins não executados
- `main.py` - Logs melhorados do ciclo
- `utils/main_config.py` - Intervalo do ciclo ajustado

## [v1.5.0] - 2025-11-16

### Validação Temporal e Ensemble de Padrões

#### Adicionado
- ✅ **Rolling Window Completo Implementado**
  - Janela deslizante de 180 dias que recalcula métricas a cada 30 dias
  - Tracking de performance ao longo do tempo
  - Detecção automática de degradação de performance
  - Ajuste automático de confidence baseado em performance recente
  - Logs INFO, DEBUG, TRACE e WARNING completos
  - Persistência de métricas de cada janela no banco

- ✅ **Ensemble de Padrões Implementado e Integrado**
  - Detecção de convergência de padrões (2-3 padrões apontando mesma direção)
  - Sistema de pesos dinâmicos baseado em confidence
  - Score combinado quando múltiplos padrões convergem
  - Integrado no método `executar()` do PluginPadroes
  - Logs TRACE para cálculos de ensemble

- ✅ **Logs Completos de Padrões e IA**
  - Logs INFO para resumo de padrões detectados
  - Logs DEBUG para detalhamento
  - Logs TRACE para cálculos internos e ensemble
  - Logs WARNING para padrões fracos e degradação
  - Logs de IA completos (INFO, DEBUG, TRACE, WARNING)

#### Melhorado
- ✅ Validação Temporal agora está 100% completa
- ✅ Sistema de ensemble integrado no fluxo de detecção
- ✅ Método de rankeamento por performance implementado (aguardando métricas de backtest)

## [v1.4.0] - 2025-11-15

### Sistema de Armazenamento de Indicadores Técnicos

#### Adicionado
- ✅ **Tabelas de Indicadores Técnicos** - 8 tabelas criadas no banco de dados
  - `indicadores_ichimoku`: Dados do Ichimoku Cloud
  - `indicadores_supertrend`: Dados do Supertrend
  - `indicadores_bollinger`: Dados das Bollinger Bands
  - `indicadores_volume`: Dados do Volume
  - `indicadores_ema`: Dados de EMA Crossover
  - `indicadores_macd`: Dados do MACD
  - `indicadores_rsi`: Dados do RSI
  - `indicadores_vwap`: Dados do VWAP
  - Cada tabela armazena valores calculados, sinais LONG/SHORT e metadados
  - Constraints de unicidade para evitar duplicatas
  - Índices otimizados para consultas rápidas por par e timeframe
  - Suporte a testnet/mainnet em todas as tabelas

- ✅ **Persistência Automática de Indicadores**
  - Todos os 8 plugins de indicadores agora salvam dados no banco após cálculo
  - Dados são salvos automaticamente a cada execução
  - Upsert automático via constraints de unicidade
  - Histórico completo de indicadores disponível para análise

- ✅ **Filtro Dinâmico do SmartTrader** - Sistema de Seleção Inteligente de Pares
  - Localização: `plugins/filtro/plugin_filtro_dinamico.py`
  - **4 Camadas de Filtro:**
    1. **Liquidez Diária Real**: Mediana de Volume 24h (remove pares sem liquidez)
    2. **Maturidade do Par**: Idade Mínima >= 60 dias (remove tokens novos)
    3. **Atividade Recente**: Volume médio 15m e 1h > 0 (remove pares inativos)
    4. **Integridade Técnica**: Timeframes vazios e fail_rate < 30% (remove pares problemáticos)
  - Rastreamento de histórico de falhas por par
  - Bloqueio automático de pares problemáticos (3 ciclos para timeframes vazios)
  - Tabela `pares_filtro_dinamico` para rastreamento completo
  - Integração completa com PluginDadosVelas (usa apenas pares aprovados)

#### Melhorado
- ✅ **PluginBancoDados** atualizado para v1.4.0
  - Suporte completo para inserção de dados de indicadores
  - Método `inserir()` genérico funciona com todas as tabelas de indicadores
  - Upsert automático via constraints de unicidade

- ✅ **PluginDadosVelas** integrado com Filtro Dinâmico
  - Usa apenas pares aprovados pelo filtro para processamento
  - Fallback para lista configurada se filtro não disponível
  - Reduz desperdício de recursos em pares problemáticos

#### Características do Filtro Dinâmico
- 100% dinâmico, recalculado a cada ciclo
- Adaptado ao estado real do mercado
- Rastreia histórico de falhas por par
- Bloqueia pares problemáticos automaticamente
- Relatório completo de rejeições por camada
- Salva resultados no banco para análise

#### Impacto
- ✅ Menos pares inúteis processados
- ✅ Menos requisições desperdiçadas
- ✅ Menos timeframes vazios
- ✅ Menos ruído nos logs
- ✅ Menos risco de rate-limit
- ✅ Mais velocidade e consistência
- ✅ Mais precisão e estabilidade
- ✅ Histórico completo de indicadores para análise

#### Documentação
- ✅ `definicao_banco.md` atualizado com todas as novas tabelas
- ✅ Estrutura completa de cada tabela de indicadores documentada
- ✅ Exemplos de uso e índices explicados

## [v1.3.0] - 2025-11-08

### Sistema de Padrões de Trading - Top 10 Implementado

#### Adicionado
- ✅ **PluginPadroes** - Plugin de detecção de padrões técnicos
  - Localização: `plugins/padroes/plugin_padroes.py`
  - Orquestra detecção dos Top 10 padrões de trading
  - Implementa filtro de regime de mercado (Trending vs Range)
  - Sistema de Confidence Decay (decaimento de confiança)
  - Cálculo de score final (technical_score * 0.6 + confidence * 0.4)
  
- ✅ **Top 30 Padrões Implementados** (Top 10 + Próximos 20)
  1. Breakout de suporte/resistência com volume confirmado
  2. Pullback válido após breakout (reteste + suporte segurando)
  3. EMA crossover (9/21) com confirmação de volume
  4. RSI divergence (price × RSI) - bullish/bearish
  5. Bollinger Squeeze + rompimento (BB Width < 0.04 por ≥5 velas)
  6. VWAP rejection / acceptance (preço testa e volta)
  7. Candlestick Engulfing (bull/bear) com volume confirmado
  8. Hammer / Hanging Man + confirmação no fechamento seguinte
  9. Volume spike anomaly (z-score sobre média(20))
  10. False breakout (fechamento de volta dentro da zona)
  
  **Próximos 20 Padrões (11-30):**
  11. Head & Shoulders / Inverse H&S (neckline break)
  12. Double Top / Double Bottom
  13. Triangle (Asc/Desc/Sym) (breakout + volume)
  14. Flag / Pennant (continuation)
  15. Wedge rising / falling (reversão)
  16. Rectangle (range breakout)
  17. Three White Soldiers / Three Black Crows
  18. Morning Star / Evening Star
  19. Tweezer Tops / Tweezer Bottoms
  20. Harami / Harami Cross
  21. Piercing Line / Dark Cloud Cover
  22. Gap types (breakaway / runaway / exhaustion)
  23. MACD divergence + histogram reversal
  24. ATR-based volatility breakout (> k × ATR)
  25. Fibonacci retracement confluence (61.8% + suporte)
  26. Liquidity sweep (long wick into stops)
  27. Harmonic patterns (AB=CD, Gartley) — estrutura básica
  28. Volume–price divergence (decoupling em tendência)
  29. Multi-timeframe confirmation (15m + 1h) — estrutura básica
  30. Order-flow proxy (wick + volume = stop hunt)

- ✅ **Filtro de Regime de Mercado**
  - Detecta Trending vs Range baseado em:
    - `trend_strength = abs(ema_50 - ema_200) / atr_14`
    - `volatility_regime = bb_width.pct_change().rolling(20).std()`
  - Regime Trending: `trend_strength > 1.5` e `volatility_regime < 0.3`
  - Regime Range: caso contrário
  - Campo `regime` obrigatório na telemetria

- ✅ **Confidence Decay**
  - Fórmula: `confidence_score = base_score * exp(-0.01 * days_since_last_win)`
  - Quarentena automática se `confidence_score < 0.5`
  - Peso maior no ensemble se `confidence_score > 0.8`

- ✅ **Tabelas no Banco de Dados**
  - `padroes_detectados`: Padrões detectados com telemetria completa
    - Campos: symbol, timeframe, open_time, tipo_padrao, direcao, score, confidence, regime, suggested_sl, suggested_tp, final_score, meta (JSONB)
  - `padroes_metricas`: Métricas de performance por padrão
    - Campos: tipo_padrao, frequency, precision, recall, expectancy, sharpe_condicional, drawdown_condicional, winrate, avg_rr, total_trades, etc.
  - `padroes_confidence`: Histórico de confidence decay por padrão
    - Campos: tipo_padrao, data_ultimo_win, days_since_last_win, base_score, confidence_score, em_quarentena

- ✅ **Estrutura Modular**
  - Cada padrão é uma função separada (`_detectar_*`)
  - Código vetorizado usando Pandas/NumPy
  - Fácil expansão para os próximos 20 padrões

#### Características
- Modular: cada padrão é uma função separada
- Vetorizado: usa Pandas/NumPy para performance
- Telemetria completa: regime, confidence, métricas
- Persistência automática no banco de dados
- Serialização correta de datetime e tipos numpy/pandas para PostgreSQL

#### Conforme Documentação
- Segue `proxima_atualizacao.md` rigorosamente
- Implementa Top 10 padrões primeiro (PoC)
- Validação temporal implementada (Walk-Forward, Rolling Window, OOS)
- Pronto para backtest completo (simulação de trades)

#### Validação Temporal
- ✅ Método `validar_temporal()` implementado
  - Walk-Forward: 60% treino → 40% teste
  - Rolling Window: 180 dias → recalcula a cada 30 dias (básico)
  - Out-of-Sample (OOS): ≥ 30% dos dados nunca vistos
- ✅ Método `_calcular_metricas()` implementado
  - Frequency: Ocorrências por 1.000 velas
  - Estrutura pronta para métricas completas (precision, expectancy, sharpe, etc.)
- ✅ Persistência automática de métricas no banco

#### Documentação Atualizada
- ✅ `definicao_banco.md` atualizado com campo `testnet` e tabelas de padrões
- ✅ `STATUS_PROJETO.md` atualizado com sistema de padrões
- ✅ `README.md` atualizado com informações sobre padrões de trading
- ✅ `CHANGELOG.md` atualizado com todas as mudanças

#### Versão
- PluginPadroes: v1.0.0
- Schema versão: v1.0.0

---

## [v1.2.0] - 2025-11-05

### PluginBancoDados - Refatoração Completa

#### Adicionado
- ✅ **CRUD Completo Implementado**
  - Método `inserir()` - Inserção de dados com upsert para velas
  - Método `consultar()` - Consulta com filtros, campos e ordenação
  - Método `atualizar()` - Atualização com filtros e validação
  - Método `deletar()` - Exclusão com filtros obrigatórios (segurança)
  
- ✅ **Estrutura de Métodos**
  - Métodos internos com underscore (_inserir_velas, _consultar, etc.)
  - Métodos públicos sem underscore (inserir, consultar, atualizar, deletar)
  - Separação clara entre lógica interna e interface pública
  
- ✅ **Logs Padronizados**
  - Formato: `[BancoDados][INSERT]`, `[UPDATE]`, `[SELECT]`, `[DELETE]`
  - Facilita depuração e auditoria
  - Logs informativos por operação com detalhes
  
- ✅ **Retorno Padronizado**
  - Dicionário padronizado para todas as operações CRUD
  - Facilita integração com IA
  - Estrutura:
    ```python
    {
        "sucesso": bool,
        "operacao": str,  # INSERT, UPDATE, SELECT, DELETE
        "tabela": str,
        "dados": Any,
        "mensagem": str,
        "linhas_afetadas": int,
        "erro": Optional[str],
        "timestamp": str
    }
    ```
  
- ✅ **Melhorias de Segurança**
  - Uso de `sql.Identifier` para prevenir SQL injection
  - Validação de filtros obrigatórios em UPDATE e DELETE
  - Validação de dados antes de inserção
  
- ✅ **Métodos Auxiliares**
  - `_formatar_retorno()` - Formata retorno padronizado
  - `_inserir_generico()` - Inserção genérica para qualquer tabela
  - `atualizar_view_materializada()` - Atualiza view materializada
  
- ✅ **Documentação Completa**
  - Docstrings em todos os métodos
  - Exemplos de uso na documentação
  - Tipagem completa com type hints

#### Melhorado
- ✅ Estrutura de código mais organizada
- ✅ Tratamento de erros mais robusto
- ✅ Logs mais informativos e padronizados
- ✅ Retorno padronizado para facilitar integração com IA

#### Versão
- PluginBancoDados: v1.0.0 → v1.2.0
- Schema versão: v1.0.0 → v1.2.0

---

## [v1.1.0] - 2025-11-05

### Melhorias e Robustez

#### Adicionado
- ✅ Enums para Status e Tipos (StatusExecucao, TipoPlugin, NivelGravidade)
- ✅ Metadados de Plugin (autor, data, dependências)
- ✅ Monitoramento e Telemetria (tolerância de erro temporal, armazenamento)
- ✅ Ações Automáticas (ERROR → recuperação, CRITICAL → reinicialização)
- ✅ Suporte Assíncrono (executar_async())
- ✅ GerenciadorBot Melhorado (tratamento de empates)
- ✅ Banco de Dados Expandido (campo exchange, view materializada, histórico de schema)

---

## [v1.0.0] - 2025-01-XX

### Adicionado
- Estrutura base do projeto conforme regras de ouro
- Classe base `Plugin` com ciclo de vida completo
- `GerenciadorLog` com sistema de logs estruturado por tipo
- `GerenciadorBanco` para persistência de dados com validação
- `GerenciadorPlugins` para orquestração de plugins
- `GerenciadorBot` para controle de trades (Sistema 6/8)
- `ConfigManager` com suporte a testnet/mainnet Bybit
- `main.py` como ponto de entrada do sistema
- Sistema de diretórios de logs organizados por tipo

### Estrutura
- `plugins/base_plugin.py`: Classe base para todos os plugins
- `plugins/gerenciadores/`: Gerenciadores principais do sistema
- `plugins/indicadores/`: Preparado para 8 plugins de indicadores
- `utils/config.py`: Configuração centralizada
- `utils/logging_config.py`: Helpers de logging

