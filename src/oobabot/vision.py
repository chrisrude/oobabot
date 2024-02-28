import aiohttp

async def get_image_description(image, vision_api_url, vision_api_key, model, max_tokens):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {vision_api_key}"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe the following image in as much detail as possible, including any relevant details while being concise."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image,
                        }
                    }
                ]
            }
        ],
        "max_tokens": max_tokens
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url=vision_api_url, headers=headers, json=payload) as response:
            if response.status == 200:
                data = await response.json()
                if data['choices'] and data['choices'][0]['message']['content']:
                    description = data['choices'][0]['message']['content']
                    return description
                else:
                    return "Description not available."
            else:
                response.raise_for_status()

