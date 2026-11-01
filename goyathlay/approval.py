"""Interactive approval gate for AI-generated shell commands."""


class ApprovalManager:
    """Ask the user to approve, edit, or cancel a command."""

    def review(self, command: str, display_command: bool = True) -> tuple[bool, str | None]:
        """Return an approved command, or ``(False, None)`` when canceled.

        Invalid selections are prompted again. An empty edited command is
        treated as cancellation so it cannot be mistaken for approval.
        """
        print("-" * 36)
        print("GOYATHLAY COMMAND REVIEW" if display_command else "GOYATHLAY EXECUTION APPROVAL")
        print("-" * 36)
        print()
        if display_command:
            print("Generated Command:")
            print()
            print(command)
            print()
        if not display_command:
            print("Approve execution for this request?")
        print("[A] Approve")
        print("[E] Edit")
        print("[C] Cancel")
        print()

        while True:
            selection = input("Selection: ").strip().casefold()

            if selection in ("a", "approve"):
                return True, command
            if selection in ("e", "edit"):
                edited_command = input("Edit Command: ").strip()
                if not edited_command:
                    return False, None
                return True, edited_command
            if selection in ("c", "cancel"):
                return False, None

            print("Please enter A (Approve), E (Edit), or C (Cancel).")
