import os
from ticktick_v2.utils.config import ROOT_DIR
from ticktick_v2.utils.logger import create_logger
from ticktick_v2.web.cookies_handler import CookiesManager, LoginData, LoginSelectors


def get_authenticated_ticktick_headers(
    cookies_path: str | None = None,
    username_env: str = "TICKTICK_EMAIL",
    password_env: str = "TICKTICK_PASSWORD",
    headless: bool = False,
    undetected: bool = False,
    download_driver: bool = False,
):
    log = create_logger("TickTick Cookies Helper")

    if os.getenv(username_env) is None or os.getenv(password_env) is None:
        log.error(
            f"Either username or password environment variables {username_env} | {password_env} is None"
        )

    cookies_manager = CookiesManager(
        login_data=LoginData(
            username_env=username_env,
            password_env=password_env,
            sign_in_url="https://www.ticktick.com/signin",
            selectors=LoginSelectors(
                username='input[placeholder="Email"]',
                password="#password",
                login_button="#app div[class^=body] button",
            ),
        ),
        test_cookies_url="https://api.ticktick.com/api/v2/habits",
        test_cookies_response_fn=lambda data: "errorCode" not in data,
        min_num_cookies=5,
        headless=headless,
        undetected=undetected,
        download_driver=download_driver,
    )
    if cookies_path:
        cookies_manager.cookies_path = cookies_path
    elif ROOT_DIR:
        cookies_manager.cookies_path = f"{ROOT_DIR}/.ticktick-cookies.json"
    else:
        cookies_manager.cookies_path = "../../.ticktick-cookies.json"

    headers = cookies_manager.get_headers_with_cookies()

    return headers
