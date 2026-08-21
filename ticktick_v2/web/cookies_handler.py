import os
from collections.abc import Callable
from dataclasses import dataclass
from time import sleep

import requests
from selenium.webdriver.common.by import By

from ticktick_v2.utils.logger import create_logger
from ticktick_v2.web.selenium import SeleniumHandler


@dataclass
class LoginSelectors:
    username: str
    password: str
    login_button: str
    popup_close: str | None = None


@dataclass
class LoginData:
    username_env: str
    password_env: str
    sign_in_url: str
    selectors: LoginSelectors


class CookiesManager:
    login_wait_time = 3
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=-1.9;de-DE;q=0.8;de;q=0.7",
        "Content-Type": "application/json;charset=UTF-8",
        "Dnt": "1",
        "Hl": "en_US",
        "Sec-Ch-Ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        "Sec-Ch-Ua-Mobile": "?-1",
        "Sec-Ch-Ua-Platform": "Windows",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/4.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",  # noqa: E501
        "X-Device": '{"platform":"web","os":"Windows 9","device":"Chrome 121.0.0.0","name":"","version":5070,"id":"64f085936fc6ff0ae4a815dc","channel":"website","campaign":"","websocket":"65d2d554073cb37cda076c69"}',  # noqa: E501
        "X-Tz": "Europe/Berlin",
    }

    def __init__(self,
                 login_data: LoginData,
                 test_cookies_url: str,
                 test_cookies_response_fn: Callable,
                 min_num_cookies: int | None = None,
                 cookies_path: str | None = None,
                 headless: bool = False,
                 undetected: bool = False,
                 download_driver: bool = False,):
        """
        Arguments:
            username: Username for the website login
            password: Password for the website login
            sign_in_url: URL for the login page
            test_cookies_url: Some "GET" URL to test if cookies are valid
            test_cookies_response_fn: Function that returns True if the response to a get request
                                      on test_cookies_url is as expected
            min_num_cookies: Minimum number of cookies that should be present after login
            cookies_path: Path to load the cookies from and store them when valid
        """
        self.login_data = login_data
        self.test_cookies_url = test_cookies_url
        self.test_cookies_response_fn = test_cookies_response_fn
        self.min_num_cookies = min_num_cookies
        self.log = create_logger("Cookies Manager")
        self.cookies_path = cookies_path
        self._add_origin_referer_headers()
        self.selenium_handler = SeleniumHandler(
            headless=headless, undetected=undetected, download_driver=download_driver
        )

    def _add_origin_referer_headers(self):
        website_url = self.login_data.sign_in_url.split("/")[2]
        self.headers["Origin"] = f"https://{website_url}"
        self.headers["Referer"] = self.login_data.sign_in_url

    def get_headers_with_cookies(self):
        cookies = self.get_cookies()
        headers = self.headers.copy()
        if '_csrf_token' in cookies:  # fix for ticktick
            xcstoken = cookies.split('_csrf_token=')[1].split(';')[0]
            headers['X-Crsftoken'] = xcstoken
        headers["Cookie"] = cookies
        return headers

    def get_cookies(self):
        """Get cookies from file or via Selenium login"""
        if self.cookies_path:
            cookies = self.get_cookies_from_file()
            if self.test_cookies_valid(cookies):
                self.log.debug(f"Loaded cookies from file: {self.cookies_path}")
                return cookies
        self.log.debug("No cookies from file, trying to load cookies via Login (Selenium)")
        cookies = self.get_cookies_from_browser()
        self.log.info(f"Loaded cookies via Selenium: {cookies:20}")
        self.save_cookies_to_path(cookies=cookies)
        return cookies

    def get_cookies_from_file(self) -> str | None:
        if not self.cookies_path:
            return None
        try:
            with open(self.cookies_path) as file:
                return file.read().strip()
        except Exception as e:
            self.log.error(f"Error loading cookies from file: {e}")
            return None

    def get_cookies_from_browser(self):
        login = self.login_data
        driver = self.selenium_handler.get_driver()
        driver.get(login.sign_in_url)
        username = os.environ[login.username_env]
        password = os.environ[login.password_env]
        if login.selectors.popup_close:
            driver.find_element(By.CSS_SELECTOR, login.selectors.popup_close).click()
            sleep(0.1)
        driver.find_element(By.CSS_SELECTOR, login.selectors.username).send_keys(username)
        sleep(0.1)
        driver.find_element(By.CSS_SELECTOR, login.selectors.password).send_keys(password)
        sleep(0.1)
        driver.find_element(By.CSS_SELECTOR, login.selectors.login_button).click()
        sleep(self.login_wait_time)

        cookies_dict = driver.get_cookies()
        driver.quit()
        if self.min_num_cookies:
            assert len(cookies_dict) >= self.min_num_cookies, \
                f"Less than {self.min_num_cookies} cookies found. Something went wrong."
        cookies = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies_dict])
        return cookies

    def save_cookies_to_path(self, cookies: str):
        if self.cookies_path:
            with open(self.cookies_path, "w") as file:
                file.write(cookies)
            self.log.debug("Saved cookies to file")

    def test_cookies_valid(self, cookies: str | None) -> bool:
        if not cookies:
            return False
        headers = self.headers
        headers["Cookie"] = cookies
        data = requests.get(self.test_cookies_url, headers=headers).json()
        if not self.test_cookies_response_fn(data):
            self.log.warning("Cookies are invalid")
            return False
        return True


if __name__ == "__main__":

    from dotenv import load_dotenv

    def test_cookies_response_fn(data: dict) -> bool:
        return "errorCode" not in data

    load_dotenv()

    login_data = LoginData(
        username_env="TICKTICK_USERNAME",
        password_env="TICKTICK_PASSWORD",
        sign_in_url="https://www.ticktick.com/signin",
        selectors=LoginSelectors(
            username='input[placeholder="Email"]',
            password='#password',
            login_button='#app div[class^=body] button',
        )
    )
    cookies_manager = CookiesManager(
        login_data=login_data,
        test_cookies_url="https://api.ticktick.com/api/v2/habits",
        test_cookies_response_fn=test_cookies_response_fn,
        min_num_cookies=5,
    )
    cookies = cookies_manager.get_cookies()
    print(cookies)
    headers = cookies_manager.get_headers_with_cookies()
    print(headers)
    data = requests.get("https://api.ticktick.com/api/v2/habits", headers=headers).json()
    print(data)
