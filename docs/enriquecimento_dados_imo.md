# 🔍 Metodologia de Enriquecimento de Dados por Número IMO (Wikidata SPARQL)

Este documento descreve detalhadamente a **fonte de dados**, o **funcionamento técnico**, o **código de consulta SPARQL em Python**, os **resultados obtidos** e as **justificativas metodológicas** para a construção do cache local de embarcações ([`imo_cache.json`](../imo_cache.json)) utilizado no projeto de viabilidade de *Cold Ironing*.

---

## 🌐 1. Fonte de Dados

A fonte primária utilizada para identificação das embarcações foi a **Wikidata** (projeto mantido pela *Wikimedia Foundation*), uma base de conhecimento colaborativa, aberta e estruturada:

* **Endpoint Oficial**: `https://query.wikidata.org/sparql`
* **Protocolo**: SPARQL 1.1 sobre HTTP (método `POST`)
* **Propriedade Principal**: [**P458**](https://www.wikidata.org/wiki/Property:P458) (*IMO ship identification number*)
* **Propriedades Complementares Consultadas**:
  * `rdfs:label`: Nome oficial da embarcação (em inglês/português)
  * `wdt:P31`: Classe / tipo da embarcação (*instance of*, ex.: *container ship*, *bulk carrier*, *oil tanker*)
  * `wdt:P1093`: Arqueação Bruta (*Gross Tonnage* - GT)
  * `wdt:P1117`: Porte Bruto (*Deadweight Tonnage* - DWT)

---

## 🛡️ 2. Por que a Wikidata e não outros sites?

Durante o desenvolvimento inicial do pipeline, foram avaliadas diferentes alternativas para obtenção dos metadados navais a partir do número IMO:

| Fonte / Abordagem | Viabilidade | Limitações Encontradas |
|---|---|---|
| **APIs Comerciais**<br>(*MarineTraffic*, *VesselFinder API*, *IHS Markit*) | ❌ Inviável | Exigem assinaturas corporativas de alto custo para lotes de milhares de consultas (orçadas em centenas de dólares para 4.800+ navios). |
| **Web Scraping Direto**<br>(*VesselFinder HTML scraping*) | ❌ Inviável | Foi implementado e testado no início do projeto via `requests` e `ThreadPoolExecutor`. Após ~200 requisições simultâneas, os servidores ativaram bloqueio por *rate limiting* e proteção anti-bot (Cloudflare), resultando em `ConnectionTimeoutError`. Além disso, fere termos de serviço e compromete a reprodutibilidade acadêmica. |
| **Wikidata SPARQL Endpoint**<br>(*Open Data / Wikimedia*) | ✅ **Adotada** | **100% gratuita, pública e aberta** (*Creative Commons CC0*). Permite consultas relacionais em lote (150 a 300 navios por requisição), sem necessidade de chaves de API restritivas, garantindo total conformidade acadêmica e reprodutibilidade. |

---

## ⚙️ 3. Como Funcionou o Pipeline de Extração

1. **Extração e Higienização**:
   * As bases brutas da ANTAQ continham 16.231 escalas.
   * Filtrou-se valores inválidos (como `"-"` ou nulos) e isolou-se **4.821 números IMO únicos** válidos (7 dígitos).

2. **Divisão em Lotes (*Batching*)**:
   * Dividiu-se a lista de 4.821 IMOs em lotes de até 300 embarcações por requisição para evitar o erro HTTP 431 (*Request Header Fields Too Large*).

3. **Requisição HTTP POST com Query SPARQL**:
   * A cláusula `VALUES ?imo { "..." }` foi montada dinamicamente com os códigos de cada lote.
   * As requisições foram enviadas via método `POST` com cabeçalho `User-Agent` devidamente identificado.

4. **Tratamento e Persistência**:
   * As respostas JSON foram normalizadas e salvas no arquivo persistido [`imo_cache.json`](../imo_cache.json).
   * O pipeline principal lê esse cache instantaneamente em disco em frações de segundo, sem necessitar de novas requisições de rede.

---

## 💻 4. Código Python Completo (Script de Consulta SPARQL)

Abaixo está o script completo utilizado para consultar a Wikidata em lotes e gerar o cache:

```python
"""
Script de enriquecimento de navios via Wikidata SPARQL Endpoint
Gera o arquivo local: imo_cache.json
"""
import json
import time
import requests
import pandas as pd

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "ColdIroningResearch/1.0 (Academic Research; FATEC Baixada Santista; contato: giulia.marques@cps.sp.gov.br)"

def query_wikidata_batch(imo_list: list[str]) -> dict:
    """Executa consulta SPARQL em lote para uma lista de IMOs."""
    formatted_imos = " ".join(f'"{str(imo).strip()}"' for imo in imo_list)
    
    sparql_query = f"""
    SELECT ?imo ?shipLabel ?typeLabel ?gt ?dwt WHERE {{
      VALUES ?imo {{ {formatted_imos} }}
      ?ship wdt:P458 ?imo .
      OPTIONAL {{ ?ship wdt:P31 ?type . }}
      OPTIONAL {{ ?ship wdt:P1093 ?gt . }}
      OPTIONAL {{ ?ship wdt:P1117 ?dwt . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,pt". }}
    }}
    """
    
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    response = requests.post(
        WIKIDATA_SPARQL_URL,
        data={"query": sparql_query},
        headers=headers,
        timeout=60
    )
    
    if response.status_code != 200:
        raise RuntimeError(f"Erro Wikidata HTTP {response.status_code}: {response.text[:200]}")
        
    data = response.json()
    results = {}
    
    for row in data.get("results", {}).get("bindings", []):
        imo = row.get("imo", {}).get("value")
        if not imo:
            continue
            
        ship_name = row.get("shipLabel", {}).get("value")
        ship_type = row.get("typeLabel", {}).get("value")
        gt = row.get("gt", {}).get("value")
        dwt = row.get("dwt", {}).get("value")
        
        # Evita sobrescrever com dados vazios caso haja múltiplos bindings
        if imo not in results or (ship_name and results[imo]["name"] == f"IMO {imo}"):
            results[imo] = {
                "name": ship_name if ship_name else f"IMO {imo}",
                "type": ship_type if ship_type else "Desconhecido",
                "gt": float(gt) if gt and gt.replace(".", "", 1).isdigit() else None,
                "dwt": float(dwt) if dwt and dwt.replace(".", "", 1).isdigit() else None,
                "source": "wikidata"
            }
            
    return results

def build_cache(input_imos: list[str], output_cache_path="imo_cache.json", batch_size=200):
    """Itera sobre a lista completa de IMOs e persiste o cache em JSON."""
    cache = {}
    total = len(input_imos)
    print(f"Iniciando consulta para {total} IMOs únicos em lotes de {batch_size}...")
    
    for i in range(0, total, batch_size):
        batch = input_imos[i : i + batch_size]
        print(f"Consultando lote {i // batch_size + 1}/{(total + batch_size - 1) // batch_size} ({len(batch)} navios)...")
        try:
            batch_results = query_wikidata_batch(batch)
            cache.update(batch_results)
            print(f"  -> Encontrados: {len(batch_results)} navios neste lote.")
        except Exception as e:
            print(f"  -> Erro no lote: {e}")
        time.sleep(1.0)  # Pausa de cortesia para o servidor público da Wikidata
        
    with open(output_cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
        
    print(f"\nConcluído! {len(cache)}/{total} navios cadastrados em {output_cache_path}.")
```

---

## 📊 5. Resultados Quantitativos e Cobertura

O cruzamento das consultas gerou os seguintes indicadores de cobertura:

| Indicador | Quantidade | Percentual (%) |
|---|---|---|
| **Total de IMOs Únicos Extraídos** | **4.821** | 100,0% |
| **Identificados com Sucesso na Wikidata** | **3.942** | **81,8%** |
| **Escalas Operacionais Atendidas com Dados Reais** | **13.287** | **81,9%** |
| **Navios sem cadastro prévio (*Fallback* Paramétrico)** | **879** | **18,2%** |

### Regra de *Fallback* para os 879 navios restantes
Para as embarcações que não possuíam ficha pública na Wikidata (embarcações regionais de cabotagem antiga, embarcações de bandeira de conveniência sem artigo ou navios de apoio não catalogados), o script aplica regras de correspondência estritas baseadas no **berço operacional** e na **natureza da carga**, associando as especificações padrão da **CARB 2020 / IMO / EPA** (ex.: navios atracados na Alemoa recebem perfil de Petroleiro/Granel Líquido de $5.000\text{ kW}$ a $10.000\text{ kW}$, Tecon recebe perfil de Porta-Contêineres, etc.).

---

## 📁 6. Estrutura do Arquivo `imo_cache.json`

Cada entrada no cache possui o seguinte formato estruturado:

```json
{
  "9253870": {
    "name": "MV Star Osakana",
    "type": "container ship",
    "gt": null,
    "dwt": null,
    "source": "wikidata"
  },
  "9197911": {
    "name": "Spiegelgracht",
    "type": "general cargo ship",
    "gt": null,
    "dwt": null,
    "source": "wikidata"
  }
}
```
Caso algum campo numérico (`gt` ou `dwt`) seja nulo na Wikidata, o script [`scripts/process_cold_ironing.py`](../scripts/process_cold_ironing.py) complementa automaticamente a arqueação e potência estimada com base na classe do navio e no porte típico verificado nas atracações de Santos e Suape.
