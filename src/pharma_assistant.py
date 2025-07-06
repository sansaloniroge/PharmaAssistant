import os
import pandas as pd
from config import DevConstants, ProdConstants
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Environment initialization
IS_PROD = os.getenv("IS_PROD", "").lower() in ("1", "true", "yes")
CONFIG = ProdConstants() if IS_PROD else DevConstants()


class PharmaAssistant:
    def __init__(self):
        """Initialize with validated configuration"""
        self._validate_environment()
        self.embeddings = self._create_embeddings()
        self.vector_store = self._load_or_create_vectorstore()
        self.qa_chain = self._create_qa_chain()

    def _validate_environment(self) -> None:
        """Ensure all required resources are available"""
        try:
            CONFIG.validate_paths()
            # Test API key access
            if not CONFIG.OPENAI_API_KEY:
                raise ValueError("API key could not be loaded")
        except Exception as e:
            raise RuntimeError(f"Configuration error: {str(e)}")

    def _create_embeddings(self) -> OpenAIEmbeddings:
        """Initialize embeddings with environment-aware API key"""
        return OpenAIEmbeddings(
            model=CONFIG.EMBEDDING_MODEL,
            api_key=CONFIG.OPENAI_API_KEY
        )

    def _load_or_create_vectorstore(self) -> FAISS:
        """Smart loader for FAISS index"""
        if list(CONFIG.FAISS_INDEX_DIR.glob("*.faiss")):
            print("Loading existing vector store...")
            return FAISS.load_local(
                CONFIG.FAISS_INDEX_DIR,
                self.embeddings,
                allow_dangerous_deserialization=True
            )

        print("Creating new vector store...")

        df = pd.read_csv(CONFIG.DATA_PATH)
        records = []

        for _, row in df.iterrows():
            content = row["Características"]
            metadata = row.drop("Características").to_dict()
            metadata["source"] = CONFIG.DATA_PATH.name  # Añade el nombre del archivo como fuente
            records.append(Document(page_content=content, metadata=metadata))

        # Chunking
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = splitter.split_documents(records)

        # Embed and store
        db = FAISS.from_documents(chunks, self.embeddings)
        db.save_local(CONFIG.FAISS_INDEX_DIR)
        return db

    def _create_qa_chain(self) -> RetrievalQA:
        """Configure QA system with safety checks"""
        llm = ChatOpenAI(
            temperature=0,
            model_name=CONFIG.LLM_MODEL,
            api_key=CONFIG.OPENAI_API_KEY,
            max_retries=3  # Auto-retry on API errors
        )
        return RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=self.vector_store.as_retriever(search_kwargs={"k": 3}),
            return_source_documents=True,
            verbose=True
        )

    def query(self, question: str) -> dict:
        """Execute query with error handling"""
        try:
            result = self.qa_chain.invoke({"query": question})
            return {
                "answer": result["result"],
                "sources": [doc.metadata for doc in result["source_documents"]]
            }
        except Exception as e:
            return {"error": f"Query failed: {str(e)}"}


def main():
    print("=== Pharma Assistant ===")
    assistant = PharmaAssistant()

    while True:
        try:
            question = input("\nYour question (or 'quit'): ").strip()
            if question.lower() in ('quit', 'exit'):
                break

            response = assistant.query(question)

            if "error" in response:
                print(f"❌ Error: {response['error']}")
            else:
                print(f"\n✅ Answer: {response['answer']}")
                print("\n📚 Sources:")
                for src in response["sources"]:
                    print(f"- {src.get('source', 'Unknown')}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()