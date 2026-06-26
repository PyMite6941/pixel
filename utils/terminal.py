import shutil
import time
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console as _RichConsole
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.table import Table
    from rich.syntax import Syntax
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich import box
    _RICH = True
    _console = _RichConsole()
except ImportError:
    _RICH = False
    _console = None


_TERM_WIDTH = shutil.get_terminal_size().columns


def _line(c: str = "─", color: str = "") -> str:
    return c * _TERM_WIDTH


def banner() -> None:
    w = min(_TERM_WIDTH, 72)
    tagline = "security-first | self-aware | local-first AI assistant"
    sep = "─" * w

    if _RICH:
        from rich.text import Text as RichText
        from rich.panel import Panel as RichPanel
        logo = RichText(
            "  ____ _ _   _ _     \n"
            " |  _ (_) | | | |    \n"
            " | |_) | | | | | |   \n"
            " |  __/| | |_| | |___\n"
            " |_|   |_|\\___/|_____|",
            style="bold cyan",
        )
        grid = Table.grid(padding=0)
        grid.add_column(justify="center", width=w)
        grid.add_row(logo)
        grid.add_row(RichText(tagline, style="dim white", justify="center"))
        _console.print(RichPanel(grid, box=box.MINIMAL, border_style="cyan"))
        _console.print()
    else:
        logo_ascii = (
            "  ____ _ _   _ _     \n"
            " |  _ (_) | | | |    \n"
            " | |_) | | | | | |   \n"
            " |  __/| | |_| | |___\n"
            " |_|   |_|\\___/|_____|"
        )
        for line in logo_ascii.split("\n"):
            print(f"\033[1;36m{line.center(w)}\033[0m")
        print(f"  \033[3;90m{tagline}\033[0m".center(w))
        print(f"  {sep}")
        print()


def user_message(text: str) -> None:
    ts = datetime.now().strftime("%H:%M")
    if _RICH:
        _console.print(Panel(
            Text(text),
            title=f"[bold yellow]You[/bold yellow]  [{ts}]",
            title_align="left",
            border_style="yellow",
            padding=(0, 1),
        ))
    else:
        print(f"\n\033[1;33m  You\033[0m  \033[90m[{ts}]\033[0m")
        print(f"\033[33m  {_line('─')}\033[0m")
        for line in text.split("\n"):
            print(f"  {line}")
        print(f"\033[33m  {_line('─')}\033[0m")


def stream_assistant_start() -> None:
    if _RICH:
        _console.print(Panel(
            Text("..."),
            title="[bold cyan]Pixel[/bold cyan]",
            title_align="left",
            border_style="cyan",
            padding=(0, 1),
        ))


def assistant_message(text: str) -> None:
    ts = datetime.now().strftime("%H:%M")
    if _RICH:
        try:
            md = Markdown(text)
        except Exception:
            md = Text(text)
        _console.print(Panel(
            md,
            title=f"[bold cyan]Pixel[/bold cyan]  [{ts}]",
            title_align="left",
            border_style="cyan",
            padding=(0, 1),
        ))
    else:
        print(f"\n\033[1;36m  Pixel\033[0m  \033[90m[{ts}]\033[0m")
        print(f"\033[36m  {_line('─')}\033[0m")
        for line in text.split("\n"):
            print(f"  {line}")
        print(f"\033[36m  {_line('─')}\033[0m")
    print()


def info(text: str) -> None:
    if _RICH:
        _console.print(f"[dim]*[/dim] {text}")
    else:
        print(f"  \033[2m*\033[0m {text}")


def success(text: str) -> None:
    if _RICH:
        _console.print(f"[bold green]+[/bold green] {text}")
    else:
        print(f"  \033[1;32m+\033[0m {text}")


def warn(text: str) -> None:
    if _RICH:
        _console.print(f"[bold yellow]![/bold yellow] {text}")
    else:
        print(f"  \033[1;33m!\033[0m {text}")


def error(text: str) -> None:
    if _RICH:
        _console.print(f"[bold red]x[/bold red] {text}")
    else:
        print(f"  \033[1;31mx\033[0m {text}")


def status_enter(text: str) -> None:
    if _RICH:
        _console.print(f"[dim]{text}...[/dim]")
    else:
        print(f"  \033[2m{text}...\033[0m")


def status_done(text: str) -> None:
    if _RICH:
        _console.print(f"[green]+[/green] {text}")
    else:
        print(f"  \033[32m+\033[0m {text}")


def command_table(items: list[tuple[str, str]], title: str = "") -> None:
    if _RICH:
        table = Table(title=title, box=box.SIMPLE, border_style="cyan")
        table.add_column("Command", style="bold cyan", no_wrap=True)
        table.add_column("Description", style="white")
        for cmd, desc in items:
            table.add_row(cmd, desc)
        _console.print(table)
    else:
        if title:
            print(f"\n  \033[1;36m{title}\033[0m")
        for cmd, desc in items:
            print(f"  \033[1;33m{cmd:<20}\033[0m {desc}")


def skill_table(skills: dict) -> None:
    if _RICH:
        table = Table(box=box.SIMPLE, border_style="cyan")
        table.add_column("Skill", style="bold cyan", no_wrap=True)
        table.add_column("Description", style="white")
        table.add_column("Auto-Triggers", style="dim")
        for name, skill in skills.items():
            triggers = getattr(skill, 'auto_triggers', [])
            trigger_str = ", ".join(triggers[:3]) + ("..." if len(triggers) > 3 else "") if triggers else "—"
            table.add_row(name, skill.description, trigger_str)
        _console.print(table)
    else:
        print(f"\n  \033[1;36mSkills\033[0m")
        for name, skill in skills.items():
            triggers = getattr(skill, 'auto_triggers', [])
            t_str = f" \033[2m[{', '.join(triggers[:2])}...]\033[0m" if triggers else ""
            print(f"  \033[1;33m{name}\033[0m: {skill.description}{t_str}")


def memory_table(memory: dict) -> None:
    if _RICH:
        table = Table(box=box.SIMPLE, border_style="yellow")
        table.add_column("Key", style="bold yellow")
        table.add_column("Value", style="white")
        for k, v in memory.items():
            table.add_row(str(k), str(v))
        _console.print(table)
    else:
        for k, v in memory.items():
            print(f"  \033[1;33m{k}\033[0m: {v}")


def secrets_table(secrets: list[dict]) -> None:
    if _RICH:
        table = Table(box=box.SIMPLE, border_style="red")
        table.add_column("Type", style="bold red")
        table.add_column("File", style="dim")
        for s in secrets:
            table.add_row(s["type"], s.get("file", s.get("preview", "")))
        _console.print(table)
    else:
        for s in secrets:
            print(f"  \033[1;31m[{s['type']}]\033[0m {s.get('file', s.get('preview', ''))}")


def goodbye() -> None:
    if _RICH:
        _console.print()
        _console.print(Panel(
            "[dim]session ended[/dim]",
            border_style="cyan",
            box=box.MINIMAL,
        ))
    else:
        print(f"\n  \033[36m{_line('─')}\033[0m")
        print("  \033[3;90msession ended\033[0m")
