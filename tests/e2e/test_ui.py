"""End-to-end tests of the planner page's JavaScript."""

import json
import logging
import re
import time

from playwright.sync_api import Locator, Page, expect

from big_o.app import LINE_METADATA, metro_graph


def choose_station(field: Locator, name: str) -> None:
    """Type into a station search box and click the option with exactly that name."""
    field.fill(name)
    listbox = field.page.locator(f"#{field.get_attribute('aria-controls')}")
    listbox.get_by_role("option").filter(has=field.page.get_by_text(name, exact=True)).click()


def find_route(page: Page, source: str, destination: str, via: tuple[str, ...] = ()) -> None:
    choose_station(page.locator("#source-search"), source)
    choose_station(page.locator("#destination-search"), destination)
    for name in via:
        page.click("#add-stop")
        choose_station(page.locator(".via-row .station-input").last, name)
    page.click("#find-route")


def stop_names(page: Page) -> list[str]:
    # The name element also holds VIA/line chips; the station name is its first text node.
    return page.locator(".stop-name").evaluate_all(
        "els => els.map(el => el.firstChild.textContent.trim())"
    )


# --- Loading -----------------------------------------------------------------

def test_loads_stations_and_network(app_page: Page):
    count = len(metro_graph.stations)

    expect(app_page.locator("#api-status")).to_have_text(f"{count} stations · network loaded")
    # One placeholder option plus every station, in both dropdowns.
    expect(app_page.locator("#source option")).to_have_count(count + 1)
    expect(app_page.locator("#destination option")).to_have_count(count + 1)
    expect(app_page.locator(".legend-item")).to_have_count(len(LINE_METADATA))
    expect(app_page.locator("#add-stop")).to_be_enabled()


def test_reports_unavailable_backend(page: Page, live_server):
    page.route(
        "**/stations",
        lambda route: route.fulfill(status=500, content_type="application/json",
                                    body=json.dumps({"message": "Database unavailable"})),
    )
    page.goto(live_server)

    expect(page.locator("#api-status")).to_have_text("Route engine unavailable")
    expect(page.locator("#message")).to_have_text("Database unavailable Make sure the Flask server is running.")
    expect(page.locator("#add-stop")).to_be_disabled()


# --- Finding a route ---------------------------------------------------------

def test_finds_and_renders_a_route(app_page: Page):
    find_route(app_page, "Central Secretariat", "Mandi House")

    expect(app_page.locator("#total-time")).to_have_text("4 min 42 sec")
    expect(app_page.locator("#interchanges")).to_have_text("0")
    expect(app_page.locator("#stop-count")).to_have_text("3 stops")
    expect(app_page.locator("#map-title")).to_have_text("Central Secretariat → Mandi House")
    assert stop_names(app_page) == ["Central Secretariat", "Janpath", "Mandi House"]
    expect(app_page.locator(".stop-meta").first).to_have_text(re.compile(r"^Start · "))
    expect(app_page.locator(".stop-meta").last).to_have_text(re.compile(r"^Arrive · "))
    expect(app_page.locator(".endpoint-tooltip", has_text="START · Central Secretariat")).to_be_visible()
    expect(app_page.locator(".endpoint-tooltip", has_text="DESTINATION · Mandi House")).to_be_visible()


def test_mode_buttons_toggle_and_are_sent(app_page: Page):
    fewest = app_page.locator(".mode[data-mode=fewest_interchanges]")
    fastest = app_page.locator(".mode[data-mode=fastest]")

    fewest.click()
    expect(fewest).to_have_class(re.compile(r"\bactive\b"))
    expect(fastest).not_to_have_class(re.compile(r"\bactive\b"))

    with app_page.expect_request("**/route") as request:
        find_route(app_page, "Central Secretariat", "Mandi House")
    assert request.value.post_data_json["mode"] == "fewest_interchanges"


def test_rejects_same_source_and_destination(app_page: Page):
    find_route(app_page, "Rajiv Chowk", "Rajiv Chowk")

    expect(app_page.locator("#message")).to_have_text("Choose two different stations for your journey.")


def test_route_error_message_names_stations(app_page: Page):
    app_page.route(
        "**/route",
        lambda route: route.fulfill(status=404, content_type="application/json",
                                    body=json.dumps({"error": "route_not_found", "message": "No route from 'x' to 'y'"})),
    )
    find_route(app_page, "Central Secretariat", "Mandi House")

    expect(app_page.locator("#message")).to_have_text(
        "There is no available route from Central Secretariat to Mandi House. Try another pair of stations."
    )


def test_swap_exchanges_endpoints_and_reverses_stops(app_page: Page, station_id):
    choose_station(app_page.locator("#source-search"), "Central Secretariat")
    choose_station(app_page.locator("#destination-search"), "Mandi House")
    for name in ("Rajiv Chowk", "Barakhamba"):
        app_page.click("#add-stop")
        choose_station(app_page.locator(".via-row .station-input").last, name)

    app_page.click("#swap")

    expect(app_page.locator("#source")).to_have_value(station_id("Mandi House"))
    expect(app_page.locator("#destination")).to_have_value(station_id("Central Secretariat"))
    assert app_page.locator(".via-row select").evaluate_all("els => els.map(el => el.value)") == [
        station_id("Barakhamba"),
        station_id("Rajiv Chowk"),
    ]
    # The search boxes show the swapped stations too.
    expect(app_page.locator("#source-search")).to_have_value("Mandi House")
    expect(app_page.locator("#destination-search")).to_have_value("Central Secretariat")
    assert app_page.locator(".via-row .station-input").evaluate_all("els => els.map(el => el.value)") == [
        "Barakhamba",
        "Rajiv Chowk",
    ]


# --- Station search ----------------------------------------------------------

def test_station_search_matches_words_in_any_spelling(app_page: Page):
    source = app_page.locator("#source-search")
    source.fill("noida 52")
    expect(app_page.locator("#source-list [role=option]")).to_have_count(1)
    expect(app_page.locator("#source-list [role=option]")).to_contain_text("Noida Sec-52")

    source.fill("zzzz")
    expect(app_page.locator("#source-list")).to_have_text("No matching station")


def test_station_search_by_code_and_keyboard(app_page: Page, station_id):
    source = app_page.locator("#source-search")
    source.fill(station_id("Mandi House"))
    source.press("Enter")

    expect(source).to_have_value("Mandi House")
    expect(app_page.locator("#source")).to_have_value(station_id("Mandi House"))
    expect(app_page.locator("#source-list")).to_be_hidden()


def test_station_search_escape_keeps_previous_station(app_page: Page, station_id):
    choose_station(app_page.locator("#source-search"), "Rajiv Chowk")
    source = app_page.locator("#source-search")
    source.fill("hauz")
    source.press("Escape")

    expect(source).to_have_value("Rajiv Chowk")
    expect(app_page.locator("#source")).to_have_value(station_id("Rajiv Chowk"))


def test_leaving_station_search_picks_best_match(app_page: Page, station_id):
    source = app_page.locator("#source-search")
    source.fill("kashmere")
    source.press("Tab")

    expect(source).to_have_value("Kashmere Gate")
    expect(app_page.locator("#source")).to_have_value(station_id("Kashmere Gate"))


# --- Intermediate (via) stops ------------------------------------------------

def test_add_and_remove_stops(app_page: Page):
    add = app_page.locator("#add-stop")
    labels = app_page.locator(".via-row .field-label")

    for _ in range(3):
        add.click()
    expect(labels).to_have_text(["Via stop 1", "Via stop 2", "Via stop 3"])
    expect(add).to_be_disabled()  # limit is 3

    app_page.locator(".via-remove").nth(1).click()
    expect(labels).to_have_text(["Via stop 1", "Via stop 2"])
    expect(add).to_be_enabled()


def test_route_via_intermediate_station(app_page: Page, station_id):
    with app_page.expect_request("**/route") as request:
        find_route(app_page, "Central Secretariat", "Mandi House", via=("Rajiv Chowk",))
    assert request.value.post_data_json["via"] == [station_id("Rajiv Chowk")]

    expect(app_page.locator("#map-title")).to_have_text("Central Secretariat → Rajiv Chowk → Mandi House")
    assert stop_names(app_page) == ["Central Secretariat", "Patel Chowk", "Rajiv Chowk", "Barakhamba", "Mandi House"]
    rajiv = app_page.locator(".stop", has_text="Rajiv Chowk")
    expect(rajiv.locator(".via-chip")).to_have_text("Via")
    expect(rajiv.locator(".stop-dot")).to_have_class(re.compile(r"\bvia\b"))
    expect(rajiv.locator(".stop-meta")).to_have_text(re.compile(r"^Via stop · Continue on "))
    # Yellow -> Blue at Rajiv Chowk: one interchange, shown as two line chips.
    expect(app_page.locator("#interchanges")).to_have_text("1")
    expect(rajiv.locator(".line-chip")).to_have_count(2)
    expect(app_page.locator(".endpoint-tooltip", has_text="VIA · Rajiv Chowk")).to_be_visible()


def test_rejects_blank_stop(app_page: Page):
    choose_station(app_page.locator("#source-search"), "Central Secretariat")
    choose_station(app_page.locator("#destination-search"), "Mandi House")
    app_page.click("#add-stop")
    app_page.click("#find-route")

    expect(app_page.locator("#message")).to_have_text("Choose a station for each via stop, or remove it.")


def test_rejects_stop_repeating_previous_station(app_page: Page):
    find_route(app_page, "Central Secretariat", "Mandi House", via=("Central Secretariat",))

    expect(app_page.locator("#message")).to_have_text("Each stop must be different from the one before it.")


def test_no_route_message_names_the_stop(app_page: Page):
    app_page.route(
        "**/route",
        lambda route: route.fulfill(status=404, content_type="application/json",
                                    body=json.dumps({"error": "route_not_found", "message": "No route from 'x' to 'y' via 'z'"})),
    )
    find_route(app_page, "Central Secretariat", "Mandi House", via=("Rajiv Chowk", "Barakhamba"))

    expect(app_page.locator("#message")).to_have_text(
        "There is no available route from Central Secretariat to Mandi House through Rajiv Chowk and Barakhamba. "
        "Try a different stop, or remove it."
    )


# --- Walkways ----------------------------------------------------------------

def test_walkway_shown_as_walk(app_page: Page):
    find_route(app_page, "Noida Sector 50", "Noida Sec-61")

    expect(app_page.locator(".stop", has_text="Noida Sector 51").locator(".stop-meta")).to_have_text(
        "Walk to Noida Sec-52 (5 min)"
    )
    expect(app_page.locator("#interchanges")).to_have_text("1")


# --- Map labels --------------------------------------------------------------

def visible_label_boxes(page: Page) -> list[dict]:
    return page.locator(".station-label:not(.is-hidden) span").evaluate_all(
        "els => els.map(el => { const r = el.getBoundingClientRect(); "
        "return {text: el.textContent, x1: r.left, y1: r.top, x2: r.right, y2: r.bottom}; })"
    )


def assert_no_overlaps(boxes: list[dict]) -> None:
    overlaps = [
        (a["text"], b["text"])
        for i, a in enumerate(boxes)
        for b in boxes[i + 1:]
        if a["x1"] < b["x2"] - 1 and b["x1"] < a["x2"] - 1 and a["y1"] < b["y2"] - 1 and b["y1"] < a["y2"] - 1
    ]
    assert overlaps == []


def test_station_labels_are_shown_without_overlapping(app_page: Page):
    expect(app_page.locator(".station-label:not(.is-hidden)").first).to_be_attached()

    boxes = visible_label_boxes(app_page)
    assert boxes, "expected some interchange / terminus labels on the map"
    assert_no_overlaps(boxes)


def test_route_greys_out_the_rest_of_the_map(app_page: Page):
    expect(app_page.locator("#route-map")).not_to_have_class(re.compile(r"\bhas-route\b"))

    find_route(app_page, "Central Secretariat", "Mandi House", via=("Rajiv Chowk",))

    expect(app_page.locator("#route-map")).to_have_class(re.compile(r"\bhas-route\b"))
    # Off-route labels fade; route labels don't; endpoints and stops use their own tooltips.
    expect(app_page.locator(".station-label.is-muted").first).to_be_attached()
    expect(app_page.locator(".station-label:not(.is-muted):not(.is-hidden)", has_text="Rajiv Chowk")).to_have_count(0)
    app_page.wait_for_timeout(800)  # let the zoom-to-route animation settle
    assert_no_overlaps(visible_label_boxes(app_page))


# --- Theme and title ---------------------------------------------------------

def test_theme_toggle_switches_palette_and_persists(app_page: Page):
    body = app_page.locator("body")
    face = "getComputedStyle(document.body).getPropertyValue('--face').trim()"

    # Light mode is the default: cream windows on the teal desktop.
    expect(body).to_have_attribute("data-theme", "light")
    expect(app_page.locator("#theme-label")).to_have_text("Dark mode")
    assert app_page.evaluate(face) == "#e4dec9"

    app_page.click("#theme-toggle")
    expect(body).to_have_attribute("data-theme", "dark")
    expect(app_page.locator("#theme-toggle")).to_have_attribute("aria-label", "Switch to light mode")

    app_page.click("#theme-toggle")
    expect(body).to_have_attribute("data-theme", "light")
    expect(app_page.locator("#theme-toggle")).to_have_attribute("aria-label", "Switch to dark mode")
    assert app_page.evaluate(face) == "#e4dec9"

    # The choice of light mode is saved across reloads.
    app_page.reload()
    expect(body).to_have_attribute("data-theme", "light")
    assert app_page.evaluate(face) == "#e4dec9"


def test_kinetic_title_animates_letters(browser, live_server):
    # Opt back in to motion: the title is split into per-letter spans and revealed.
    context = browser.new_context(reduced_motion="no-preference")
    page = context.new_page()
    page.goto(live_server)

    expect(page.locator(".kinetic-char")).to_have_count(len("METERONORMATIVE"))
    expect(page.locator(".kinetic-title")).to_have_class(re.compile(r"\bis-visible\b"))
    context.close()


# --- Interaction logging ------------------------------------------------------
# These read the live server's own log records (it runs in this process), so they
# check the whole path: browser -> /log -> server log.

def logged_ui_events(caplog, minimum: int = 1, timeout: float = 5.0) -> list[dict]:
    """Parsed 'UI <event> <json details>' server log lines, once at least `minimum` arrived."""
    deadline = time.monotonic() + timeout
    while True:
        events = []
        for record in caplog.records:
            match = re.match(r"UI (\w+) (\{.*\}) \[req ", record.getMessage())
            if record.name == "big_o" and match:
                events.append({"event": match[1], "details": json.loads(match[2])})
        if len(events) >= minimum or time.monotonic() > deadline:
            return events
        time.sleep(0.05)  # beacons are fire-and-forget


def test_interactions_are_logged(page: Page, live_server, station_id, caplog):
    caplog.set_level(logging.INFO, logger="big_o")
    page.goto(live_server)
    expect(page.locator("#api-status")).to_have_text(re.compile(r"network loaded$"))

    page.locator(".mode[data-mode=fewest_interchanges]").click()
    page.click("#add-stop")
    page.locator(".via-remove").click()
    page.click("#swap")
    page.click("#theme-toggle")
    find_route(page, "Central Secretariat", "Mandi House")
    expect(page.locator("#total-time")).not_to_have_text("—")
    find_route(page, "Rajiv Chowk", "Rajiv Chowk")

    events = logged_ui_events(caplog, minimum=10)
    names = [event["event"] for event in events]
    for name in ("page_loaded", "mode_changed", "stop_added", "stop_removed", "stations_swapped",
                 "theme_changed", "route_requested", "route_found", "validation_failed"):
        assert name in names
    found = next(event for event in events if event["event"] == "route_found")
    assert found["details"]["source"] == station_id("Central Secretariat")
    assert found["details"]["mode"] == "fewest_interchanges"
    assert found["details"]["interchanges"] == 0
    assert next(e for e in events if e["event"] == "theme_changed")["details"] == {"theme": "dark"}
    assert next(e for e in events if e["event"] == "validation_failed")["details"] == {"reason": "same_station"}


def test_failed_route_is_logged(app_page: Page, caplog):
    caplog.set_level(logging.INFO, logger="big_o")
    app_page.route(
        "**/route",
        lambda route: route.fulfill(status=404, content_type="application/json",
                                    body=json.dumps({"error": "route_not_found", "message": "No route from 'x' to 'y'"})),
    )
    find_route(app_page, "Central Secretariat", "Mandi House")

    events = logged_ui_events(caplog, minimum=2)
    failed = next(event for event in events if event["event"] == "route_failed")
    assert failed["details"]["status"] == 404
    assert failed["details"]["error"] == "route_not_found"


def test_javascript_errors_are_logged(app_page: Page, caplog):
    caplog.set_level(logging.INFO, logger="big_o")
    app_page.evaluate("setTimeout(() => { throw new Error('test explosion'); })")

    events = logged_ui_events(caplog)
    error = next(event for event in events if event["event"] == "js_error")
    assert "test explosion" in error["details"]["message"]


def test_logging_failure_does_not_break_the_page(app_page: Page):
    app_page.route("**/log", lambda route: route.abort())

    find_route(app_page, "Central Secretariat", "Mandi House")

    expect(app_page.locator("#total-time")).to_have_text("4 min 42 sec")
