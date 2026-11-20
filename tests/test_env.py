import importlib


def test_runtime_dependencies_importable():
    for module in (
        "pydantic",
        "yaml",
        "jsonschema",
        "langgraph",
        "langchain_core",
        "lark_oapi",
        "openai",
        "streamlit",
    ):
        importlib.import_module(module)
