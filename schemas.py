from typing   import List
from pydantic import BaseModel, Field

class FiltrosConsultaGraphRAG(BaseModel):
    terminos_clave: List[str] = Field(
        description="Lista de nombres de entidades, tecnologías, conceptos o propiedades a buscar en el grafo."
    )
