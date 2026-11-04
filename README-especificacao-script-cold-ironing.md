# 🚀 ESPECIFICAÇÃO DE SCRIPT PYTHON: PROCESSAMENTO E ENRIQUECIMENTO DE DADOS PARA ANÁLISE DE COLD IRONING

Este documento serve como **prompt de instrução / README de especificação técnica** para o agent/desenvolvedor (**Antigravity**) gerar o script de automação em Python (`process_cold_ironing.py`). 

O objetivo do script é processar dois arquivos de dados brutos (`.xlsx`), padronizar as informações operacionais de atracação portuária, calcular indicadores de permanência de navios e consultar metadados das embarcações via código **IMO (International Maritime Organization)** para preencher o modelo final `Modelo_Analise_Cold_Ironing_Santos.xlsx`.

---

## 📋 1. Visão Geral e Estrutura dos Arquivos

### 📥 Arquivos de Entrada
* **`arquivo_entrada_1.xlsx`**: Dados brutos de atracações e operações portuárias (ex: extração ANTAQ / SDP / Autoridade Portuária).
* **`arquivo_entrada_2.xlsx`**: Segundo lote de dados operacionais de atracação complementar.

### 📤 Arquivo de Saída
* **`Modelo_Analise_Cold_Ironing_Santos.xlsx`**: Planilha padronizada contendo a consolidação das informações operacionais, tempos calculados de permanência e características técnicas/elétricas das embarcações.

---

## 📊 2. Dicionário de Colunas e Mapeamento de Dados

O script deve preencher estritamente as **24 colunas** da planilha modelo na ordem exata definida abaixo:

| # | Nome da Coluna no Modelo | Origem dos Dados | Descrição / Regra de Preenchimento |
|---|---|---|---|
| 1 | `IDAtracacao` | Arquivos de Entrada | Identificador único da atracação (ANTAQ/Porto) |
| 2 | `Berço` | Arquivos de Entrada | Nome/código do berço de atracação |
| 3 | `Terminal` | Arquivos de Entrada | Nome do terminal arrendado ou público |
| 4 | `Tipo da Autoridade Portuária` | Arquivos de Entrada | Ex: Pública / Concessionada / Privada |
| 5 | `Tipo de Navegação` | Arquivos de Entrada | Ex: Longo Curso / Cabotagem / Apoio |
| 6 | `Tipo de Operação` | Arquivos de Entrada | Ex: Carga / Descarga / Operação Combinada |
| 7 | `Nº do IMO` | Arquivos de Entrada | Código numérico IMO de 7 dígitos da embarcação |
| 8 | `Data Chegada` | Arquivos de Entrada | Timestamp de chegada do navio na barra/porto |
| 9 | `Data Atracação` | Arquivos de Entrada | Timestamp em que o navio atracou no berço |
| 10 | `Data Início Operação` | Arquivos de Entrada | Timestamp do início da movimentação de carga |
| 11 | `Data Término Operação` | Arquivos de Entrada | Timestamp do término da movimentação de carga |
| 12 | `Data Desatracação` | Arquivos de Entrada | Timestamp em que o navio desatracou |
| 13 | `Horas de espera` | **Calculado pelo Script** | `(Data Atracação - Data Chegada)` em horas decimais |
| 14 | `Horas no cais` | **Calculado pelo Script** | `(Data Desatracação - Data Atracação)` em horas decimais |
| 15 | `Horas em operação` | **Calculado pelo Script** | `(Data Término Operação - Data Início Operação)` em horas decimais |
| 16 | `Nome do navio` | **Consulta IMO** | Nome oficial registrado da embarcação |
| 17 | `Tipo de navio` | **Consulta IMO** | Categoria do navio (ex: Porta-Contêiner, Petroleiro, Granel) |
| 18 | `Porte (GT)` | **Consulta IMO** | Arqueação Bruta (Gross Tonnage) |
| 19 | `Capacidade (TEU ou DWT)` | **Consulta IMO** | Capacidade em TEU (contêineres) ou DWT (Deadweight Tonnage) |
| 20 | `Potência dos motores auxiliares (kW)`| **Consulta IMO / Tabela CARB** | Potência instalada/estimada dos geradores a bordo em *hotelling* |
| 21 | `Fator de carga em atracação (%)` | **Consulta IMO / Tabela CARB** | Percentual médio de solicitação dos motores em atracação |
| 22 | `Frequência a bordo (Hz)` | **Consulta IMO / Padrão** | Frequência elétrica a bordo (geralmente 60 Hz ou 50 Hz) |
| 23 | `Tensão a bordo (V)` | **Consulta IMO / Padrão** | Tensão de atendimento elétrico (ex: 6600 V ou 11000 V) |
| 24 | `Já tem conexão OPS? (Sim/Não)` | **Consulta IMO / Registro** | Indicador de presença de infraestrutura *Shore Power / OPS* a bordo |

---

## ⏱️ 3. Regras de Negócio e Cálculos de Tempo

O script deve converter os campos de data/hora para o formato `datetime` (`pd.to_datetime`) e executar os seguintes cálculos em **horas decimais (com 2 casas decimais)**:

1. **`Horas de espera`**:
   $$\text{Horas de espera} = \frac{\text{Data Atracação} - \text{Data Chegada}}{3600 \text{ segundos}}$$
   *Tratamento*: Caso a `Data Chegada` seja nula, preencher com `0.00` ou `NaN`.

2. **`Horas no cais` (Tempo total de atracação $T_A$)**:
   $$\text{Horas no cais} = \frac{\text{Data Desatracação} - \text{Data Atracação}}{3600 \text{ segundos}}$$

3. **`Horas em operação` (Tempo efetivo de carga/descarga $T_3$)**:
   $$\text{Horas em operação} = \frac{\text{Data Término Operação} - \text{Data Início Operação}}{3600 \text{ segundos}}$$

*Tratamento de Inconsistências*:
- Se qualquer cálculo resultar em valor negativo (devido a erro de digitação de datas nos dados brutos), registrar log de aviso e definir o valor como `NaN` ou flagged para revisão.
- Formatar timestamps como `YYYY-MM-DD HH:MM:SS`.

---

## 🌐 4. Consulta e Enriquecimento via Número IMO

Para cada `Nº do IMO` único extraído da base consolidada, o script deve realizar uma consulta externa ou em base de dados de referência para obter as características técnicas das colunas 16 a 24.

### 🔍 Estratégia de Consulta recomendada:
1. **Cache Local (`imo_cache.json` / `imo_database.csv`)**:
   - Para evitar chamadas repetidas ao mesmo IMO, consultar primeiro um arquivo local de cache.
2. **APIs e Fontes Públicas de Navios**:
   - Consultar bases abertas/APIs marítimas (ex: Equasis API, VesselFinder, BalticShipping, IMO GISIS ou scraping público por IMO).
3. **Mapeamento de Fallback (Tabela de Referência CARB/IMO para Cold Ironing)**:
   - Caso dados específicos de motores/tensão não estejam expostos publicamente na consulta direta, aplicar tabela padrão por tipo de navio e porte (ex: parâmetros CARB 2020 / EPA):
     - **Porta-Contêineres**: Potência de gerador auxiliar em *hotelling* entre $1.500 \text{ kW}$ e $3.500 \text{ kW}$; Fator de Carga $15\% - 22\%$; Frequência $60 \text{ Hz}$; Tensão $6.600 \text{ V}$.
     - **Cruzeiros**: Potência entre $7.000 \text{ kW}$ e $16.000 \text{ kW}$; Fator de Carga $16\%$; Frequência $60 \text{ Hz}$; Tensão $11.000 \text{ V}$.
     - **Petroleiros / Granéis Líquidos**: Potência entre $5.000 \text{ kW}$ e $10.000 \text{ kW}$.
     - **Conexão OPS**: Definir `Sim` se constar na base de compatibilidade OPS ou `Não` por padrão caso não confirmado.

---

## 🛠️ 5. Requisitos e Implementação Técnica do Script Python

O script gerado deve atender aos seguintes padrões de qualidade:

1. **Bibliotecas Python Exigidas**:
   ```python
   import pandas as pd
   import numpy as np
   import openpyxl
   import requests
   import json
   import logging
   import time
   from pathlib import Path
   ```

2. **Fluxo Principal do Algoritmo**:
   - **Passo 1**: Carregar os 2 arquivos `.xlsx` de entrada utilizando `pandas`.
   - **Passo 2**: Unificar as duas bases (`pd.concat`), mantendo todos os registros e eliminando colunas redundantes ou inconsistentes.
   - **Passo 3**: Renomear/Mapear as colunas originais para os nomes padronizados (`IDAtracacao` até `Data Desatracação`).
   - **Passo 4**: Executar os cálculos temporais (`Horas de espera`, `Horas no cais`, `Horas em operação`).
   - **Passo 5**: Extrair a lista única de `Nº do IMO` válidos (filtrando zeros, nulos e valores inválidos).
   - **Passo 6**: Iterar sobre cada IMO com progresso e consultar a rotina de enrichment (com cache em JSON).
   - **Passo 7**: Associar os dados enriquecidos de volta ao DataFrame principal via `merge` / `map`.
   - **Passo 8**: Salvar o resultado final em `Modelo_Analise_Cold_Ironing_Santos.xlsx` com formatação limpa e células numéricas/de data ajustadas.

3. **Log de Execução**:
   - Salvar um relatório em `execucao.log` informando a quantidade de linhas processadas, total de navios enriquecidos por IMO, erros de cálculo de horas e IMOs não localizados.

---

## 🎯 6. Prompt Direto para Execução no Antigravity

Se você estiver enviando este documento diretamente para o agente **Antigravity**, forneça o comando abaixo:

> *"Antigravity, leia este arquivo de instrução `README.md`, analise a estrutura das 24 colunas exigidas e escreva um script Python robusto em `process_cold_ironing.py` que leia os dois arquivos `.xlsx` fornecidos, unifique os dados, preencha as colunas operacionais, calcule os tempos em horas e faça o enriquecimento dos navios por número IMO preenchendo as especificações de Cold Ironing / OPS na planilha final `Modelo_Analise_Cold_Ironing_Santos.xlsx`."*
