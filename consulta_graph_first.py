from dotenv                 import dotenv_values
from neo4j                  import GraphDatabase
from langchain_openai       import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from schemas                import FiltrosConsultaGraphRAG
from typing                 import Dict, Any

class PipelineGraphFirst:

    def __init__(self):
        config     = dotenv_values(dotenv_path=".env")
        openai_key = config.get("OPENAI_API_KEY")

        # Neo4j
        neo4j_uri      = config.get("NEO4J_URI")
        neo4j_user     = config.get("NEO4J_USER")
        neo4j_password = config.get("NEO4J_PASSWORD")
        self._driver   = GraphDatabase.driver(
            uri  = neo4j_uri,
            auth = (
                neo4j_user,
                neo4j_password
            )
        )

        # Modelos
        self._embeddings = OpenAIEmbeddings(
            model   = "text-embedding-3-small",
            api_key = openai_key
        )

        self._llm = ChatOpenAI(
            model       = "gpt-4o-mini",
            temperature = 0.0,
            api_key     = openai_key
        )

    def __call__(self, pregunta:str, filtros: FiltrosConsultaGraphRAG):
        datos_grafo    = self._obtener_contexto_grafo_texto(filtros=filtros)
        textos         = [
            f"\n--- Contexto de Origen {i:02d}---\n\n{txt}"
            for i, txt in enumerate(datos_grafo["contexto_text"], 1)
        ]
        valores_prompt = { # sintesis final con LLM
            "contexto_grafo"     : "\n".join(datos_grafo["contexto_grafo"]),
            "contexto_vectorial" : "\n".join(textos),
            "pregunta"           : pregunta
        }
        prompt_sintesis = ChatPromptTemplate.from_messages([
            ("system", (
                "Eres un asistente experto en bases de conocimiento.\n"
                "Responde a la pregunta del usuario utilizando EXCLUSIVAMENTE el contexto proveído a continuación.\n"
                "Si la información no es suficiente para responder, indícalo claramente sin inventar datos.\n\n"
                "1. ESTRUCTURA Y RELACIONES DEL GRAFO:\n"
                "{contexto_grafo}\n\n"
                "2. FRAGMENTOS DE TEXTO RECUPERADOS:\n"
                "{contexto_vectorial}"
            )),
            ("human", "{pregunta}")
        ])
        cadena_sintesis = prompt_sintesis | self._llm
        respuesta       = cadena_sintesis.invoke(input=valores_prompt)
        return respuesta.content

    def close(self):
        self._driver.close()

    def _limpiar_props(self, props: Dict[str, Any]) -> str:
        if not props:
            return ""
        props_filtradas = {k:v for k, v in props.items() if k not in ["id", "nombre", "text", "vector"]}
        return f" {props_filtradas}" if props_filtradas else ""

    def _obtener_contexto_grafo_texto(self, filtros: FiltrosConsultaGraphRAG) -> Dict[str, Any]:
        contexto_grafo = []
        query_cypher   = """
        MATCH (n:Entidad)-[r]->(m:Entidad)
        WHERE (
            // 1. Búsqueda directa en nombre y text para el nodo origen (excluyendo vector)
            ANY(t IN $terminos WHERE toLower(n.nombre) CONTAINS toLower(t) OR toLower(n.text) CONTAINS toLower(t))
            OR ANY(t in $terminos WHERE ANY(key IN [k IN keys(n) WHERE k <> 'vector'] WHERE toLower(toString(n[key])) CONTAINS toLower(t)))

            // 2. Búsqueda en relaciones
            OR ANY(t IN $terminos WHERE ANY(key IN keys(r) WHERE toLower(toString(r[key])) CONTAINS toLower(t)))

            // 3. Busqueda directa en nombre y text para el nodo destino (excluyendo vector)
            OR ANY(t IN $terminos WHERE toLower(m.nombre) CONTAINS toLower(t) OR toLower(m.text) CONTAINS toLower(t))
            OR ANY(t IN $terminos WHERE ANY(key IN [k IN keys(m) WHERE k <> 'vector'] WHERE toLower(toString(m[key])) CONTAINS toLower(t)))
        )
        RETURN 
            n.id             AS nodo_origen_id,
            n.nombre         AS nodo_origen_nombre,
            n.text           AS nodo_origen_text,
            properties(n)    AS nodo_origen_props,
            type(r)          AS relacion,
            properties(r)    AS relacion_props,
            m.id             AS nodo_destino_id,
            m.nombre         AS nodo_destino_nombre,
            m.text           AS nodo_destino_text,
            properties(m)    AS nodo_destino_props,
            startNode(r) = n AS es_origen_real
        LIMIT 50
        """
        with self._driver.session() as session:
            result = session.run(
                query    = query_cypher,
                terminos = filtros.terminos_clave
            )

            textos = set()
            for record in result:
                nodo_origen_nombre  = record["nodo_origen_nombre"]
                nodo_origen_props   = record["nodo_origen_props"]
                relacion            = record["relacion"]
                relacion_props      = record["relacion_props"]
                nodo_destino_nombre = record["nodo_destino_nombre"]
                nodo_destino_props  = record["nodo_destino_props"]
                es_origen_real      = record["es_origen_real"]

                textos.add(record["nodo_origen_text"])
                textos.add(record["nodo_destino_text"])

                # Formato de propiedades limpias
                nodo_origen_props_limpias  = self._limpiar_props(props=nodo_origen_props)
                nodo_destino_props_limpias = self._limpiar_props(props=nodo_destino_props)
                relacion_props_limpias     = self._limpiar_props(props=relacion_props) if relacion_props else ""

                if relacion and nodo_destino_nombre:
                    relacion_con_props = f"-[{relacion}{relacion_props_limpias}]->" if relacion_props_limpias else f"-[{relacion}]->"
                    if es_origen_real:
                        contexto_grafo.append(
                            f"({nodo_origen_nombre}{nodo_origen_props_limpias}){relacion_con_props}({nodo_destino_nombre}{nodo_destino_props_limpias})"
                        )
                    else:
                        contexto_grafo.append(
                            f"({nodo_destino_nombre}{nodo_destino_props_limpias}){relacion_con_props}({nodo_origen_nombre}{nodo_origen_props_limpias})"
                        )
                else:
                    contexto_grafo.append(f"Entidad: {nodo_origen_nombre} | Atributos: {nodo_origen_props_limpias}")
        return {
            "contexto_grafo" : list(set(contexto_grafo)),
            "contexto_text"  : list(textos)
        }