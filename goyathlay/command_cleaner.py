def clean_command(text: str) -> str:

    text = text.strip()

    text = text.replace("```bash", "")
    text = text.replace("```", "")

    return text.strip()
