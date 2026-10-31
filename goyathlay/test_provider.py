from providers.ollama_provider import OllamaProvider

provider = OllamaProvider(
    model="qwen2.5-coder:7b"
)

command = provider.generate_command(
    "show listening ports"
)

print("Generated Command:")
print(command)
