from brain.domains.base_domain import BaseDomain


class GameDomain(BaseDomain):
    keywords = [
        "connect 4", "connect four", "connect-4", "connect4",
        "chess", "checkers", "tic tac toe", "play",
    ]
    valid_actions = ["make_move", "analyze_position", "suggest_move", "explain_move", "load_game"]

    def encode(self, context: dict) -> dict:
        task = str(context.get("task", "")).lower()
        if "chess" in task:
            game_type = "chess"
        elif any(k in task for k in ("connect 4", "connect four", "connect-4", "connect4")):
            game_type = "connect4"
        elif "tic tac toe" in task:
            game_type = "tic_tac_toe"
        else:
            game_type = "unknown"
        return {
            "domain": "game",
            "game_type": game_type,
            "task": task,
        }
