from pathlib import Path

import typer

app = typer.Typer(help="Trip advisor backend commands.")


@app.command()
def run_pipeline(site: str = "olumo-rock") -> None:
    """Run collect -> structure -> context -> generate for a site."""
    typer.echo(f"Pipeline for {site} not implemented yet.")


@app.command()
def export_schemas(out: Path = Path("data/schemas")) -> None:
    """Write JSON Schema files for the pack, delta, advice and reports."""
    from trip_advisor.schemas.export import export_schemas as export

    for path in export(out):
        typer.echo(path)


if __name__ == "__main__":
    app()
