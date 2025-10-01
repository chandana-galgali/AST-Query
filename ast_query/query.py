def parse_query(query_string: str) -> dict:
    """
    Parses a simple query string into a dictionary.
    
    Example:
        "find function_def" -> {'node_type': 'function_def'}
    """
    parts = query_string.strip().lower().split()
    
    if len(parts) == 2 and parts[0] == 'find':
        # The node type is the second part of the query
        return {'node_type': parts[1]}
    else:
        # If the query is not in the format "find <something>", it's invalid.
        raise ValueError(f"Invalid query format: '{query_string}'. Must be 'find <node_type>'.")