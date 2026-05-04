import hashlib
import random
import time
import threading
from datetime import datetime
import urllib3
import json
import os

# --- Configuration ---
target = "59:59"  # Target time in "MM:SS" format
cookie_file = "cookies.txt"  # File with one cookie per line
feed_time_shift = 1400  # Start 1400ms before target
request_interval = 1000  # 1000ms between requests
stop_after = 2500  # Stop 2500ms after target
request_timeout = 5  # Timeout for individual requests (seconds)

# --- Colors (optional) ---
class Colors:
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"

col_g = Colors.GREEN
col_b = Colors.BLUE
col_y = Colors.YELLOW
col_r = Colors.RED

# --- Global Variables ---
valid_cookies = []  # Stores valid cookies
results = {}  # Stores results for each cookie
lock = threading.Lock()  # Thread-safe lock for results

# --- Device ID Generation ---
def generate_device_id():
    random_data = f"{random.random()}-{time.time()}-{os.urandom(4).hex()}"
    return hashlib.sha1(random_data.encode('utf-8')).hexdigest().upper()

# --- Read Cookies from File ---
def read_cookies():
    try:
        with open(cookie_file, "r") as f:
            cookies = [line.strip() for line in f if line.strip()]
        return cookies
    except FileNotFoundError:
        print(col_r + f"[Error]: File '{cookie_file}' not found." + Colors.RESET)
        exit()

# --- Check Cookie Status ---
def check_cookie_status(session, cookie_value):
    try:
        url = "https://sgp-api.buy.mi.com/bbs/api/global/user/bl-switch/state"
        device_id = generate_device_id()
        headers = {
            "Cookie": f"new_bbs_serviceToken={cookie_value};versionCode=500411;versionName=5.4.11;deviceId={device_id};"
        }
        response = session.make_request('GET', url, headers=headers)
        if response is None:
            return False, "Request failed"

        response_data = json.loads(response.data.decode('utf-8'))
        response.release_conn()

        if response_data.get("code") == 100004:
            return False, "Expired cookie"

        data = response_data.get("data", {})
        is_pass = data.get("is_pass")
        button_state = data.get("button_state")

        if is_pass == 4 and button_state == 1:
            return True, "Ready"
        elif is_pass == 1:
            return False, "Already approved"
        else:
            return False, f"Blocked (state: {is_pass}, button: {button_state})"

    except Exception as e:
        return False, f"Error: {str(e)}"

# --- HTTP Session ---
class HTTP11Session:
    def __init__(self):
        self.http = urllib3.PoolManager(
            maxsize=20,
            retries=True,
            timeout=urllib3.Timeout(connect=2.0, read=request_timeout),
            headers={}
        )

    def make_request(self, method, url, headers=None, body=None):
        try:
            request_headers = {}
            if headers:
                request_headers.update(headers)
                request_headers['Content-Type'] = 'application/json; charset=utf-8'

            if method == 'POST':
                if body is None:
                    body = '{"is_retry":true}'.encode('utf-8')
                request_headers['Content-Length'] = str(len(body))
                request_headers['Accept-Encoding'] = 'gzip, deflate, br'
                request_headers['User-Agent'] = 'okhttp/4.12.0'
                request_headers['Connection'] = 'keep-alive'

            response = self.http.request(
                method,
                url,
                headers=request_headers,
                body=body,
                preload_content=False,
                timeout=request_timeout
            )
            return response
        except Exception as e:
            return None

# --- Send Request (Non-blocking) ---
def send_request(session, cookie_value, request_time):
    device_id = generate_device_id()
    url = "https://sgp-api.buy.mi.com/bbs/api/global/apply/bl-auth"
    headers = {
        "Cookie": f"new_bbs_serviceToken={cookie_value};versionCode=500411;versionName=5.4.11;deviceId={device_id};"
    }

    try:
        response = session.make_request('POST', url, headers=headers)
        if response:
            response_data = json.loads(response.data.decode('utf-8'))
            response.release_conn()
            code = response_data.get("code")
            data = response_data.get("data", {})

            with lock:
                results[cookie_value] = {
                    "time": request_time.strftime('%H:%M:%S'),
                    "device_id": device_id,
                    "code": code,
                    "data": data
                }
    except Exception as e:
        with lock:
            results[cookie_value] = {
                "time": request_time.strftime('%H:%M:%S'),
                "device_id": device_id,
                "error": str(e)
            }

# --- Time Logic ---
def wait_until_feed_time():
    target_min, target_sec = map(int, target.split(":"))
    while True:
        now = datetime.now()
        if now.minute == target_min and now.second == target_sec:
            # Calculate feed_time_shift (1400ms before target)
            feed_time = now - timedelta(milliseconds=feed_time_shift)
            if now >= feed_time:
                print(col_g + f"[Feed Time Reached]: Starting requests at {now.strftime('%H:%M:%S')}" + Colors.RESET)
                return
        time.sleep(0.1)

# --- Main Loop ---
def main_loop(session):
    start_time = datetime.now()
    target_min, target_sec = map(int, target.split(":"))
    stop_time = start_time.replace(minute=target_min, second=target_sec) + timedelta(milliseconds=stop_after)

    index = 0
    while datetime.now() < stop_time:
        if index >= len(valid_cookies):
            index = 0  # Loop back to the first cookie

        cookie = valid_cookies[index]
        request_time = datetime.now()
        threading.Thread(
            target=send_request,
            args=(session, cookie, request_time),
            daemon=True
        ).start()

        index += 1
        time.sleep(request_interval / 1000)  # Convert ms to seconds

# --- Print Results ---
def print_results():
    print("\n" + col_y + "=== Results ===" + Colors.RESET)
    for cookie, result in results.items():
        status = result.get("code", result.get("error", "Unknown"))
        print(
            f"{col_g}[Cookie]: {cookie[:10]}...{Colors.RESET} "
            f"{col_b}[Time]: {result['time']}{Colors.RESET} "
            f"{col_b}[Device ID]: {result['device_id'][:8]}...{Colors.RESET} "
            f"{col_y}[Status]: {status}{Colors.RESET}"
        )

# --- Main Function ---
def main():
    global valid_cookies

    # Read cookies from file
    cookies = read_cookies()
    if not cookies:
        print(col_r + "[Error]: No cookies found in file." + Colors.RESET)
        exit()

    # Initialize session
    session = HTTP11Session()

    # Check all cookies
    print(col_y + "[Checking Cookies...]" + Colors.RESET)
    for cookie in cookies:
        is_valid, status = check_cookie_status(session, cookie)
        print(f"{col_g if is_valid else col_r}[{cookie[:10]}...]: {status}{Colors.RESET}")
        if is_valid:
            valid_cookies.append(cookie)

    if not valid_cookies:
        print(col_r + "[Error]: No valid cookies found." + Colors.RESET)
        exit()

    print(col_g + f"\n[Valid Cookies]: {len(valid_cookies)}" + Colors.RESET)

    # Wait until feed_time_shift before target
    wait_until_feed_time()

    # Start main loop
    main_loop(session)

    # Wait for all threads to finish (optional)
    time.sleep(1)

    # Print results
    print_results()

if __name__ == "__main__":
    from datetime import timedelta
    main()
