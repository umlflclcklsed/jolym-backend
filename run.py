import os
import subprocess
import importlib.util
import sys

def load_azure_config():
    """Загружает конфигурацию Azure OpenAI"""
    try:
        # Проверяем, существует ли файл конфигурации
        if os.path.exists('azure_config.py'):
            # Динамически импортируем конфигурацию
            spec = importlib.util.spec_from_file_location("azure_config", "azure_config.py")
            azure_config = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(azure_config)
            print("Azure OpenAI credentials loaded successfully.")
        else:
            print("Warning: azure_config.py not found. Please create it to use Azure OpenAI features.")
    except Exception as e:
        print(f"Error loading Azure OpenAI configuration: {str(e)}")

def main():
    """Загружает конфигурацию и запускает сервер"""
    print("Starting Roadmap API Server...")
    
    # Загружаем конфигурацию Azure OpenAI
    load_azure_config()
    
    # Запускаем сервер с uvicorn
    command = ["uvicorn", "app:app", "--reload"]
    
    try:
        subprocess.run(command)
    except KeyboardInterrupt:
        print("\nServer stopped by user.")

if __name__ == "__main__":
    main() 