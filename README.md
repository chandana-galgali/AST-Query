# AST-Query 🐍
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

An interactive command-line tool to query the Abstract Syntax Tree (AST) of Python code using a simple, powerful query language. It's like `grep` or `SQL` for your code's structure.

## The Problem
Static analysis, linting, and codemodding all rely on understanding and navigating a program's Abstract Syntax Tree. However, exploring the AST to find specific structural patterns is often a cumbersome, non-interactive process. AST-Query solves this by providing a simple, declarative language to find the exact nodes you're looking for.

## Key Features
- **Simple Query Language:** Use an intuitive syntax to find nodes (e.g., `find function_def where name="my_func"`).
- **Interactive Highlighting:** Pinpoints and highlights the exact lines of code that match your query in the terminal.
- **Pure Python:** Built with no dependencies outside the standard library, using Python's powerful `ast` module.
- **Educational:** A great tool for learning how Python's internals work and understanding the structure of your own code.

## Installation
```bash
# Clone the repository
git clone [https://github.com/YOUR_USERNAME/ast-query.git](https://github.com/YOUR_USERNAME/ast-query.git)
cd ast-query

# (Optional) It is recommended to use a virtual environment
python -m venv .venv
source .venv/bin/activate
```
## Usage
To run a query, use the following command structure:
```Bash
python ast_query/main.py <path_to_your_file.py> "<your_query>"
```

**Example Queries**
Given a file example.py:
```Python
import os

class DataProcessor:
    def process(self, data):
        if not data:
            return None
        
        for item in data:
            print(f"Processing {item}")
        
        return True
```

**Find all function definitions:**
```Bash
python ast_query/main.py example.py "find function_def"
```

**Find all for loops inside the process function:**
```Bash
python ast_query/main.py example.py "find for_loop inside function_def[name='process']"
```

**Find all function calls:**
```Bash
python ast_query/main.py example.py "find call"
```
