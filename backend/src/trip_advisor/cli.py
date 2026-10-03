import typer

app = typer.Typer(help="Trip advisor backend commands.")


@app.command()
def run_pipeline(site: str = "olumo-rock") -> None:
    """Run collect -> structure -> context -> generate for a site."""
    typer.echo(f"Pipeline for {site} not implemented yet.")


if __name__ == "__main__":
    app()
