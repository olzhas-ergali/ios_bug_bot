import openai
import logging
import os
import asyncio
import time
from services.analyzer.analyzer import LogAnalyzer

api_key = os.getenv("OPENAI_API_KEY")
client = openai.AsyncOpenAI(api_key=api_key)

MAX_INPUT_TOKENS = 4000

async def analyze_file_with_ai(panic_string: str, log_analyzer: LogAnalyzer = None) -> str:
    try:
        if log_analyzer:
            solutions = log_analyzer.find_error_solutions()
            if solutions:
                return "\n".join(solutions[0].get("solutions", []) + "\n\n(Решение найдено в базе)")
        
        panic_string = panic_string[:MAX_INPUT_TOKENS]

        system_prompt = (
            "Ты эксперт по ремонту iPhone. Анализируешь crash-логи и предоставляешь решения. "
            "Формат ответа:\n"
            "МОДЕЛЬ: [модель устройства]\n"
            # "ОШИБКА: [описание ошибки]\n"
            "РЕШЕНИЕ: [конкретные шаги для исправления]"
        )

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": panic_string}
            ],
            max_tokens=500
        )

        if response.choices:
            return response.choices[0].message.content.strip()
        
        return "Решение не найдено в нашей базе. Скоро будет "
        
    except Exception as e:
            return "Решение не найдено в нашей базе. Скоро добавим!"