import os

"""
Этот файл содержит настройки для подключения к Azure OpenAI.
Заполните информацию ниже вашими данными из Azure OpenAI сервиса.
"""

# ================================
# НАСТРОЙТЕ ЭТИ ЗНАЧЕНИЯ!
# ================================

# Ключ API Azure OpenAI
os.environ["AZURE_OPENAI_API_KEY"] = ""

# Конечная точка Azure OpenAI, например: https://YOUR_RESOURCE_NAME.openai.azure.com/
os.environ["AZURE_OPENAI_ENDPOINT"] = ""

# Название deployment для модели эмбеддингов (обычно text-embedding-ada-002)
os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"] = "text-embedding-ada-002"

# Название deployment для модели чата (например, gpt-4, gpt-35-turbo)
os.environ["AZURE_OPENAI_DEPLOYMENT_NAME_CHAT"] = "gpt-4"

# Версия API
os.environ["AZURE_OPENAI_API_VERSION"] = "2023-05-15"

# ================================
# Дополнительные настройки
# ================================

# Отключаем Redis (использовать память для кеширования)
os.environ["REDIS_ENABLED"] = "false"

print("Azure OpenAI configuration loaded.")
print("Tip: Fill in your credentials in azure_config.py file.") 