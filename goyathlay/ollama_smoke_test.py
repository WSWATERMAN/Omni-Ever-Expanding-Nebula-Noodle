import ollama

response = ollama.chat(
    model="qwen2.5-coder:7b",
    messages=[
        {
            "role": "system",
            "content": "Return only a Linux command."
        },
        {
            "role": "user",
            "content": "show all listening ports"
        }
    ]
)

print(response["message"]["content"])
