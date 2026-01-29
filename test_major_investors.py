from app.services.layout_analyzer import get_major_investors_layout
from app.main import app
from fastapi.testclient import TestClient
import json

def test_function_call():
    print("Testing get_major_investors_layout directly...")
    try:
        results = get_major_investors_layout(days=3)
        print(f"Result type: {type(results)}")
        print(f"Result length: {len(results)}")
        if isinstance(results, list):
            print("Successfully returned a list.")
        else:
            print(f"Returned unexpected type: {results}")
    except Exception as e:
        print(f"Function call failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_function_call()
