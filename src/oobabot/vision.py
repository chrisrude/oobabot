import aiohttp

async def get_image_description(image, vision_api_url, vision_api_key, vision_api_model):
    if image.startswith('http'):
        image_data = image
    else:
        image_data = f"data:image/jpeg;base64,{image}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {vision_api_key}"
    }

    payload = {
        "model": vision_api_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe the following image. Be as descriptive as possible and include any relevant details while being concise."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data,
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300
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

