import sys
import os
sys.path.append(os.getcwd())
try:
    from app.services.layout_analyzer import get_major_investors_layout
except ImportError:
    # If running from inside app, handle upwards
    sys.path.append(os.path.dirname(os.getcwd()))
    from app.services.layout_analyzer import get_major_investors_layout

def test_function_call():
    print("Testing get_major_investors_layout directly...")
    try:
        results = get_major_investors_layout(days=3)
        print(f"Result type: {type(results)}")
        print(f"Result length: {len(results)}")
        
        if isinstance(results, list):
            print("SUCCESS: Returned a list.")
            import json
            try:
                json_str = json.dumps(results)
                print("SUCCESS: Result indicates valid JSON serialization.")
            except TypeError as te:
                print(f"FAILURE: JSON serialization failed: {te}")
        else:
            print(f"FAILURE: Returned unexpected type: {type(results)}")
            
    except Exception as e:
        print(f"FAILURE: Function call failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_function_call()
