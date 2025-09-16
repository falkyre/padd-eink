import logging
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ProgressBar, Rule, Link, Button
from textual.containers import VerticalScroll, Container, Center, Vertical, Horizontal
from textual.screen import ModalScreen
from textual import work
from rich.emoji import Emoji

from . import (
    format_uptime,
    compare_versions,
    generate_ascii_bar,
    heatmap_generator,
    generate_qrascii,
)

logger = logging.getLogger(__name__)


# --- Textual TUI Widgets ---
class PiHoleStats(Static):
    """A widget to display Pi-hole statistics."""

    def on_mount(self) -> None:
        """Set the border title when the widget is mounted."""
        self.border_title = "Pi-hole Stats"
        self.styles.border = ("heavy", "white")
        self.styles.border_title_align = "center"

    def update_content(self, padd_data: dict) -> None:
        """Formats and updates the widget's content."""
        if padd_data.get("error"):
            self.update(f"[bold red]{padd_data['error']}[/]")
            return
        if not padd_data:
            self.update("No Pi-hole data available.")
            return

        data = padd_data
        queries = data.get("queries", {})
        percent_blocked = queries.get("percent_blocked", 0.0)

        # Generate the ASCII bar
        ascii_bar = generate_ascii_bar(percent_blocked, total_width=40)

        lines = [
            f"[bold]Blocking:[/bold]   {data.get('gravity_size', 0):,}",
            f"[bold]Piholed:[/bold]    {ascii_bar} {percent_blocked:.1f}%",
            f"[bold]Queries:[/bold]    {queries.get('blocked', 0):,} out of {queries.get('total', 0):,}",
            f"[bold]Latest:[/bold]     {data.get('recent_blocked', 'N/A')}",
            f"[bold]Top Ad:[/bold]     {data.get('top_blocked', 'N/A')}",
            f"[bold]Top Domain:[/bold] {data.get('top_domain', 'N/A')}",
            f"[bold]Top Client:[/bold] {data.get('top_client', 'N/A')}",
            f"[bold]Clients:[/bold]    {data.get('active_clients', 0)}",
        ]
        self.update("\n".join(lines))


class SystemStats(Static):
    """A widget to display system statistics."""

    def on_mount(self) -> None:
        self.border_title = "System Stats"
        self.styles.border = ("panel", "blue")
        self.styles.border_title_align = "center"

    def update_content(self, padd_data: dict) -> None:
        if not padd_data or padd_data.get("error"):
            self.update("")  # Clear on error
            return

        data = padd_data
        system = data.get("system", {})

        # Generate the ASCII bar for CPU
        cpu_per = system.get("cpu", {}).get("%cpu", [0.0])
        cpu_bar = generate_ascii_bar(cpu_per, total_width=40)
        cpu_color = heatmap_generator(cpu_per)

        # Generate the ASCII bar for Memory
        mem_load = system.get("memory", {}).get("ram", {}).get("%used", 0.0)
        mem_bar = generate_ascii_bar(mem_load, total_width=40)
        mem_color = heatmap_generator(mem_load)

        # CPU temperature colors
        cpu_temp = data.get("sensors", {}).get("cpu_temp", 0.0)

        if cpu_temp > 80:
            cpu_emoji = str(Emoji("thumbs_down")) + " " + str(Emoji("fire"))
        elif cpu_temp >= 60:
            cpu_emoji = str(Emoji("thumbs_up")) + " " + str(Emoji("thermometer"))
        else:
            cpu_emoji = str(Emoji("thumbs_up")) + " " + str(Emoji("ok_hand"))

        color = heatmap_generator(cpu_temp)

        cpu_load_1 = system.get("cpu", {}).get("load", {}).get("raw", [0.0])[0]
        cpu_load_1_color = heatmap_generator(cpu_load_1)
        cpu_load_5 = system.get("cpu", {}).get("load", {}).get("raw", [0.0])[1]
        cpu_load_5_color = heatmap_generator(cpu_load_5)
        cpu_load_15 = system.get("cpu", {}).get("load", {}).get("raw", [0.0])[2]
        cpu_load_15_color = heatmap_generator(cpu_load_15)

        lines = [
            f"[bold]Host:[/bold]       {data.get('node_name', 'N/A')} ({data.get('iface', {}).get('v4', {}).get('addr', 'N/A')})",
            f"[bold]CPU Used:[/bold]   {cpu_bar} [{cpu_color}]{cpu_per:.1f}%[/{cpu_color}]",
            f"[bold]CPU Load:[/bold]   [{cpu_load_1_color}]{cpu_load_1:.2f}[/{cpu_load_1_color}], [{cpu_load_5_color}]{cpu_load_5:.2f}[/{cpu_load_5_color}], [{cpu_load_15_color}]{cpu_load_15:.2f}[/{cpu_load_15_color}]",
            f"[bold]Memory:[/bold]     {mem_bar} [{mem_color}]{mem_load:.1f}%[/{mem_color}]",
            f"[bold]Uptime:[/bold]     {format_uptime(system.get('uptime', 0))}"
            f"	[bold]CPU Temp:[/bold]   [{color}]{cpu_temp:.1f}°C[/{color}]   {cpu_emoji}",
        ]
        self.update("\n".join(lines))


class AdminUrlModal(ModalScreen):
    """A modal screen to display admin url and qr code"""

    def __init__(self, pihole_url: str, **kwargs):
        super().__init__(**kwargs)
        self.pihole_url = pihole_url

    def compose(self) -> ComposeResult:
        """Compose child widgets."""
        with Horizontal(id="modal-container"):
            with Vertical(id="qr-link-container"):
                admin_qr = generate_qrascii(self.pihole_url)
                yield Link(
                    "Pihole Admin URL",
                    url=self.pihole_url,
                    tooltip=self.pihole_url,
                    id="admin-link",
                )
                yield Static(admin_qr, id="admin_qr")
        with Center():
            yield Button("Close", variant="primary", id="close-modal")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-modal":
            self.app.pop_screen()


class PiHoleVersions(Container):
    """A widget to display component versions and a refresh progress bar."""

    def __init__(self, pihole_url: str, __version__: str, **kwargs):
        super().__init__(**kwargs)
        self.pihole_url = pihole_url
        self.__version__ = __version__

    def compose(self) -> ComposeResult:
        """Create child widgets for the container."""
        yield Static("Loading...", id="version-text")
        yield ProgressBar(
            total=100,
            show_eta=False,
            show_percentage=False,
            name="next refresh",
            id="refresh-progress",
        )
        yield Rule(line_style="double")
        with Center():
            yield Button("Show Admin URL", id="show-admin-url")

    def on_mount(self) -> None:
        self.border_title = "Component Versions"
        self.styles.border = ("round", "green")
        self.styles.border_title_align = "center"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "show-admin-url":
            self.app.push_screen(AdminUrlModal(self.pihole_url))

    def update_content(self, padd_data: dict) -> None:
        version_text_widget = self.query_one("#version-text")
        if not padd_data or padd_data.get("error"):
            version_text_widget.update("")  # Clear on error
            return

        version_data = padd_data.get("version")
        if not version_data:
            version_text_widget.update("Version data not available.")
            return

        any_updates = False
        checkmark = "✓"
        lines = [f"[bold]PADD-eInk:[/bold]	v{self.__version__} {checkmark}"]

        components = {"Pi-hole": "core", " Web UI": "web", "    FTL": "ftl"}
        for name, key in components.items():
            comp_data = version_data.get(key)
            if not comp_data:
                lines.append(f"[bold]{name}:[/bold]	N/A")
                continue

            local = comp_data.get("local", {}).get("version", "N/A")
            remote = comp_data.get("remote", {}).get("version", "N/A")

            status_str = ""
            if local != "N/A" and remote != "N/A" and compare_versions(remote, local) > 0:
                any_updates = True
                status_str = f"{local}[bold red]**[/bold red]"
            else:
                status_str = f"{local} {checkmark}" if local != "N/A" else "N/A"
            lines.append(f"[bold]{name}:[/bold]	{status_str}")

        if any_updates:
            lines.append("[bold red]** Update available[/bold red]")
        else:
            lines.append(
                f"[bold green]{checkmark} {checkmark} SYSTEM IS HEALTHY {checkmark} {checkmark}[/bold green]"
            )

        version_text_widget.update("\n".join(lines))


# --- Textual TUI Application (Main App Class) ---
class PADD_TUI(App):
    """A Textual TUI for Pi-hole statistics."""

    CSS_PATH = "padd_eink.tcss"

    BINDINGS = [
        ("r", "refresh", "Refresh Data"),
        ("q", "quit", "Quit"),
    ]

    TUI_REFRESH_INTERVAL = 60

    def __init__(self, pihole_client, pihole_url, __version__):
        super().__init__()
        self.pihole = pihole_client
        self.pihole_url = pihole_url
        self.__version__ = __version__
        self.countdown = self.TUI_REFRESH_INTERVAL

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with VerticalScroll(id="main-container"):
            yield PiHoleStats("Loading...")
            yield SystemStats("Loading...")
            yield PiHoleVersions(
                self.pihole_url, self.__version__, id="sidebar"
            )  # Container doesn't need initial content
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.run_update_worker()
        self.set_interval(self.TUI_REFRESH_INTERVAL, self.run_update_worker)
        self.set_interval(1, self.tick_progress_bar)  # Timer for progress bar
        self.title = f"PADD-eInk Terminal Mode v{self.__version__}"

    def tick_progress_bar(self) -> None:
        """Updates the progress bar every second."""
        self.countdown -= 1
        progress = (self.countdown / self.TUI_REFRESH_INTERVAL) * 100
        self.query_one(ProgressBar).progress = progress

    def run_update_worker(self) -> None:
        """Initiates the background data fetching worker and resets countdown."""
        self.countdown = self.TUI_REFRESH_INTERVAL  # Reset countdown on refresh
        self.update_data()

    @work(thread=True, exclusive=True)
    def update_data(self) -> None:
        """Fetches new data and updates the widgets from a background thread."""
        logger.info("TUI: Refreshing data in worker...")
        try:
            padd_data = self.pihole.get_padd_summary(full=True)

            # Call the update methods on each custom widget
            self.call_from_thread(self.query_one(PiHoleStats).update_content, padd_data)
            self.call_from_thread(self.query_one(SystemStats).update_content, padd_data)
            self.call_from_thread(
                self.query_one(PiHoleVersions).update_content, padd_data
            )

            logger.info("TUI: Display updated by worker.")
        except Exception as e:
            error_message = f"Error fetching data: {e}"
            logger.error(error_message)
            self.call_from_thread(
                self.query_one(PiHoleStats).update_content, {"error": error_message}
            )

    def action_refresh(self) -> None:
        """Called when the user presses the 'r' key."""
        # Update widgets to show a refreshing message
        self.query_one(PiHoleStats).update("Refreshing...")
        self.query_one(SystemStats).update("Refreshing...")
        self.query_one(PiHoleVersions).query_one("#version-text").update(
            "Refreshing..."
        )
        self.run_update_worker()

    def action_quit(self) -> None:
        """Called when the user presses the 'q' key."""
        self.pihole.close_session()
        self.exit()
