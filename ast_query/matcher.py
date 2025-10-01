import ast

class QueryVisitor(ast.NodeVisitor):
    def __init__(self, parsed_query: dict):
        self.parsed_query = parsed_query
        self.matches = []

    def _check_conditions(self, node: ast.AST) -> bool:
        """Helper function to check if a node meets all 'where' conditions."""
        if 'conditions' not in self.parsed_query:
            return True # No conditions to check, so it's a match

        for condition in self.parsed_query['conditions']:
            attr_name = condition['attribute']
            expected_value = condition['value']

            # Check if the node even has the attribute we're looking for
            if not hasattr(node, attr_name):
                return False
            
            # Get the actual value of the attribute from the node
            actual_value = getattr(node, attr_name)

            # Compare the actual value with the expected value
            if str(actual_value).lower() != expected_value:
                return False
        
        # If we get here, all conditions were met
        return True

    def generic_visit(self, node: ast.AST):
        node_class_name = type(node).__name__
        normalized_node_name = node_class_name.lower()
        normalized_query_name = self.parsed_query['node_type'].replace('_', '')

        # First, check if the node type matches.
        if normalized_node_name == normalized_query_name:
            # If the type matches, THEN check the 'where' conditions.
            if self._check_conditions(node):
                self.matches.append(node)
            
        # Continue the traversal down the tree
        super().generic_visit(node)