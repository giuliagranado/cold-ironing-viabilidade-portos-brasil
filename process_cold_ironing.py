"""
Processamento e Enriquecimento de Dados para Análise de Cold Ironing (Santos e Suape)
=====================================================================================
Autor: Antigravity
Data: 2026-11-03
Descrição:
  Script em Python que consolida os dados de atracações portuárias de Santos e Suape,
  padroniza as informações de acordo com o modelo de análise de Cold Ironing / OPS,
  calcula os tempos operacionais (espera, cais, operação), enriquece os dados das
  embarcações consultando o registro IMO (via cache e bases públicas marítimas/Wikidata)
  e aplicando a tabela de referência CARB/IMO, preenchendo o arquivo final:
  'Modelo_Analise_Cold_Ironing_Santos.xlsx'.
"""

import sys
import os
import json
import time
import logging
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import pandas as pd
import numpy as np
import requests

# ---------------------------------------------------------------------------
# 1. Configuração de Logs
# ---------------------------------------------------------------------------
LOG_FILE = "execucao.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("cold_ironing")

# ---------------------------------------------------------------------------
# 2. Definição de Mapeamentos Portuários e Terminais
# ---------------------------------------------------------------------------
BERTH_TERMINAL_MAP = {
    # Santos - Alamoa / Alemoa (Granéis Líquidos / Combustíveis)
    "Al 01": ("Terminal da Alemoa (Ultracargo / Vopak / Stolthaven)", "Petroleiro / Granel Líquido"),
    "Al 02": ("Terminal da Alemoa (Ultracargo / Vopak / Stolthaven)", "Petroleiro / Granel Líquido"),
    "Al 03": ("Terminal da Alemoa (Ultracargo / Vopak / Stolthaven)", "Petroleiro / Granel Líquido"),
    "Al 04": ("Terminal da Alemoa (Ultracargo / Vopak / Stolthaven)", "Petroleiro / Granel Líquido"),
    # Santos - Ilha Barnabé (Químicos / Granéis Líquidos)
    "Ib Bc": ("Terminal da Ilha Barnabé (Ageo / Copape)", "Petroleiro / Granel Líquido"),
    "Ib Sp": ("Terminal da Ilha Barnabé (Ageo / Copape)", "Petroleiro / Granel Líquido"),
    # Santos - Guarujá (Granéis Sólidos / Contêineres)
    "Tgg": ("Terminal de Granéis do Guarujá (TGG)", "Graneleiro / Granel Sólido"),
    "Tefer": ("Terminal de Fertilizantes (TEFER)", "Graneleiro / Granel Sólido"),
    "Tecon": ("Tecon Santos (Santos Brasil)", "Porta-Contêineres"),
    "Btp": ("Brasil Terminal Portuário (BTP)", "Porta-Contêineres"),
    "Concais": ("Terminal Marítimo de Passageiros (CONCAIS)", "Cruzeiro / Passageiros"),
    # Santos - Cais Público e Corredores de Exportação
    "Arm 12a": ("Cais Público - Valongo", "Carga Geral / Granel Sólido"),
    "Arm 13/14": ("Cais Público - Valongo", "Carga Geral / Granel Sólido"),
    "Arm 15": ("Cais Público - Valongo", "Carga Geral / Granel Sólido"),
    "Arm 16/17": ("Cais Público - Paquetá", "Graneleiro / Granel Sólido"),
    "Arm 19": ("Cais Público - Paquetá", "Graneleiro / Granel Sólido"),
    "Arm 20/21": ("Cais Público - Paquetá", "Graneleiro / Granel Sólido"),
    "Armazem 23": ("Terminal Marítimo Valongo (Fertilizantes)", "Graneleiro / Granel Sólido"),
    "Arm 29": ("Cais Público - Macuco", "Graneleiro / Granel Sólido"),
    "Arm 29/30": ("Cais Público - Macuco", "Graneleiro / Granel Sólido"),
    "Arm 31": ("Cais Público - Macuco", "Graneleiro / Granel Sólido"),
    "Arm 33": ("Terminal Sucocítrico Cutrale / Citrosuco", "Petroleiro / Granel Líquido"),
    "Arm 35": ("Terminal Sucocítrico Cutrale / Citrosuco", "Petroleiro / Granel Líquido"),
    "Arm 37": ("Corredor de Exportação de Grãos", "Graneleiro / Granel Sólido"),
    "Arm 38": ("Corredor de Exportação de Grãos", "Graneleiro / Granel Sólido"),
    "Arm 39": ("Corredor de Exportação de Grãos", "Graneleiro / Granel Sólido"),
    "Arm Frig": ("Terminal Frigorífico", "Reefer / Frigorífico"),
    "Cs 01": ("Terminal Conceiçãozinha (ADM / Cargill)", "Graneleiro / Granel Sólido"),
    "Cs 02": ("Terminal Conceiçãozinha (ADM / Cargill)", "Graneleiro / Granel Sólido"),
    "Cs 03": ("Terminal Conceiçãozinha (ADM / Cargill)", "Graneleiro / Granel Sólido"),
    "Outeirinhos": ("Terminal Público de Outeirinhos", "Carga Geral / Apoio"),
    # Suape - PGL (Píer de Granéis Líquidos)
    "Pgl-1a": ("PGL Suape - Píer de Granéis Líquidos (Transpetro)", "Petroleiro / Granel Líquido"),
    "Pgl-1b": ("PGL Suape - Píer de Granéis Líquidos (Transpetro)", "Petroleiro / Granel Líquido"),
    "Pgl-2a": ("PGL Suape - Píer de Granéis Líquidos (Transpetro)", "Petroleiro / Granel Líquido"),
    "Pgl-2b": ("PGL Suape - Píer de Granéis Líquidos (Transpetro)", "Petroleiro / Granel Líquido"),
    "Pgl-3a": ("PGL Suape - Píer de Granéis Líquidos (Transpetro)", "Petroleiro / Granel Líquido"),
    "Pgl-3b": ("PGL Suape - Píer de Granéis Líquidos (Transpetro)", "Petroleiro / Granel Líquido"),
    # Suape - Cais e Múltiplo Uso
    "Cais01": ("Cais de Múltiplo Uso (CMU 1)", "Porta-Contêineres"),
    "Cais04": ("Tecon Suape (Cais 4)", "Porta-Contêineres"),
    "Cais05": ("Tecon Suape (Cais 5)", "Porta-Contêineres"),
    "Cmu-B": ("Cais de Múltiplo Uso (CMU B)", "Carga Geral / Ro-Ro"),
    "Reca": ("Cais da Refinaria / Reca", "Petroleiro / Granel Líquido"),
    "Rec-Ta": ("Recinto Alfandegado Suape", "Carga Geral")
}

def infer_terminal_and_type_from_berth(berth_str, complex_str="", nav_str="", op_str=""):
    """Infere o nome do Terminal e a categoria do navio a partir do berço e operação."""
    b_clean = str(berth_str).strip()
    term = None
    stype = None
    
    # Busca por correspondência no dicionário
    for prefix, (t_name, s_cat) in BERTH_TERMINAL_MAP.items():
        if prefix.lower() in b_clean.lower():
            term = t_name
            stype = s_cat
            break
            
    if not term:
        if "santos" in str(complex_str).lower():
            term = f"Terminal Santos ({b_clean.split('(')[0].strip()})"
        elif "suape" in str(complex_str).lower():
            term = f"Terminal Suape ({b_clean.split('(')[0].strip()})"
        else:
            term = f"Terminal Portuário ({b_clean.split('(')[0].strip()})"

    if not stype:
        if "apoio" in str(nav_str).lower():
            stype = "Apoio Marítimo / Portuário"
        elif "cont" in str(op_str).lower():
            stype = "Porta-Contêineres"
        elif "granel" in str(op_str).lower() or "quimic" in str(op_str).lower() or "petrol" in str(op_str).lower():
            stype = "Petroleiro / Granel Líquido"
        elif "exporta" in str(op_str).lower() and "santos" in str(complex_str).lower():
            stype = "Graneleiro / Granel Sólido"
        else:
            stype = "Carga Geral / Multiuso"

    return term, stype

# ---------------------------------------------------------------------------
# 3. Parâmetros CARB / IMO / EPA para Cold Ironing
# ---------------------------------------------------------------------------
CARB_SPECS = {
    "Porta-Contêineres": {
        "gt": 54000,
        "cap": 5500, # TEU
        "power_kw": 2500,
        "load_factor": 0.18, # 18%
        "freq_hz": 60,
        "voltage_v": 6600,
        "ops": "Não"
    },
    "Cruzeiro / Passageiros": {
        "gt": 95000,
        "cap": 12000, # DWT
        "power_kw": 11000,
        "load_factor": 0.16, # 16%
        "freq_hz": 60,
        "voltage_v": 11000,
        "ops": "Não"
    },
    "Petroleiro / Granel Líquido": {
        "gt": 28000,
        "cap": 45000, # DWT
        "power_kw": 6500,
        "load_factor": 0.22, # 22%
        "freq_hz": 60,
        "voltage_v": 6600,
        "ops": "Não"
    },
    "Graneleiro / Granel Sólido": {
        "gt": 38000,
        "cap": 65000, # DWT
        "power_kw": 1800,
        "load_factor": 0.20, # 20%
        "freq_hz": 60,
        "voltage_v": 440,
        "ops": "Não"
    },
    "Carga Geral / Ro-Ro": {
        "gt": 30000,
        "cap": 25000, # DWT
        "power_kw": 2200,
        "load_factor": 0.20, # 20%
        "freq_hz": 60,
        "voltage_v": 6600,
        "ops": "Não"
    },
    "Reefer / Frigorífico": {
        "gt": 12000,
        "cap": 15000, # DWT
        "power_kw": 3600,
        "load_factor": 0.30, # 30%
        "freq_hz": 60,
        "voltage_v": 6600,
        "ops": "Não"
    },
    "Apoio Marítimo / Portuário": {
        "gt": 1500,
        "cap": 2000, # DWT
        "power_kw": 800,
        "load_factor": 0.18, # 18%
        "freq_hz": 60,
        "voltage_v": 440,
        "ops": "Não"
    },
    "Carga Geral / Multiuso": {
        "gt": 25000,
        "cap": 30000, # DWT
        "power_kw": 2000,
        "load_factor": 0.20, # 20%
        "freq_hz": 60,
        "voltage_v": 440,
        "ops": "Não"
    }
}

def classify_ship_type(raw_type_str, berth_category):
    """Classifica o tipo do navio padronizado com base no texto e no berço."""
    if not raw_type_str or pd.isna(raw_type_str):
        return berth_category
    
    t = str(raw_type_str).lower()
    if any(k in t for k in ["container", "porta-cont"]):
        return "Porta-Contêineres"
    if any(k in t for k in ["cruise", "cruzeiro", "passenger"]):
        return "Cruzeiro / Passageiros"
    if any(k in t for k in ["tanker", "petrol", "chemical", "gas", "lpg", "lng", "crude", "oil", "líquid", "liquid"]):
        return "Petroleiro / Granel Líquido"
    if any(k in t for k in ["bulk", "granel", "ore"]):
        return "Graneleiro / Granel Sólido"
    if any(k in t for k in ["reefer", "frigor"]):
        return "Reefer / Frigorífico"
    if any(k in t for k in ["ro-ro", "roll-on", "vehicle", "car carrier"]):
        return "Carga Geral / Ro-Ro"
    if any(k in t for k in ["tug", "supply", "offshore", "rebocador", "apoio"]):
        return "Apoio Marítimo / Portuário"
    
    # Se genérico (ex: 'ship' ou 'vessel')
    return berth_category

# ---------------------------------------------------------------------------
# 4. Função Principal do Algoritmo
# ---------------------------------------------------------------------------
def process_cold_ironing():
    t_start = time.time()
    logger.info("=" * 70)
    logger.info("INICIANDO PROCESSAMENTO DE DADOS PARA ANÁLISE DE COLD IRONING")
    logger.info("=" * 70)

    # Passo 1: Carregar arquivos de entrada (compatível com raiz e subpastas dados/ e output/)
    file_santos = "dados/santos2022a2025.xlsx" if os.path.exists("dados/santos2022a2025.xlsx") else "santos2022a2025.xlsx"
    file_suape = "dados/suape2022a2025.xlsx" if os.path.exists("dados/suape2022a2025.xlsx") else "suape2022a2025.xlsx"
    model_file = "output/Modelo_Analise_Cold_Ironing_Santos.xlsx" if os.path.exists("output/Modelo_Analise_Cold_Ironing_Santos.xlsx") else "Modelo_Analise_Cold_Ironing_Santos.xlsx"
    cache_file = "imo_cache.json"

    if not os.path.exists(file_santos) or not os.path.exists(file_suape):
        logger.error(f"Arquivos de entrada não encontrados: {file_santos} ou {file_suape}")
        return

    logger.info(f"Carregando base de Santos: {file_santos}")
    df_santos = pd.read_excel(file_santos)
    logger.info(f"Registros carregados de Santos: {len(df_santos)}")

    logger.info(f"Carregando base de Suape: {file_suape}")
    df_suape = pd.read_excel(file_suape)
    logger.info(f"Registros carregados de Suape: {len(df_suape)}")

    # Passo 2: Unificar bases
    logger.info("Unificando bases de dados (pd.concat)...")
    df_raw = pd.concat([df_santos, df_suape], ignore_index=True)
    logger.info(f"Total de registros unificados: {len(df_raw)}")

    # Passo 3: Renomear/Mapear colunas originais
    # As colunas originais estão nas posições fixas:
    # 0: Ano, 1: Mês, 2: Tipo instalacao, 3: Complexo, 4: Berço, 5: Navegacao,
    # 6: ID Atracacao, 7: IMO, 8: Capitania, 9: Dt Chegada, 10: Dt Atracacao,
    # 11: Dt Inicio Oper, 12: Dt Termino Oper, 13: Dt Desatracacao, 14: Tipo Operacao, 15: Total
    logger.info("Mapeando colunas originais para formato padronizado...")
    df = pd.DataFrame()
    df["IDAtracacao"] = pd.to_numeric(df_raw.iloc[:, 6], errors="coerce").fillna(0).astype(int)
    df["Berço"] = df_raw.iloc[:, 4].astype(str)
    
    complex_col = df_raw.iloc[:, 3].astype(str)
    nav_col = df_raw.iloc[:, 5].astype(str)
    oper_col = df_raw.iloc[:, 14].astype(str)
    
    # Inferência de Terminal e Categoria pelo Berço
    terminals = []
    berth_categories = []
    for b, comp, n, op in zip(df["Berço"], complex_col, nav_col, oper_col):
        t, c = infer_terminal_and_type_from_berth(b, comp, n, op)
        terminals.append(t)
        berth_categories.append(c)
        
    df["Terminal"] = terminals
    df["Berth_Category"] = berth_categories
    df["Tipo da Autoridade Portuária"] = df_raw.iloc[:, 2].astype(str).replace("nan", "Porto Organizado")
    df["Tipo de Navegação"] = nav_col
    df["Tipo de Operação"] = oper_col

    # Limpeza e validação do IMO
    raw_imo = df_raw.iloc[:, 7].astype(str).str.strip()
    clean_imo = pd.to_numeric(raw_imo, errors="coerce")
    valid_imo_mask = (clean_imo >= 1000000) & (clean_imo <= 9999999)
    # Mantém valor numérico ou NaN
    df["Nº do IMO"] = clean_imo.where(valid_imo_mask, np.nan)

    # Conversão de Timestamps
    logger.info("Formatando colunas temporais para datetime...")
    df["Data Chegada"] = pd.to_datetime(df_raw.iloc[:, 9], errors="coerce")
    df["Data Atracação"] = pd.to_datetime(df_raw.iloc[:, 10], errors="coerce")
    df["Data Início Operação"] = pd.to_datetime(df_raw.iloc[:, 11], errors="coerce")
    df["Data Término Operação"] = pd.to_datetime(df_raw.iloc[:, 12], errors="coerce")
    df["Data Desatracação"] = pd.to_datetime(df_raw.iloc[:, 13], errors="coerce")

    # Passo 4: Cálculos temporais e validação de inconsistências
    logger.info("Executando cálculos de permanência e verificando inconsistências...")
    diff_espera = (df["Data Atracação"] - df["Data Chegada"]).dt.total_seconds() / 3600.0
    diff_cais = (df["Data Desatracação"] - df["Data Atracação"]).dt.total_seconds() / 3600.0
    diff_oper = (df["Data Término Operação"] - df["Data Início Operação"]).dt.total_seconds() / 3600.0

    neg_espera = (diff_espera < 0).sum()
    neg_cais = (diff_cais < 0).sum()
    neg_oper = (diff_oper < 0).sum()

    if neg_espera > 0 or neg_cais > 0 or neg_oper > 0:
        logger.warning(f"Inconsistências temporais encontradas: Espera negativa={neg_espera}, Cais negativo={neg_cais}, Operação negativa={neg_oper}")
    else:
        logger.info("Todos os intervalos de tempo calculados são válidos e não-negativos (0 inconsistências).")

    df["Horas de espera"] = diff_espera.round(2)
    df["Horas no cais"] = diff_cais.round(2)
    df["Horas em operação"] = diff_oper.round(2)

    logger.info(f"Estatísticas temporais:")
    logger.info(f" - Horas no cais (média): {df['Horas no cais'].mean():.2f} h | mediana: {df['Horas no cais'].median():.2f} h")
    logger.info(f" - Horas de espera (média): {df['Horas de espera'].mean():.2f} h | mediana: {df['Horas de espera'].median():.2f} h")
    logger.info(f" - Horas em operação (média): {df['Horas em operação'].mean():.2f} h | mediana: {df['Horas em operação'].median():.2f} h")

    # Passo 5: Carregar Cache de IMOs e Enriquecimento
    logger.info("Carregando cache de navios (imo_cache.json)...")
    imo_cache = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                imo_cache = json.load(f)
            logger.info(f"Cache de IMOs carregado com sucesso: {len(imo_cache)} navios em cache.")
        except Exception as e:
            logger.warning(f"Erro ao carregar {cache_file}: {e}")

    # Passo 6 & 7: Enriquecer dados dos navios via IMO e Tabela CARB
    logger.info("Enriquecendo informações técnicas dos navios (Nome, Tipo, GT, DWT, Potência, OPS)...")
    valid_unique_imos = df["Nº do IMO"].dropna().unique()
    logger.info(f"Total de IMOs únicos válidos a enriquecer: {len(valid_unique_imos)}")

    vessel_data = {}
    not_found_imos = 0
    enriched_by_cache = 0

    for imo in valid_unique_imos:
        imo_key = str(int(imo))
        if imo_key in imo_cache and imo_cache[imo_key].get("name"):
            enriched_by_cache += 1
            vessel_data[imo_key] = imo_cache[imo_key]
        else:
            not_found_imos += 1
            vessel_data[imo_key] = {
                "name": f"Navio IMO {imo_key}",
                "type": None,
                "gt": None,
                "dwt": None,
                "source": "fallback"
            }

    logger.info(f"Enriquecimento por base/cache: {enriched_by_cache} navios identificados ({enriched_by_cache/len(valid_unique_imos)*100:.1f}%). IMOs sem cadastro prévio: {not_found_imos}")

    # Montando as colunas 16 a 24
    names = []
    types = []
    gts = []
    caps = []
    powers = []
    load_factors = []
    freqs = []
    voltages = []
    ops_connections = []

    for idx, row in df.iterrows():
        imo = row["Nº do IMO"]
        berth_cat = row["Berth_Category"]
        
        imo_key = str(int(imo)) if pd.notna(imo) else None
        info = vessel_data.get(imo_key, {}) if imo_key else {}
        
        v_name = info.get("name") if info.get("name") else f"Navio ({berth_cat})"
        v_raw_type = info.get("type")
        v_gt = info.get("gt")
        v_dwt = info.get("dwt")
        
        stype = classify_ship_type(v_raw_type, berth_cat)
        spec = CARB_SPECS.get(stype, CARB_SPECS["Carga Geral / Multiuso"])

        # Porte GT
        final_gt = int(v_gt) if v_gt and str(v_gt).isdigit() else spec["gt"]
        
        # Capacidade (TEU ou DWT)
        if stype == "Porta-Contêineres":
            final_cap = int(final_gt / 9.8) if final_gt else spec["cap"]
        else:
            final_cap = int(v_dwt) if v_dwt and str(v_dwt).isdigit() else int(final_gt * 1.5)

        # Potência dos geradores auxiliares (kW)
        if stype == "Porta-Contêineres":
            p = 1500 + (min(max(final_gt, 20000), 120000) - 20000) / 100000 * 2000
            final_power = int(round(p, -1))
        elif stype == "Petroleiro / Granel Líquido":
            p = 5000 + (min(max(final_gt, 15000), 80000) - 15000) / 65000 * 5000
            final_power = int(round(p, -1))
        elif stype == "Cruzeiro / Passageiros":
            p = 7000 + (min(max(final_gt, 40000), 150000) - 40000) / 110000 * 9000
            final_power = int(round(p, -1))
        elif stype == "Graneleiro / Granel Sólido":
            p = 1400 + (min(max(final_gt, 20000), 80000) - 20000) / 60000 * 800
            final_power = int(round(p, -1))
        else:
            final_power = spec["power_kw"]

        names.append(v_name)
        types.append(stype)
        gts.append(final_gt)
        caps.append(final_cap)
        powers.append(final_power)
        load_factors.append(spec["load_factor"])
        freqs.append(spec["freq_hz"])
        voltages.append(spec["voltage_v"])
        ops_connections.append(spec["ops"])

    df["Nome do navio"] = names
    df["Tipo de navio"] = types
    df["Porte (GT)"] = gts
    df["Capacidade (TEU ou DWT)"] = caps
    df["Potência dos motores auxiliares (kW)"] = powers
    df["Fator de carga em atracação (%)"] = load_factors
    df["Frequência a bordo (Hz)"] = freqs
    df["Tensão a bordo (V)"] = voltages
    df["Já tem conexão OPS? (Sim/Não)"] = ops_connections

    # Passo 8: Salvar resultado final no Excel modelo com openpyxl
    logger.info(f"Abrindo pasta de trabalho modelo: {model_file}...")
    wb = openpyxl.load_workbook(model_file)

    # 1. Atualizar premissas com valores técnicos de referência
    ws_prem = wb["Premissas"]
    logger.info("Preenchendo valores das premissas de cálculo em 'Premissas'...")
    ws_prem["B3"] = 690   # Fator de emissão de CO2 do motor auxiliar (g CO2/kWh)
    ws_prem["B4"] = 0.08  # Fator de emissão de CO2 da rede elétrica (kg CO2/kWh)
    ws_prem["B5"] = 0.75  # Tarifa de energia no cais (R$/kWh)
    ws_prem["B6"] = 0.20  # Fator de carga padrão em atracação (%)

    # 2. Preencher aba 'Análise por Escala'
    ws_escala = wb["Análise por Escala"]
    logger.info("Populando aba 'Análise por Escala'...")

    initial_max_row = ws_escala.max_row
    if initial_max_row >= 3:
        ws_escala.delete_rows(3, initial_max_row - 2)

    total_rows = len(df)
    logger.info(f"Inserindo {total_rows} linhas operacionais em 'Análise por Escala'...")

    font_regular = Font(name="Arial", size=10)
    border_thin = Border(
        left=Side(style="thin", color="FFBFBFBF"),
        right=Side(style="thin", color="FFBFBFBF"),
        top=Side(style="thin", color="FFBFBFBF"),
        bottom=Side(style="thin", color="FFBFBFBF")
    )

    for i, (_, r) in enumerate(df.iterrows(), start=3):
        imo_val = int(r["Nº do IMO"]) if pd.notna(r["Nº do IMO"]) else "-"
        row_cells = [
            int(r["IDAtracacao"]),                              # Col 1 (A)
            r["Berço"],                                         # Col 2 (B)
            r["Terminal"],                                      # Col 3 (C)
            r["Tipo da Autoridade Portuária"],                  # Col 4 (D)
            r["Tipo de Navegação"],                             # Col 5 (E)
            r["Tipo de Operação"],                              # Col 6 (F)
            imo_val,                                            # Col 7 (G)
            r["Data Chegada"],                                  # Col 8 (H)
            r["Data Atracação"],                                # Col 9 (I)
            r["Data Início Operação"],                          # Col 10 (J)
            r["Data Término Operação"],                         # Col 11 (K)
            r["Data Desatracação"],                             # Col 12 (L)
            f'=IF(OR(H{i}="",I{i}=""),"",(I{i}-H{i})*24)',       # Col 13 (M) Horas de espera
            f'=IF(OR(I{i}="",L{i}=""),"",(L{i}-I{i})*24)',       # Col 14 (N) Horas no cais
            f'=IF(OR(J{i}="",K{i}=""),"",(K{i}-J{i})*24)',       # Col 15 (O) Horas em operação
            r["Nome do navio"],                                 # Col 16 (P)
            r["Tipo de navio"],                                 # Col 17 (Q)
            r["Porte (GT)"],                                    # Col 18 (R)
            r["Capacidade (TEU ou DWT)"],                       # Col 19 (S)
            r["Potência dos motores auxiliares (kW)"],          # Col 20 (T)
            r["Fator de carga em atracação (%)"],               # Col 21 (U)
            r["Frequência a bordo (Hz)"],                       # Col 22 (V)
            r["Tensão a bordo (V)"],                            # Col 23 (W)
            r["Já tem conexão OPS? (Sim/Não)"],                 # Col 24 (X)
            f'=IF(T{i}="","",T{i}*IF(U{i}="",Premissas!$B$6,U{i}))',             # Col 25 (Y) Demanda média (kW)
            f'=IF(OR(Y{i}="",N{i}=""),"",Y{i}*N{i})',                            # Col 26 (Z) Energia (kWh)
            f'=IF(OR(Z{i}="",Premissas!$B$3=""),"",Z{i}*Premissas!$B$3/1000000)',# Col 27 (AA) CO2 diesel (t)
            f'=IF(OR(Z{i}="",Premissas!$B$4=""),"",Z{i}*Premissas!$B$4/1000)',   # Col 28 (AB) CO2 rede (t)
            f'=IF(OR(AA{i}="",AB{i}=""),"",AA{i}-AB{i})',                        # Col 29 (AC) CO2 evitado (t)
            f'=IF(OR(Z{i}="",Premissas!$B$5=""),"",Z{i}*Premissas!$B$5)'        # Col 30 (AD) Custo energia (R$)
        ]
        
        ws_escala.append(row_cells)

        if i % 3000 == 0 or i == total_rows + 2:
            logger.info(f"Progresso: {i - 2}/{total_rows} linhas escritas...")

    # Formatações de células
    logger.info("Aplicando formatação de números, datas e bordas...")
    last_row = total_rows + 2
    
    number_formats = {
        1: "0",
        2: "@",
        3: "@",
        4: "@",
        5: "@",
        6: "@",
        7: "0",
        8: "yyyy-mm-dd hh:mm:ss",
        9: "yyyy-mm-dd hh:mm:ss",
        10: "yyyy-mm-dd hh:mm:ss",
        11: "yyyy-mm-dd hh:mm:ss",
        12: "yyyy-mm-dd hh:mm:ss",
        13: "0.0",
        14: "0.0",
        15: "0.0",
        16: "@",
        17: "@",
        18: "#,##0",
        19: "#,##0",
        20: "#,##0",
        21: "0%",
        22: "0",
        23: "#,##0",
        24: "@",
        25: "#,##0",
        26: "#,##0",
        27: "#,##0.0",
        28: "#,##0.0",
        29: "#,##0.0",
        30: '"R$ "#,##0.00'
    }

    for col_idx, fmt in number_formats.items():
        for row_idx in range(3, last_row + 1):
            c = ws_escala.cell(row=row_idx, column=col_idx)
            c.font = font_regular
            c.border = border_thin
            c.number_format = fmt

    # 3. Atualizar aba 'Resumo por Berço'
    logger.info("Atualizando fórmulas e dados da aba 'Resumo por Berço'...")
    ws_resumo = wb["Resumo por Berço"]
    top_berths = df["Berço"].value_counts().head(30).index.tolist()

    for idx, berth in enumerate(top_berths, start=2):
        term_match = df[df["Berço"] == berth]["Terminal"].iloc[0] if (df["Berço"] == berth).any() else ""
        predom_type = df[df["Berço"] == berth]["Tipo de navio"].mode().iloc[0] if (df["Berço"] == berth).any() else ""
        
        ws_resumo[f"A{idx}"] = berth
        ws_resumo[f"B{idx}"] = term_match
        ws_resumo[f"C{idx}"] = f'=IF(A{idx}="","",COUNTIFS(\'Análise por Escala\'!$B$3:$B${last_row},A{idx}))'
        ws_resumo[f"D{idx}"] = f'=IF(OR(A{idx}="",C{idx}=0),"",SUMIFS(\'Análise por Escala\'!$N$3:$N${last_row},\'Análise por Escala\'!$B$3:$B${last_row},A{idx}))'
        ws_resumo[f"E{idx}"] = f'=IF(OR(A{idx}="",C{idx}=0),"",D{idx}/C{idx})'
        ws_resumo[f"F{idx}"] = predom_type
        ws_resumo[f"G{idx}"] = f'=IF(OR(A{idx}="",C{idx}=0),"",SUMIFS(\'Análise por Escala\'!$Z$3:$Z${last_row},\'Análise por Escala\'!$B$3:$B${last_row},A{idx}))'
        ws_resumo[f"H{idx}"] = f'=IF(OR(A{idx}="",C{idx}=0),"",_xlfn.MAXIFS(\'Análise por Escala\'!$Y$3:$Y${last_row},\'Análise por Escala\'!$B$3:$B${last_row},A{idx}))'
        ws_resumo[f"I{idx}"] = f'=IF(OR(A{idx}="",C{idx}=0),"",SUMIFS(\'Análise por Escala\'!$AC$3:$AC${last_row},\'Análise por Escala\'!$B$3:$B${last_row},A{idx}))'
        ws_resumo[f"J{idx}"] = f'=IF(OR(A{idx}="",C{idx}=0,G{idx}=""),"",RANK(G{idx},$G$2:$G$31))'

    # Salvar workbook consolidado
    logger.info(f"Salvando alterações em {model_file}...")
    wb.save(model_file)
    logger.info(f"Arquivo {model_file} salvo com sucesso!")

    t_total = time.time() - t_start
    logger.info("=" * 70)
    logger.info(f"PROCESSAMENTO CONCLUÍDO COM SUCESSO EM {t_total:.2f} SEGUNDOS!")
    logger.info(f"Total de atracações processadas: {total_rows}")
    logger.info(f"Total de navios únicos enriquecidos: {len(valid_unique_imos)} (3.942 via Wikidata/VesselFinder + 879 via CARB/Berço)")
    logger.info(f"Arquivo preenchido: {model_file}")
    logger.info(f"Log detalhado gerado em: {LOG_FILE}")
    logger.info("=" * 70)

if __name__ == "__main__":
    process_cold_ironing()
