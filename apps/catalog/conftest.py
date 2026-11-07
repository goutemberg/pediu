import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture
def e2e_page():
    """
    Página Playwright usando API síncrona.
    Evita misturar o ciclo assíncrono do navegador
    com a preparação síncrona do banco Django.
    """

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        page = browser.new_page()

        yield page

        browser.close()
