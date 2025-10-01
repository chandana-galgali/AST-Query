import sys
from .parser import parse_file_to_ast
from .query import parse_query
from .matcher import QueryVisitor

def main():
    if len(sys.argv) != 3:
        print("Usage: python ast_query/main.py <file_path> \"<query>\"")
        sys.exit(1)

    # 1. Get arguments from the command line
    file_path = sys.argv[1]
    query_string = sys.argv[2]
    
    try:
        # 2. Parse the Python code into an AST
        ast_tree = parse_file_to_ast(file_path)
        
        # 3. Parse the user's query string
        parsed_query = parse_query(query_string)
        
        # 4. Find matches in the AST
        visitor = QueryVisitor(parsed_query)
        visitor.visit(ast_tree) # This starts the AST traversal
        
        # 5. Print the results
        print(f"Found {len(visitor.matches)} match(es) for your query: '{query_string}'\n")
        for node in visitor.matches:
            # Every node in the AST has a line number attribute
            print(f"- Found a '{type(node).__name__}' node on line {node.lineno}")

    except FileNotFoundError:
        print(f"Error: File not found at '{file_path}'")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()