import re

from dotenv                 import dotenv_values
from neo4j                  import GraphDatabase
from langchain_openai       import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from typing                 import Dict, Any

class PipeLineVectorFirst:

    def __init__(self):
        config = dotenv_values(dotenv_path=".env")

        # Neoj
        self._neoj_driver = GraphDatabase.driver(
            uri  = config.get("NEO4J_URI"),
            auth = (
                config.get("NEO4J_USER"),
                config.get("NEO4J_PASSWORD")
            )
        )

        # LLM para sintetizar la respuesta final
        self._llm = ChatOpenAI(
            model       = "gpt-4o-mini",
            temperature = 0.0,
            api_key     = config.get("OPENAI_API_KEY")
        )

        self._embeddings = OpenAIEmbeddings(
            api_key = config.get("OPENAI_API_KEY"),
            model   = "text-embedding-3-small"
        )

    def _obtener_contexto_vector_y_grago(
        self,
        consulta_usuario : str,
        top_k            : int = 3,
        max_hops         : int = 1
    ) -> Dict[str, Any]:
        vector_query = self._embeddings.embed_query(text=consulta_usuario)

        palabras_ignorar = {"el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o", "de", "del", "a", "en", "por", "para", "con", "sin", "sobre", "entre", "que", "cual", "cuales", "como", "es", "son", "sus"}
        palabras_limpias = [
            p.lower() for p in re.findall(r'\w+', consulta_usuario, re.UNICODE)
            if p.lower() not in palabras_ignorar and len(p) > 2
        ]
        query_lucene = " OR ".join(palabras_limpias) if palabras_limpias else consulta_usuario

        query        = f"""
        // 1. Búsqueda semántica por Vector
        MATCH (s_vec:Entidad)
        SEARCH s_vec IN (
            VECTOR INDEX entity_embeddings FOR $query_vector
            LIMIT $top_k
        ) SCORE AS score_vec

        // 2. Búsqueda léxica por Texto Completo (Full-Text)
        CALL db.index.fulltext.queryNodes("entity_text_index", $query_lucene)
        YIELD node AS s_txt, score AS score_txt

        // Unificar ambos conjuntos de nodos encontrado (Semántico + Texto)
        WITH collect(DISTINCT s_vec) + collect(DISTINCT s_txt) AS nodos_combinados
        UNWIND nodos_combinados AS s

        // Limpiar para evitar explosión combinatoria si hay muchos resultados
        WITH DISTINCT s
        LIMIT $top_k_doble

        // Recolectar semillas iniciales
        WITH collect({{
            id     : s.id,
            nombre : s.nombre,
            text   : s.text
        }}) AS semillas, collect(s) AS nodos_semilla

        // 3. Expansión del subgrafo relacional a partir de las semillas encontradas
        UNWIND nodos_semilla AS s
        OPTIONAL MATCH path = (s)-[*1..{max_hops}]->(o:Entidad)
        WITH semillas, s, path
        UNWIND (CASE WHEN path IS NULL THEN [null] ELSE relationships(path) END) AS r

        WITH semillas, s, r, endNode(r) AS obj
        WHERE r IS NOT NULL

        RETURN 
            semillas,
            collect(DISTINCT {{
                sujeto           : s.nombre,
                props_sujeto     : properties(s),
                relacion         : type(r),
                props_relacion   : properties(r),
                objeto           : obj.nombre,
                props_objeto     : properties(obj),
                etiquetas_sujeto : labels(s),
                etiquetas_objeto : labels(obj)
            }}) AS subgrafo_raw
        """
        with self._neoj_driver.session() as session:
            result = session.run(
                query        = query, 
                query_vector = vector_query, 
                query_lucene = query_lucene,
                top_k        = top_k,
                top_k_doble  = 2 * top_k
            ).single()

            if not result or not result["semillas"]:
                return {"entidades":[], "subgrafo":[]}

            entidades = result["semillas"]
            # filtrar valores nulos si alguna entidad semilla no tiene relaciones
            subgrago_raw = [r for r in result["subgrafo_raw"] if r is not None]

            tripletas_contexto = []
            for r in subgrago_raw:
                props_sub = {k: v for k, v in r["props_sujeto"].items() if k not in ["id", "nombre", "vector", "text"]}
                props_obj = {k: v for k, v in r["props_objeto"].items() if k not in ["id", "nombre", "vector", "text"]}

                tripletas_contexto.append({
                    "sujeto"           : r["sujeto"],
                    "props_sujeto"     : props_sub,
                    "relacion"         : r["relacion"],
                    "props_relacion"   : r["props_relacion"],
                    "objeto"           : r["objeto"],
                    "props_objeto"     : props_obj,
                    "etiquetas_sujeto" : r["etiquetas_sujeto"],
                    "etiquetas_objeto" : r["etiquetas_objeto"]
                })

            return {
                "entidades" : entidades,
                "subgrafo"  : tripletas_contexto
            }

    def __call__(self, consulta_usuario:str, top_k:int=3, max_hops:int=1) -> str:
        contexto = self._obtener_contexto_vector_y_grago(
            consulta_usuario = consulta_usuario,
            top_k            = top_k,
            max_hops         = max_hops
        )

        entidades_iniciales = contexto["entidades"]
        subgrafo            = contexto["subgrafo"]

        texto_contexto_documentos = ""
        for ent in entidades_iniciales:
            # Acumular el texto recuperado de las entidades
            if ent.get("text") and ent.get("text") not in texto_contexto_documentos:
                texto_contexto_documentos += f"### Entidad: {ent['nombre']}\n{ent['text']}\n\n"
        if not texto_contexto_documentos:
            texto_contexto_documentos = "No hay fragmentos de texto detallados disponibles."

        texto_contexto_relaciones = ""
        for i, t in enumerate(subgrafo, 1):
            lbl_sujeto = ":".join(t.get("etiquetas_sujeto", []))
            lbl_objeto = ":".join(t.get("etiquetas_objeto", []))

            str_sujeto = f"{t['sujeto']}:{lbl_sujeto}" if lbl_sujeto else t['sujeto']
            str_objeto = f"{t['objeto']}:{lbl_objeto}" if lbl_objeto else t['objeto']

            p_sub = f" {t['props_sujeto']}" if t['props_sujeto'] else ""
            p_rel = f" {t['props_relacion']}" if t['props_relacion'] else ""
            p_obj = f" {t['props_objeto']}" if t['props_objeto'] else ""

            linea = f"({str_sujeto}{p_sub})--[{t['relacion']}{p_rel}]-->({str_objeto}{p_obj})"
            texto_contexto_relaciones += f"- {linea}\n"

        if not texto_contexto_relaciones:
            texto_contexto_relaciones = "No se encontraron relaciones directas en el grafo."

        # Generar respuesta con RAG
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", (
                "Eres un asistente virtual experto respaldado por un Grafo de Conocimiento y "
                "una base de documentos.\n"
                "Responde a la pregunta del usuario utilizando ÚNICAMENTE la información proporcionada "
                "en los fragmentos de texto y las relaciones estructurales del grafo.\n"
                "REGLA DE ORO: Si la información no está presente en el contexto para responder de forma "
                "completa, responde de manera amable, cordial y natural indicando que no dispones de esa "
                "información en tu base de conocimientos actual, sin hacer referencias técnicas a 'fragmentos de texto', "
                "'vectores' o 'metadatos'."
            )),
            ("human", (
                "Pregunta del usuario: {pregunta}\n\n"
                "--- FRAGMENTOS DE TEXTO RECUPERADOS ---\n"
                "{contexto_textos}\n\n"
                "--- SUBGRAFO DE RELACIONES (Neo4j) ---\n"
                "{contexto_relaciones}\n\n"
                "Respuesta estructurada y clara:"
            ))
        ])

        chain     = prompt_template | self._llm
        respuesta = chain.invoke(input={
            "pregunta"            : consulta_usuario,
            "contexto_textos"     : texto_contexto_documentos,
            "contexto_relaciones" : texto_contexto_relaciones
        })

        return respuesta.content

    def close(self):
        self._neoj_driver.close()
