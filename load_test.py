import asyncio
import aiohttp
import time

async def send_message(session, url, data):
    start_time = time.time()
    try:
        async with session.post(url, json=data) as response:
            response_text = await response.text()
            latency = time.time() - start_time
            print(f"Response: {response_text}, Latency: {latency:.2f} seconds")
            return response_text
    except Exception as e:
        print(f"Request failed: {e}")

async def main():
    url = "http://localhost:8000/bot"  # Замените на URL вашего бота
    data = {"update_id": 1, "message": {"chat": {"id": 12345}, "text": "/start"}}
    tasks = []

    async with aiohttp.ClientSession() as session:
        for _ in range(100):  # Отправляем 100 запросов одновременно
            task = asyncio.ensure_future(send_message(session, url, data))
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

asyncio.run(main())
