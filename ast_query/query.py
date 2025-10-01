import re

def parse_query(query_string: str) -> dict:
    """
    Parses a query string with a 'where' clause into a dictionary.
    
    Example:
        "find function_def where name='process'" 
        -> {'node_type': 'function_def', 'conditions': [{'attribute': 'name', 'value': 'process'}]}
    """
    # Use a regular expression to find the main parts of the query
    # This is more robust than splitting by spaces.
    match = re.search(r"find\s+(\w+)(?:\s+where\s+([\w\.]+)\s*=\s*'(\w+)')?", query_string.strip().lower())
    
    if not match:
        raise ValueError(f"Invalid query format: '{query_string}'")

    node_type = match.group(1)
    attribute = match.group(2)
    value = match.group(3)
    
    query_dict = {'node_type': node_type}
    
    if attribute and value:
        query_dict['conditions'] = [{'attribute': attribute, 'value': value}]
        
    return query_dict