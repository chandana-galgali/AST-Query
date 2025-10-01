import ast

class QueryVisitor(ast.NodeVisitor):
    """
    An AST Visitor that finds all nodes matching a parsed query.
    """
    def __init__(self, parsed_query: dict):
        self.parsed_query = parsed_query
        self.matches = []

    def generic_visit(self, node: ast.AST):
        """
        This method is called for every node in the AST.
        """

        # Get the node's class name, e.g., 'FunctionDef'
        node_class_name = type(node).__name__
        
        # Normalize both names to be lowercase and without underscores for a clean comparison
        # 'FunctionDef' -> 'functiondef'
        # 'function_def' -> 'functiondef'
        normalized_node_name = node_class_name.lower()
        normalized_query_name = self.parsed_query['node_type'].replace('_', '')

        # Now, the comparison will work correctly!
        if normalized_node_name == normalized_query_name:
            self.matches.append(node)
            
        # VERY IMPORTANT: This line tells the visitor to continue walking
        # down the tree to visit the children of the current node.
        super().generic_visit(node)