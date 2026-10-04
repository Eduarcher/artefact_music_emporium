from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from emporium.rag.retriever import PolicyRetriever


class KnowledgeSearchInput(BaseModel):
    query: str = Field(description="Natural-language query about the store or its procedures.")


def _format_chunks(chunks) -> str:
    lines = []
    for chunk in chunks:
        lines.append(f"Seção {chunk.section} — {chunk.title}:\n{chunk.text}")
    return "\n\n".join(lines)


def build_knowledge_tool(retriever: PolicyRetriever) -> StructuredTool:
    async def search_knowledge(query: str) -> str:
        chunks = await retriever.search(query)
        if not chunks:
            return "Nenhuma informação relevante encontrada para esta consulta."
        return _format_chunks(chunks)

    return StructuredTool.from_function(
        coroutine=search_knowledge,
        name="search_knowledge",
        description=(
            "Busca na base de conhecimento da Empório da Música por qualquer "
            "informação factual da loja e seus procedimentos: endereço, telefone, "
            "e-mail e demais dados da empresa, horário de funcionamento, formas de "
            "pagamento, trocas e devoluções, frete e entregas, promoções, garantia e "
            "privacidade. Use para responder perguntas sobre regras, procedimentos e "
            "dados institucionais da loja."
        ),
        args_schema=KnowledgeSearchInput,
    )
