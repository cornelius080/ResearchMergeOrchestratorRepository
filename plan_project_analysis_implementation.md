Ecco un'analisi approfondita di 

useful_files/ADK_Web_Search.ipynb
 e la proposta di piano d'azione per modularizzare il codice nel progetto.

Non ho modificato né creato alcun file, come da tua richiesta.

# Analisi del Notebook & Struttura del Progetto
Il notebook implementa un grafo gerarchico basato su Google ADK:

- Tool di Ricerca e Scraping: duckduckgo_search con scraping parallelo via multithreading (curl_cffi + BeautifulSoup), estrazione date e parsing.
- 3 Sub-Agenti di Ricerca Specializzati:
deeplearning_agent (dominio deeplearning.ai $\rightarrow$ output in state: deep_learning_result)
techcrunch_agent (dominio techcrunch.com/category/artificial-intelligence/ $\rightarrow$ output in state: techcrunch_result)
arstechnica_agent (dominio arstechnica.com/ai $\rightarrow$ output in state: ars_technica_result)
Parallel Agent: ParallelWebResearchAgent che esegue i 3 sub-agenti in parallelo.
Merger / Synthesis Agent: SynthesisAgent che riceve i risultati dei 3 agenti dallo stato della sessione e redige il report scientifico formattato con citazioni [1], [2].
- Root Agent Sequenziale: SequentialAgent che coordina ParallelAgent $\rightarrow$ SynthesisAgent.
- Runner & Session Service: Runner collegato a InMemorySessionService per l'esecuzione asincrona (runner.run_async).
Valutazione della Struttura Cartelle Attuale
La struttura che hai predisposto (tools/, agents/, workflows/, frontend/, main.py) è eccellente e ben organizzata. Suggerisco soltanto di formalizzare i file specifici all'interno di ciascuna cartella e aggiungere un modulo config.py per disaccoppiare la configurazione dei modelli e delle API key:

Research_Merge_Orchestrator/
│
├── config.py                 # [NUOVO] Configurazione centralizzata (modelli, env vars, logging)
├── .env.example              # [AGGIORNATO] Template chiavi e modelli supportati
├── main.py                   # [AGGIORNATO] Entrypoint FastAPI con endpoint POST /api/process
│
├── tools/
│   ├── __init__.py           # [NUOVO] Esportazione tools
│   └── search_tool.py        # [NUOVO] duckduckgo_search, scraping parallelo, parsing date e callback
│
├── agents/
│   ├── __init__.py           # [NUOVO] Esportazione agenti
│   ├── sub_agents.py         # [NUOVO] I 3 sub-agenti di ricerca (deeplearning, techcrunch, arstechnica)
│   └── synthesis_agent.py    # [NUOVO] Merger / SynthesisAgent con prompt strutturato e citazioni
│
├── workflows/
│   ├── __init__.py           # [NUOVO] Esportazione workflow
│   └── orchestrator.py       # [NUOVO] ParallelAgent, SequentialAgent, Runner e session service
│
└── frontend/                 # [GIÀ COMPLETATO] Chat UI (index.html, style.css, app.js)


# Piano di Implementazione Step-by-Step
Procederemo in maniera guidata, implementando un solo step alla volta e attendendo il tuo via libera prima di passare al successivo:

🔹 STEP 1: Centralizzazione Configurazione (config.py e .env.example)
Obiettivo: Rendere il modello LLM flessibile e configurabile tramite variabili d'ambiente senza hardcodarlo nel codice (nel notebook viene usato sia LiteLlm con Ollama Cloud sia Gemini nativo).
File da creare:
config.py: Gestione caricamento .env, definizione del modello predefinito (Gemini nativo o LiteLLM/Ollama in base alla configurazione) e impostazioni generali.
.env.example: Elenco delle variabili d'ambiente necessarie (GEMINI_API_KEY, eventuale configurazione modello).


🔹 STEP 2: Modulo Strumenti (tools/search_tool.py)
Obiettivo: Estrarre dal notebook la logica di ricerca DuckDuckGo e scraping avanzato.
File da creare:
tools/search_tool.py:
Funzione principale duckduckgo_search(query, max_results, domain)
Funzioni ausiliarie: _extract_pub_date, _parse_date_for_sorting, _fetch_and_parse_article (con curl_cffi e ThreadPoolExecutor)
Callback before_tool e after_tool con logging pulito degli argomenti e del tool eseguito.
tools/__init__.py.


🔹 STEP 3: Modulo Agenti (agents/sub_agents.py e agents/synthesis_agent.py)
Obiettivo: Isolare le definizioni degli agenti individuali e i relativi prompt di sistema.
File da creare:
agents/sub_agents.py: Definizione di subagent_1 (deeplearning_agent), subagent_2 (techcrunch_agent), subagent_3 (arstechnica_agent) associati ai relativi callback e chiavi di output nello stato (deep_learning_result, techcrunch_result, ars_technica_result).
agents/synthesis_agent.py: Definizione di merger_agent (SynthesisAgent) con il prompt di formattazione scientifica dettagliato (regole bibliografiche, intervallo 5-15 righe, numerazione [N]).
agents/__init__.py.


🔹 STEP 4: Modulo Orchestrazione Workflow (workflows/orchestrator.py)
Obiettivo: Assemblare il grafo gerarchico dei flussi e gestire il ciclo di vita delle sessioni.
File da creare:
workflows/orchestrator.py:
Assemblaggio di parallel_research_agent = ParallelAgent(...) e root_agent = SequentialAgent(...)
Inizializzazione di InMemorySessionService e Runner
Funzione asincrona run_orchestrated_research(query: str, session_id: Optional[str] = None) che esegue runner.run_async(...), intercetta gli output intermedi dei sub-agenti e restituisce la risposta finale sintetizzata e l'elenco dei dati raccolti.
workflows/__init__.py.


🔹 STEP 5: Aggiornamento Endpoint FastAPI (

main.py
)
Obiettivo: Collegare la richiesta REST del frontend all'orchestratore di ricerca.
File da aggiornare:


main.py
:
Attivazione e completamento di @app.post("/api/process").
Ricezione di MessagePayload(message=...) dal frontend.
Chiamata a run_orchestrated_research(payload.message).
Risposta JSON strutturata con { "response": final_response, "agent_results": agent_results }.


🔹 STEP 6: Verifica & Collaudo End-to-End
Obiettivo: Eseguire una prova con FastAPI verificando che:
Il frontend in 

frontend/
 mostri "API Online".
Inviando una query (es. "What are the latest news about Nvidia?"), i 3 sub-agenti interroghino i rispettivi domini in parallelo.
La chat riceva e renderizzi correttamente il report scientifico con i tag numerati [1], [2] e la bibliografia delle fonti.