#!/usr/bin/env python3

from providers.ollama_provider import OllamaProvider

def main():

    provider = OllamaProvider()

    print()
    print("Goyathlay")
    print("Local-Only AI Shell")
    print("Type 'exit' to quit")
    print()

    while True:

        prompt = input("goyathlay> ").strip()

        if prompt.lower() in ("exit", "quit"):
            break

        if not prompt:
            continue

        try:
            command = provider.generate_command(prompt)

            print()
            print("Generated Command:")
            print(command)
            print()

        except Exception as ex:
            print(f"ERROR: {ex}")

if __name__ == "__main__":
    main()
