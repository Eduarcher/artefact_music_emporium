from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from emporium.rag.retriever import PolicyRetriever


class SearchPoliciesInput(BaseModel):
    query: str = Field(description="Natural-language query about store policies or procedures.")


def _format_chunks(chunks) -> str:
    lines = []
    for chunk in chunks:
        lines.append(f"Seção {chunk.section} — {chunk.title}:\n{chunk.text}")
    return "\n\n".join(lines)


def build_policy_tool(retriever: PolicyRetriever) -> StructuredTool:
    async def search_policies(query: str) -> str:
        chunks = await retriever.search(query)
        if not chunks:
            return "Nenhuma política relevante encontrada para esta consulta."
        return _format_chunks(chunks)

    return StructuredTool.from_function(
        coroutine=search_policies,
        name="search_policies",
        description=(
            "Busca nas políticas internas da loja (horário de funcionamento, formas de "
            "pagamento, trocas e devoluções, frete e entregas, promoções, garantia e "
            "privacidade). Use para responder perguntas sobre regras e procedimentos."
        ),
        args_schema=SearchPoliciesInput,
    )
