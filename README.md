# Motor de Consultas GraphRAG Unificado con Neo4j

> **Descripción:** Motor de consultas GraphRAG sobre un sistema unificado en Neo4j (grafos y vectores integrados). Utiliza un enrutador inteligente que alterna dinámicamente entre estrategias de consulta **Graph-First** y **Vector-First** para optimizar la recuperación.

## 📋 Tabla de Contenidos

* [Visión General](#-visión-general)
* [Arquitectura del Sistema](#-arquitectura-del-sistema)
* [Estrategias de Consulta](#-estrategias-de-consulta)
  * [1. Pipeline Graph-First](#1-pipeline-graph-first)
  * [2. Pipeline Vector-First](#2-pipeline-vector-first)
* [Estructura del Proyecto](#-estructura-del-proyecto)
* [Requisitos Previos](#-requisitos-previos)
* [Instalación y Configuración](#-instalación-y-configuración)
* [Uso](#-uso)
* [Licencia](#-licencia)

## 🔍 Visión General

A diferencia de las soluciones RAG tradicionales o híbridas que separan el almacenamiento de vectores (ej. Pinecone, Chroma) y la base de datos de grafos, este proyecto opera sobre un **sistema unificado en Neo4j**. En esta base de datos, los datos relacionales (nodos, aristas y propiedades) y las representaciones vectoriales (embeddings) conviven dentro de los mismos nodos de la base de datos.

El core del repositorio es un **motor de consultas con enrutador inteligente** que analiza la pregunta del usuario en tiempo real y decide el enfoque óptimo de extracción de contexto antes de enviarlo al Modelo de Lenguaje (LLM).

## 🏗 Arquitectura del Sistema

```
                         [ Pregunta del Usuario ]
                                    │
                                    ▼
                        [ Conmutador / Enrutador ]
                                    │
                       ¿Extrae Filtros/Entidades?
                                /       \
                               /         \
                         (Sí) /           \ (No)
                             /             \
                            ▼               ▼
                 [ Graph-First Pipeline ]  [ Vector-First Pipeline ]
                            │                       │
                            ├─ Búsqueda Cypher      ├─ Vector Index Search
                            ├─ Subgrafo Específico  ├─ Full-Text Search
                            │                       └─ Expansión Relacional
                            \                       /
                             \                     /
                              ▼                   ▼
                           [ Síntesis con LLM (GPT-4o) ]
                                    │
                                    ▼
                            [ Respuesta Final ]
```

## 🔄 Estrategias de Consulta

### 1. Pipeline Graph-First (`consulta_graph_first.py`)

Se activa cuando el enrutador identifica entidades clave, tecnologías o marcas específicas dentro de la pregunta que coinciden con la ontología activa de la base de datos.

* **Mapeo Ontológico Dinámico:** Inspecciona la base de datos en tiempo real (`CALL db.labels()`, `CALL db.relationshipTypes()`) para guiar la extracción de filtros.
* **Consulta Cypher:** Ejecuta consultas dirigidas a propiedades y nombres de entidades para extraer subgrafos y textos fuente asociados de forma precisa.

### 2. Pipeline Vector-First (`consulta_vector_frst.py`)

Se activa cuando la pregunta es conceptual, amplia o no nombra explícitamente entidades existentes en la ontología.

* **Búsqueda Híbrida Semántica + Léxica:** Realiza una búsqueda por similitud vectorial (`VECTOR INDEX`) combinada con un índice de texto completo (`db.index.fulltext`).
* **Expansión Relacional ($N$-Hops):** A partir de las entidades semilla encontradas, realiza un recorrido por el grafo para obtener contexto situacional y relaciones cercanas.

## 📁 Estructura del Proyecto

```
.
├── conmutador_automatico.py   # Enrutador dinámico principal (Conmutador)
├── consulta_graph_first.py    # Pipeline de consulta orientado a entidades/grafo
├── consulta_vector_frst.py    # Pipeline de consulta semántico/vectorial con expansión
├── schemas.py                 # Esquemas Pydantic para salidas estructuradas
├── main.py                    # Interfaz CLI de prueba de consultas
├── environment.yml            # Configuración del entorno de Conda
├── .env.example               # Plantilla de variables de entorno
└── README.md                  # Documentación del proyecto
```

## 🛠 Requisitos Previos

* **Conda:** Anaconda o Miniconda instalado.
* **Neo4j Database:** Instancia local o remota (Neo4j AuraDB) con:
  * Índice vectorial configurado (`entity_embeddings`).
  * Índice Full-Text configurado (`entity_text_index`).
* **OpenAI API Key:** Con acceso a los modelos `gpt-4o-mini` y `text-embedding-3-small`.

## ⚙️ Instalación y Configuración

1. **Clonar el repositorio:**

   ```bash
   git clone https://github.com/DiegoAlejandroLozano/graphrag-consultas-unificadas-neo4j.git
   cd graphrag-consultas-unificadas-neo4j
   ```

2. **Crear y activar el entorno con Conda:**

   Usa el archivo `environment.yml` provisto para reconstruir el entorno con todas sus dependencias:

   ```bash
   conda env create -f environment.yml
   conda activate conda-graphrag-curso
   ```

3. **Configurar variables de entorno:**
   Crea un archivo `.env` en la raíz del proyecto basándote en la plantilla:

   ```env
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=tu_contraseña
   OPENAI_API_KEY=sk-...
   ```

## 🚀 Uso

Para iniciar el sistema de consultas interactivo desde la terminal:

```bash
python main.py
```

**Ejemplo de interacción:**

```text
====================================================================================================
pregunta: ¿Qué tecnologías utiliza Python y cuáles son sus versiones?

Activando Graph-First...

Respuesta: Según la base de conocimientos, Python interactúa con...
```

Para finalizar la ejecución, escribe `salir`.

## 📄 Licencia

Este proyecto está distribuido bajo la licencia MIT.