from emporium.ingest.pdf_ingest import ingest_policy
from emporium.rag.retriever import PolicyRetriever

from .conftest import RAW_DATA_DIR


async def test_policy_retrieval_returns_relevant_sections(
    engine, session_factory, embedder
) -> None:
    await ingest_policy(engine, embedder, RAW_DATA_DIR)

    retriever = PolicyRetriever(session_factory, embedder)

    results = await retriever.search("qual o horário de funcionamento da loja?")
    assert results, "expected at least one relevant policy chunk"
    assert results[0].section == "2"
    assert "Horário" in results[0].title


async def test_policy_retrieval_filters_unrelated_queries(
    engine, session_factory, embedder
) -> None:
    await ingest_policy(engine, embedder, RAW_DATA_DIR)

    retriever = PolicyRetriever(session_factory, embedder)

    results = await retriever.search("preciso de uma receita de bolo de chocolate vegano")
    assert results == []


async def test_knowledge_retrieval_returns_store_address(
    engine, session_factory, embedder
) -> None:
    await ingest_policy(engine, embedder, RAW_DATA_DIR)

    retriever = PolicyRetriever(session_factory, embedder)

    results = await retriever.search("qual o endereço da loja?")
    assert results, "expected the store address to be retrieved from the knowledge base"
    assert results[0].section == "1.2"
    assert "Rua 14 de Maio" in results[0].text
