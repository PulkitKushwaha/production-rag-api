from setuptools import setup, find_packages
 
setup(
    name="production-rag-api",
    version="0.1.0",
    author="Pulkit Kushwaha",
    author_email="pulkitkushwahadev@gmail.com",
    description="Production-grade RAG API: FastAPI, async endpoints, auth, rate limiting, Docker, and CI/CD",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "fastapi>=0.110.1",
        "uvicorn[standard]>=0.29.0",
        "pydantic>=2.6.4",
        "openai>=1.14.0",
        "langchain>=0.1.20",
    ],
)
