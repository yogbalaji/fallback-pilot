"""Present a Brief in the terminal, and as markdown for saving."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from .generate import Brief

TIER_STYLE = {0: "blue", 1: "green", 2: "cyan", 3: "yellow"}


def to_markdown(brief: Brief) -> str:
    out = [f"# Continuity Brief: {brief.topic}", ""]
    out.append(brief.body)
    if brief.draft:
        out += ["", "## Draft message", "", brief.draft]
    out += ["", "## Sources", ""]
    for i, citation in enumerate(brief.sources, start=1):
        used = "" if i in brief.cited else "  (not cited)"
        out.append(f"{i}. {citation}{used}")
    out += [
        "",
        "---",
        f"Generated on-device at tier {brief.tier} ({brief.tier_label}) "
        f"in {brief.seconds:.1f}s"
        + (f" using {brief.model}" if brief.model else "")
        + ". No data left this machine.",
    ]
    for note in brief.notes:
        out.append(f"\n> {note}")
    return "\n".join(out)


def print_brief(brief: Brief, console: Console, already_shown: bool = False) -> None:
    style = TIER_STYLE.get(brief.tier, "white")
    if not already_shown:
        console.print(
            Panel(
                brief.body,
                title=f"Continuity Brief - {brief.topic}",
                subtitle=f"tier {brief.tier} - {brief.tier_label}",
                border_style=style,
            )
        )
    else:
        console.print(
            f"[{style}]tier {brief.tier} - {brief.tier_label}[/]\n"
        )

    if brief.draft and not already_shown:
        console.print(Panel(brief.draft, title="Draft message", border_style="magenta"))

    console.print("[bold]Sources[/]")
    for i, citation in enumerate(brief.sources, start=1):
        mark = "[green]cited[/]" if i in brief.cited else "[dim]not cited[/]"
        console.print(f"  [{i}] {citation}  {mark}")

    if brief.grounded and brief.cited:
        console.print(
            f"\n[green]Every claim traces to your files.[/] "
            f"[dim]{len(brief.cited)} of {len(brief.sources)} sources used.[/]"
        )
    for note in brief.notes:
        console.print(f"[yellow]note:[/] {note}")

    detail = f" using {brief.model}" if brief.model else ""
    console.print(
        f"[dim]{brief.seconds:.1f}s on this device{detail} - nothing left the machine.[/]"
    )
