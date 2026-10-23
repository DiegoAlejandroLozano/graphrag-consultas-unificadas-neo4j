from dotenv                 import dotenv_values
from neo4j                  import GraphDatabase
from langchain_openai       import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from schemas                import FiltrosConsultaGraphRAG
from consulta_graph_first   import PipelineGraphFirst
from consulta_vector_frst   import PipeLineVectorFirst

class Conmutador:

    def __init__(self):
        config = dotenv_values(dotenv_path=".env")

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

        # Conmutador
        openai_key = config.get("OPENAI_API_KEY")
        llm  = ChatOpenAI(
            model       = "gpt-4o-mini",
            temperature = 0.0,
            api_key     = openai_key
        )
        self._llm_extractor_filtros   = llm.with_structured_output(schema=FiltrosConsultaGraphRAG)
        self._ontologia_real          = self._obtener_esquema_ontologico_dinamico()
        self._system_prompt_enrutador = (
            "Eres el motor de enrutamiento y generación de filtros para un sistema GraphRAG.\n"
            "Tu objetivo es analizar la pregunta del usuario y extraer los términos de búsqueda "
            "basándote EXCLUSIVAMENTE en la ontología activa de la base de datos.\n\n"
            f"{self._ontologia_real}\n\n"
            "REGLAS:\n"
            "1. Extrae únicamente entidades, tecnologías, creadores o versiones exactas que coincidan con la pregunta.\n"
            "2. IMPORTANTE: Si la pregunta es conceptual, general o no nombra explícitamente una entidad o tecnología del esquema, DEBES dejar la lista de términos clave completamente vacía ([]) para activar la búsqueda vectorial."
        )

        # Pipelines
        self._pipelineGraphFirst  = PipelineGraphFirst()
        self._pipelineVectorFirst = PipeLineVectorFirst()

    def __call__(self, pregunta:str) -> str:
        filtros = self._extractor_filtros_desde_pregunta(pregunta=pregunta)
        # Se evalua si hay contexto o entidades válidas
        if filtros.terminos_clave:
            print("\nActivando Graph-First...")
            respuesta = self._pipelineGraphFirst(pregunta=pregunta, filtros=filtros)
        else:
            print("\nActivando Vector-First...")
            respuesta = self._pipelineVectorFirst(consulta_usuario=pregunta, top_k=10, max_hops=2)
        return respuesta

    def close(self):
        self._driver.close()  
        self._pipelineGraphFirst.close()
        self._pipelineVectorFirst.close()

    def _obtener_esquema_ontologico_dinamico(self):
        """
        Inspecciona la base de datos Neo4j en tiempo real para construir 
        el mapa exacto de etiquetas, relaciones y propiedades disponibles.
        """
        with self._driver.session() as session:
            # Obtener todas las etiquetas de nodos (labels)
            res_labels = session.run("CALL db.labels()")
            labels     = [r[0] for r in res_labels]

            # Obtener todos los tipos de relaciones
            res_rels = session.run("CALL db.relationshipTypes()")
            rels     = [r[0] for r in res_rels]

            # Obtener una muestra de claves de propiedades usadas en nodos
            res_props_nodos = session.run("""
                MATCH (n)
                UNWIND keys(n) AS k
                RETURN DISTINCT k
            """)
            props_nodos = [r[0] for r in res_props_nodos]

            # Obtener claves de propiedades usadas en relaciones
            res_props_rels = session.run("""
                MATCH ()-[r]->()
                UNWIND keys(r) AS k
                RETURN DISTINCT k
            """)
            props_rels = [r[0] for r in res_props_rels]

            # Formatear como un bloque de texto claro para el Prompt
            esquema_texto = (
                f"ESQUEMA REAL EXTRAÍDO DE NEO4J:\n"
                f"- Etiquetas de Nodos Disponibles: {', '.join(labels)}\n"
                f"- Tipos de Relaciones Existentes: {', '.join(rels)}\n"
                f"- Claves de Propiedades Frecuentes: {', '.join(props_nodos)}\n"
                f"- Claves de Propiedades de Relaciones: {', '.join(props_rels)}"
            )

            return esquema_texto

    def _extractor_filtros_desde_pregunta(self, pregunta) -> FiltrosConsultaGraphRAG:
        prompt = ChatPromptTemplate([
            ("system", self._system_prompt_enrutador),
            ("human", "{pregunta}")
        ])
        chain = prompt | self._llm_extractor_filtros
        return chain.invoke(input={"pregunta":pregunta})