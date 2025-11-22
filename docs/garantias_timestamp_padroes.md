# Garantias de Timestamp para Padrões Detectados

## ⚠️ Problemas Identificados e Soluções

### 1. Comparação String vs DateTime
**Problema:** Se em algum ponto entrar uma string sem normalizar → filtro quebra e deixa passar duplicata.

**Solução Implementada:**
- ✅ Função centralizada `normalizar_open_time_utc()` que normaliza TODOS os formatos para `datetime UTC`
- ✅ Usada em TODOS os pontos críticos:
  - Preparação de dados para inserção
  - Verificação de padrões já persistidos
  - Filtro de padrões da última vela nova
- ✅ Garante que comparações sempre usam `datetime` (nunca string)

### 2. Timezone Inconsistente
**Problema:** Se um plugin salva em UTC e outro em timestamp local → mesma vela, open_times diferentes → padrão duplicado.

**Solução Implementada:**
- ✅ Função `normalizar_open_time_utc()` sempre converte para UTC timezone-aware
- ✅ Método `_velas_para_dataframe()` garante que todos os datetimes sejam UTC
- ✅ Constraint UNIQUE no banco usa `open_time` normalizado (PostgreSQL TIMESTAMP com timezone)
- ✅ NUNCA mistura formatos - sempre UTC datetime

### 3. Exchange Corrigindo Candle Retroativamente
**Problema:** A vela das 10:00 pode ser atualizada às 10:30. Se não tiver lógica para lidar com reescrita, vai catalogar padrões em uma vela que nem existe mais.

**Solução Implementada:**
- ✅ Upsert com `ON CONFLICT DO UPDATE` na tabela `padroes_detectados`
- ✅ Atualiza padrão se vela for atualizada retroativamente
- ✅ Método `_inserir_padroes_detectados()` específico com lógica de upsert
- ✅ Atualiza apenas se score, final_score ou direção mudarem (evita updates desnecessários)

### 4. Usar open_time da Exchange (Não Calcular)
**Problema:** Se calcular open_time em vez de usar o timestamp da exchange, pode haver inconsistências.

**Solução Implementada:**
- ✅ Método `_velas_para_dataframe()` preserva timestamp original da exchange
- ✅ Se datetime não existir, cria a partir do timestamp (não calcula)
- ✅ Padrões sempre usam `ultima["datetime"]` que vem do timestamp da exchange
- ✅ Documentação clara: "CRÍTICO: open_time deve sempre vir do timestamp da exchange"

---

## Função Centralizada de Normalização

```python
def normalizar_open_time_utc(open_time: Union[str, int, float, datetime, pd.Timestamp]) -> datetime:
    """
    Normaliza open_time para datetime UTC de forma consistente.
    
    CRÍTICO: Esta função garante que TODOS os open_times sejam normalizados
    da mesma forma, evitando problemas de:
    - Comparação string vs datetime
    - Timezone inconsistente (UTC vs local)
    - Formatos diferentes (timestamp vs string)
    
    REGRA DE OURO: Sempre usa open_time da exchange (não calcula).
    """
```

**Suporta:**
- ✅ `datetime` (com ou sem timezone) → converte para UTC
- ✅ `pd.Timestamp` → converte para UTC datetime
- ✅ `str` (ISO format) → parseia e converte para UTC
- ✅ `int/float` (timestamp) → detecta milissegundos/segundos e converte para UTC

---

## Constraint UNIQUE no Banco

```sql
CONSTRAINT unique_padrao UNIQUE (symbol, timeframe, open_time, tipo_padrao)
```

**Garante:**
- ✅ Não há duplicatas mesmo se verificação em memória falhar
- ✅ open_time é comparado como TIMESTAMP (timezone-aware)
- ✅ Segurança final contra duplicatas

---

## Upsert para Atualizações de Velas

```sql
ON CONFLICT (symbol, timeframe, open_time, tipo_padrao)
DO UPDATE SET
    direcao = EXCLUDED.direcao,
    score = EXCLUDED.score,
    confidence = EXCLUDED.confidence,
    regime = EXCLUDED.regime,
    suggested_sl = EXCLUDED.suggested_sl,
    suggested_tp = EXCLUDED.suggested_tp,
    final_score = EXCLUDED.final_score,
    meta = EXCLUDED.meta
WHERE padroes_detectados.score != EXCLUDED.score
   OR padroes_detectados.final_score != EXCLUDED.final_score
   OR padroes_detectados.direcao != EXCLUDED.direcao;
```

**Lida com:**
- ✅ Exchange atualizando vela retroativamente → padrão é atualizado
- ✅ Padrão duplicado na mesma execução → não insere duplicata
- ✅ Atualiza apenas se houver mudança real (evita updates desnecessários)

---

## Fluxo Completo de Garantias

1. **PluginDadosVelas** → Obtém velas da exchange com timestamp original
2. **PluginPadroes._velas_para_dataframe()** → Preserva timestamp, normaliza datetime para UTC
3. **Padrões detectados** → Usam `ultima["datetime"]` (UTC da exchange)
4. **normalizar_open_time_utc()** → Normaliza antes de persistir
5. **Verificação em memória** → Compara padrões normalizados (mesma vela)
6. **Upsert no banco** → Atualiza se vela mudou, insere se novo
7. **Constraint UNIQUE** → Segurança final contra duplicatas

---

## Checklist de Garantias

- ✅ Normalização centralizada de timestamps
- ✅ Timezone UTC consistente em todos os pontos
- ✅ Constraint UNIQUE bem montada
- ✅ Não mistura formatos em nenhum ponto
- ✅ Sempre usa open_time da exchange (não calcula)
- ✅ Upsert para lidar com atualizações de velas
- ✅ Verificação em memória otimizada
- ✅ Logs informativos sobre padrões filtrados

---

**Última atualização:** 22/11/2025  
**Versão:** v1.5.0

