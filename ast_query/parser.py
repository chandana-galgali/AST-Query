import ast

def parse_file_to_ast(filepath: str) -> ast.AST:
    """
    Reads a Python file from the given path and returns the root node
    of its Abstract Syntax Tree.
    """
    with open(filepath, 'r') as source_file:
        source_code = source_file.read()
    
    # The magic happens here! ast.parse converts the code string into an AST.
    tree = ast.parse(source_code)
    return tree