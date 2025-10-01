import os

class DataProcessor:
    def process(self, data):
        if not data:
            return None
        
        for item in data:
            print(f"Processing {item}")
        
        return True

def helper_function():
    pass